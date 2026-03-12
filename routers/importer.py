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
                    team_code, year_str, month_str = parts
                    year = int(year_str)
                    month = int(month_str)
                except ValueError:
                    continue

                team = db.query(Team).filter(Team.nome == team_code).first()
                if not team:
                    team = Team(nome=team_code)
                    db.add(team)
                    db.commit()
                    db.refresh(team)

                pdf_path = os.path.join(folder, file)
                shifts = parse_pdf(pdf_path, year, month)

                for s in shifts:
                    user = db.query(User).filter(
                        User.employee_number == s["employee"]
                    ).first()

                    if not user:
                        user = User(
                            nome=s["name"],
                            email=f"{s['employee']}@atc.local",
                            employee_number=s["employee"],
                            password_hash=hash_password("temp"),
                            team_id=team.id
                        )
                        db.add(user)
                        db.commit()
                        db.refresh(user)

                    shift_type = db.query(ShiftType).filter(
                        ShiftType.code == s["code"]
                    ).first()

                    schedule = db.query(MonthlySchedule).filter(
                        MonthlySchedule.mes == month,
                        MonthlySchedule.ano == year,
                        MonthlySchedule.team_id == team.id
                    ).first()

                    if not schedule:
                        schedule = MonthlySchedule(
                            mes=month,
                            ano=year,
                            team_id=team.id
                        )
                        db.add(schedule)
                        db.commit()
                        db.refresh(schedule)

                    # Registar schedule tocado (para posterior verificação de inconsistências)
                    schedules_touched.add((team.id, year, month))

                    existing_shift = db.query(Shift).filter(
                        Shift.user_id == user.id,
                        Shift.data == s["date"]
                    ).first()

                    if existing_shift:
                        continue

                    shift = Shift(
                        data=s["date"],
                        codigo=s["code"],
                        color_bucket=s.get("color_bucket"),
                        shift_type_id=shift_type.id if shift_type else None,
                        user_id=user.id,
                        schedule_id=schedule.id
                    )
                    db.add(shift)

                teams_processed.add(team_code)
                db.commit()

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

        return {
            "message": "Schedules imported",
            "teams_processed": teams_list,
            "teams_count": len(teams_processed),
            "warning": warning,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))