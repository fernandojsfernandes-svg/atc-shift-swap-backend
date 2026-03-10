import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from security import hash_password
from database import get_db
from models import User, Shift, ShiftType, MonthlySchedule, Team
from parsers.pdf_parser import parse_pdf

router = APIRouter(
    prefix="/import",
    tags=["Import"]
)

PDF_FOLDERS = [
    "C:/PARSER_ESCALAS/PDF_Escalas/atual",
    "C:/PARSER_ESCALAS/PDF_Escalas/seguinte"
]


@router.post("/schedules")
def import_schedules(db: Session = Depends(get_db)):

    db.query(User).delete()
    db.commit()


    try:

        print("IMPORT STARTED")

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

                team_code, year, month = parts

                year = int(year)
                month = int(month)

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

                        existing_shift = db.query(Shift).filter(
                            Shift.user_id == user.id,
                            Shift.data == s["date"]
                        ).first()

                        if existing_shift:
                            continue

                        shift = Shift(
                            data=s["date"],
                            codigo=s["code"],
                            shift_type_id=shift_type.id,
                            user_id=user.id,
                            schedule_id=schedule.id
                        )

                        db.add(shift)

                db.commit()

        return {"message": "Schedules imported"}

    except Exception as e:
        print("IMPORT ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))