import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from security import hash_password
from database import get_db
from models import User, Shift, ShiftType, MonthlySchedule, Team, SwapHistory
from parsers.pdf_parser import parse_pdf

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

            for file in os.listdir(folder):
                if not file.endswith(".pdf"):
                    continue

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

                new_shifts = []
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
                        existing_shift.codigo = s["code"]
                        existing_shift.color_bucket = bucket
                        existing_shift.origin_status = origin_status
                        continue

                    new_shifts.append(Shift(
                        data=s["date"],
                        codigo=s["code"],
                        color_bucket=bucket,
                        origin_status=origin_status,
                        shift_type_id=shift_type.id if shift_type else None,
                        user_id=user.id,
                        schedule_id=schedule.id
                    ))

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
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))