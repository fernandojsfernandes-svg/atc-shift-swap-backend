import os
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from security import hash_password
from database import get_db
from models import User, Shift, ShiftType, MonthlySchedule, Team, SwapHistory
from parsers.pdf_parser import detect_schedule_month_year_from_pdf, parse_pdf

router = APIRouter(
    prefix="/import",
    tags=["Import"]
)

# Pastas dos PDF: definidas por variáveis de ambiente ou valor por defeito
# Coloca os PDF do mês corrente em PDF_FOLDER_ATUAL e do mês seguinte em PDF_FOLDER_SEGUINTE
PDF_FOLDER_ATUAL = os.environ.get(
    "PDF_FOLDER_ATUAL",
    "C:/PARSER_ESCALAS/PDF_Escalas/atual"
)
PDF_FOLDER_SEGUINTE = os.environ.get(
    "PDF_FOLDER_SEGUINTE",
    "C:/PARSER_ESCALAS/PDF_Escalas/seguinte"
)
PDF_FOLDERS = [PDF_FOLDER_ATUAL, PDF_FOLDER_SEGUINTE]

# Equipas esperadas (5 turnos A–E). Se após o import não forem 5, é devolvido um aviso.
EXPECTED_TEAMS = {"A", "B", "C", "D", "E"}

# Frase obrigatória no body para POST /clear-schedules (evita apagar por engano).
CLEAR_SCHEDULES_CONFIRM_PHRASE = "APAGAR_TODAS_AS_ESCALAS"
# Opcional: definir CLEAR_SCHEDULES_SECRET no ambiente e enviar header X-Clear-Schedules-Secret.
CLEAR_SCHEDULES_SECRET_ENV = "CLEAR_SCHEDULES_SECRET"


class ClearSchedulesBody(BaseModel):
    confirm: str = Field(
        ...,
        description=f'Deve ser exatamente: {CLEAR_SCHEDULES_CONFIRM_PHRASE}',
    )


def _clear_all_schedules_and_swap_data(db: Session) -> dict[str, int]:
    """
    Apaga todos os turnos (shifts), escalas mensais (monthly_schedules) e dados de trocas
    que dependem deles. Utilizadores, equipas e tipos de turno mantêm-se.
    Ordem respeita FKs (SQLite/Postgres).
    """
    counts: dict[str, int] = {}

    def count_table(name: str) -> int:
        r = db.execute(text(f"SELECT COUNT(*) FROM {name}"))
        return int(r.scalar() or 0)

    before = {
        "monthly_schedules": count_table("monthly_schedules"),
        "shifts": count_table("shifts"),
    }

    # Dependências primeiro (swap_* e ciclos referem shifts / swap_requests)
    stmts = [
        "DELETE FROM swap_notifications",
        "DELETE FROM swap_action_dismissals",
        "DELETE FROM swap_action_history",
        "DELETE FROM swap_history",
        "DELETE FROM swap_preferences",
        "DELETE FROM swap_wanted_options",
        "DELETE FROM swap_direct_targets",
        "DELETE FROM cycle_swaps",
        "DELETE FROM cycle_confirmations",
        "DELETE FROM cycle_proposals",
        "DELETE FROM swap_requests",
        "DELETE FROM shifts",
        "DELETE FROM monthly_schedules",
    ]
    for sql in stmts:
        db.execute(text(sql))
    db.commit()

    counts["monthly_schedules_removed"] = before["monthly_schedules"]
    counts["shifts_removed"] = before["shifts"]
    return counts

# Códigos de baixa prioridade para merge entre equipas no mesmo dia.
# Ex.: mE (mudança de equipa) pode aparecer numa equipa enquanto noutra existe o turno real.
LOW_PRIORITY_CODES = {"ME", "AF"}


def _norm_code(code: str | None) -> str:
    return (code or "").strip().upper()


def _should_replace_existing_code(existing_code: str | None, new_code: str | None) -> bool:
    """
    Decide se um novo código deve sobrescrever o código já existente para (user, day).
    Regra principal:
    - não substituir um turno "real" por marcadores de baixa prioridade (mE/AF)
    - permitir substituir mE/AF por um código mais concreto
    - se ambos são do mesmo "nível", mantém o novo (last write wins)
    """
    e = _norm_code(existing_code)
    n = _norm_code(new_code)
    if not n:
        return False
    if e and e not in LOW_PRIORITY_CODES and n in LOW_PRIORITY_CODES:
        return False
    return True


def _mark_inconsistencies_for_schedule(db: Session, schedule: MonthlySchedule):
    """
    Marca inconsistency_flag/message em shifts cuja situação não bate certo
    com o histórico de trocas (SwapHistory) conhecido.
    Regras simples:
    - Para trocas 2-a-2 (accept_swap): depois da troca, espera-se que:
        shift_offered.user_id == accepter_id
        shift_received.user_id == requester_id
      Se não for assim após o import, marcamos ambos os turnos como inconsistentes.
    - Para registos de ciclos, aplicamos apenas a primeira regra:
        shift_offered.user_id deve ser o accepter_id; se não for, marcamos.
    """
    # Limpar flags antigas deste schedule
    db.query(Shift).filter(Shift.schedule_id == schedule.id).update(
        {"inconsistency_flag": False, "inconsistency_message": None}
    )

    message = (
        "Turno trocado mas a escala importada ainda não reflete esta troca. "
        "Deve aguardar pela próxima escala ou confirmar junto do serviço de escalas."
    )

    # Histórico para este schedule (qualquer um dos dois turnos pertence a esta escala)
    histories = (
        db.query(SwapHistory)
        .join(Shift, SwapHistory.shift_id_offered == Shift.id)
        .filter(Shift.schedule_id == schedule.id)
        .all()
    )

    for h in histories:
        offered = db.query(Shift).filter(Shift.id == h.shift_id_offered).first()
        received = db.query(Shift).filter(Shift.id == h.shift_id_received).first()
        if not offered or not received:
            continue

        inconsistent = False

        # Regra principal: turno oferecido deve estar no utilizador que o aceitou
        if h.accepter_id and offered.user_id != h.accepter_id:
            inconsistent = True

        # Para trocas simples (sem ciclo): turno recebido deve estar no requester
        if h.cycle_id is None and received.user_id != h.requester_id:
            inconsistent = True

        if inconsistent:
            for sh in (offered, received):
                sh.inconsistency_flag = True
                sh.inconsistency_message = message

    db.commit()


@router.post("/schedules")
def import_schedules(db: Session = Depends(get_db)):
    """
    Importa escalas a partir dos PDF nas pastas configuradas (PDF_FOLDER_ATUAL e PDF_FOLDER_SEGUINTE).
    Nome do ficheiro esperado: {equipa}_{ano}_{mês}.pdf (ex.: A_2026_3.pdf).
    Não apaga utilizadores existentes; cria ou atualiza por employee_number e adiciona turnos.
    Devolve quantas equipas foram processadas e um aviso se não forem as 5.
    """
    teams_processed = set()
    schedules_touched: set[tuple[int, int, int]] = set()  # (team_id, year, month)
    skipped_files: list[dict] = []

    print("Import: pedido recebido, a carregar cache (BD)...", flush=True)
    # Cache em memória para evitar milhares de queries à BD (acelera muito)
    teams_by_name = {t.nome: t for t in db.query(Team).all()}
    shift_types_by_code = {st.code: st for st in db.query(ShiftType).all()}
    users_by_emp = {}
    for u in db.query(User).all():
        k = (u.employee_number or "").strip()
        if k:
            users_by_emp[k] = u
    schedules_by_key = {(s.team_id, s.ano, s.mes): s for s in db.query(MonthlySchedule).all()}
    print("Import: cache OK, a verificar pastas...", flush=True)
    for folder in PDF_FOLDERS:
        print(f"  Pasta: {folder} -> existe? {os.path.exists(folder)}", flush=True)

    try:
        for folder in PDF_FOLDERS:
            if not os.path.exists(folder):
                continue

            for file in sorted(f for f in os.listdir(folder) if f.endswith(".pdf")):
                name = file.replace(".pdf", "")
                parts = name.split("_")

                if len(parts) != 3:
                    continue

                try:
                    team_code_raw, year_str, month_str = parts
                    if team_code_raw.upper().startswith("ROTA-"):
                        team_code = team_code_raw[5:].strip()
                    else:
                        team_code = team_code_raw.strip()
                    year = int(year_str)
                    month = int(month_str)
                except ValueError:
                    continue

                team = teams_by_name.get(team_code)
                if not team:
                    team = Team(nome=team_code)
                    db.add(team)
                    db.flush()
                    teams_by_name[team_code] = team

                pdf_path = os.path.join(folder, file)
                detected = detect_schedule_month_year_from_pdf(pdf_path)
                if detected is not None:
                    det_year, det_month = detected
                    if det_year != year or det_month != month:
                        msg = (
                            f"Nome do ficheiro indica {year}-{month:02d}, mas no PDF lê-se "
                            f"{det_year}-{det_month:02d}. Corrija o nome (ex.: {team_code}_{det_year}_{det_month}.pdf) "
                            "ou coloque o PDF certo na pasta."
                        )
                        print(f"Import: SKIP {file} — {msg}", flush=True)
                        skipped_files.append(
                            {
                                "file": file,
                                "folder": folder,
                                "filename_year": year,
                                "filename_month": month,
                                "pdf_year": det_year,
                                "pdf_month": det_month,
                                "message": msg,
                            }
                        )
                        continue
                print(f"Import: a processar {file} ...", flush=True)
                shifts = parse_pdf(pdf_path, year, month)
                print(f"Import: {file} -> {len(shifts)} turnos (a gravar)...", flush=True)

                schedule = schedules_by_key.get((team.id, year, month))
                if not schedule:
                    schedule = MonthlySchedule(mes=month, ano=year, team_id=team.id)
                    db.add(schedule)
                    db.flush()
                    schedules_by_key[(team.id, year, month)] = schedule
                schedules_touched.add((team.id, year, month))

                # Deduplicar por (user_id, data) dentro do próprio ficheiro.
                # O parser pode, em alguns PDFs, extrair duas células para o mesmo dia do mesmo utilizador.
                # Como a BD tem UNIQUE(user_id, data), isso causa IntegrityError no db.add_all().
                new_shifts_by_user_day: dict[tuple[int, date], Shift] = {}
                for s in shifts:
                    emp = (s["employee"] or "").strip()
                    if not emp:
                        continue
                    user = users_by_emp.get(emp)
                    if not user:
                        user = User(
                            nome=(s.get("name") or "").strip() or emp,
                            email=f"{emp}@atc.local",
                            employee_number=emp,
                            password_hash=hash_password("temp"),
                            team_id=team.id
                        )
                        db.add(user)
                        db.flush()
                        users_by_emp[emp] = user

                    shift_type = shift_types_by_code.get(s["code"])
                    bucket = s.get("color_bucket")
                    if bucket is None:
                        origin_status = "rota"
                    elif bucket == "gray_light":
                        origin_status = "troca_nav"
                    elif bucket == "gray_dark":
                        origin_status = "troca_servico"
                    elif bucket == "red":
                        origin_status = "bht"
                    elif bucket == "yellow":
                        origin_status = "ts"
                    elif bucket == "pink":
                        origin_status = "mudanca_funcoes"
                    elif bucket == "lime":
                        origin_status = "outros"
                    else:
                        origin_status = None

                    existing_shift = db.query(Shift).filter(
                        Shift.user_id == user.id,
                        Shift.data == s["date"]
                    ).first()
                    if existing_shift:
                        if _should_replace_existing_code(existing_shift.codigo, s["code"]):
                            existing_shift.codigo = s["code"]
                            existing_shift.color_bucket = bucket
                            existing_shift.origin_status = origin_status
                            existing_shift.shift_type_id = shift_type.id if shift_type else None
                        continue
                    key = (user.id, s["date"])
                    if key in new_shifts_by_user_day:
                        # Se o PDF extraiu duas entradas idênticas, mantemos apenas uma e atualizamos campos.
                        prev = new_shifts_by_user_day[key]
                        if _should_replace_existing_code(prev.codigo, s["code"]):
                            prev.codigo = s["code"]
                            prev.color_bucket = bucket
                            prev.origin_status = origin_status
                            prev.shift_type_id = shift_type.id if shift_type else None
                            prev.schedule_id = schedule.id
                    else:
                        new_shifts_by_user_day[key] = Shift(
                            data=s["date"],
                            codigo=s["code"],
                            color_bucket=bucket,
                            origin_status=origin_status,
                            shift_type_id=shift_type.id if shift_type else None,
                            user_id=user.id,
                            schedule_id=schedule.id,
                        )

                new_shifts = list(new_shifts_by_user_day.values())
                if new_shifts:
                    db.add_all(new_shifts)
                teams_processed.add(team_code)
                db.commit()
                print(f"Import: {file} -> gravados {len(new_shifts)} turnos novos", flush=True)

        # Após processar todos os ficheiros, verificar inconsistências
        for team_id, year, month in schedules_touched:
            schedule = db.query(MonthlySchedule).filter(
                MonthlySchedule.team_id == team_id,
                MonthlySchedule.ano == year,
                MonthlySchedule.mes == month,
            ).first()
            if schedule:
                _mark_inconsistencies_for_schedule(db, schedule)

        teams_list = sorted(teams_processed)
        warning = None
        if len(teams_processed) < len(EXPECTED_TEAMS):
            missing = EXPECTED_TEAMS - teams_processed
            warning = (
                f"Apenas {len(teams_processed)} de 5 equipas foram processadas. "
                f"Equipas em falta: {sorted(missing)}. "
                "Verifica os ficheiros nas pastas ou o formato dos nomes (ex.: A_2026_3.pdf)."
            )

        # Lista de escalas (equipa + mês) para mostrar ex.: 5 equipas × 2 meses = 10 escalas
        schedules_list = []
        for (tid, y, m) in schedules_touched:
            t = db.query(Team).filter(Team.id == tid).first()
            if t:
                schedules_list.append(f"{t.nome} {y}-{m:02d}")
        schedules_list.sort()

        return {
            "message": "Schedules imported",
            "teams_processed": teams_list,
            "teams_count": len(teams_processed),
            "schedules_count": len(schedules_touched),
            "schedules_processed": schedules_list,
            "warning": warning,
            "skipped_files": skipped_files,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-schedules")
def clear_all_schedules(
    body: ClearSchedulesBody,
    db: Session = Depends(get_db),
    x_clear_schedules_secret: str | None = Header(None, alias="X-Clear-Schedules-Secret"),
):
    """
    Remove **todas** as escalas importadas (`shifts` + `monthly_schedules`) e **todos** os dados
    de trocas/notificações/histórico ligados a turnos. Utilizadores e equipas não são apagados.

    - `confirm` no JSON deve ser exatamente a frase configurada em `CLEAR_SCHEDULES_CONFIRM_PHRASE`.
    - Se existir variável de ambiente `CLEAR_SCHEDULES_SECRET`, o mesmo valor deve ir no header
      `X-Clear-Schedules-Secret`.
    """
    secret = os.environ.get(CLEAR_SCHEDULES_SECRET_ENV, "").strip()
    if secret and (x_clear_schedules_secret or "").strip() != secret:
        raise HTTPException(
            status_code=403,
            detail="Operação protegida: defina o header X-Clear-Schedules-Secret ou contacte o administrador.",
        )

    if body.confirm.strip() != CLEAR_SCHEDULES_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=(
                f'Campo "confirm" deve ser exatamente: {CLEAR_SCHEDULES_CONFIRM_PHRASE!r} '
                "(respeite maiúsculas e underscores)."
            ),
        )

    try:
        stats = _clear_all_schedules_and_swap_data(db)
        return {
            "message": "Todas as escalas e dados de trocas associados foram apagados. Pode fazer um import limpo.",
            **stats,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))