import os
from parsers.pdf_parser import parse_pdf
from database import SessionLocal
from models import User, Shift, ShiftType, MonthlySchedule, Team

PDF_FOLDERS = [
    "C:/PARSER_ESCALAS/PDF_Escalas/atual",
    "C:/PARSER_ESCALAS/PDF_Escalas/seguinte"
]

db = SessionLocal()

db.query(Shift).delete()
db.query(MonthlySchedule).delete()
db.query(User).delete()
db.commit()

for folder in PDF_FOLDERS:

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

        users = {}

        for s in shifts:
            users[s["employee"]] = s["name"]

        for employee, name in users.items():

            existing = db.query(User).filter(
                User.employee_number == employee
            ).first()

            if not existing:

                new_user = User(
                    nome=name,
                    email=f"{employee}@atc.local",
                    employee_number=employee,
                    password_hash="temp",
                    team_id=team.id
                )

                db.add(new_user)

        db.commit()

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

        for s in shifts:

            user = db.query(User).filter(
                User.employee_number == s["employee"]
            ).first()

            shift_type = db.query(ShiftType).filter(
                ShiftType.code == s["code"]
            ).first()

            new_shift = Shift(
                data=s["date"],
                codigo=s["code"],
                shift_type_id=shift_type.id,
                user_id=user.id,
                schedule_id=schedule.id
            )

            db.add(new_shift)

        db.commit()

print("Import completo")