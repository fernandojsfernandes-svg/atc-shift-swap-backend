from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import MonthlySchedule, Shift, User, ShiftType
from schemas.schedule import ScheduleCreate, ScheduleRead

from parsers.schedule_parser import parse_schedule_pdf
from parsers.pdf_parser import parse_pdf

router = APIRouter(
    prefix="/schedules",
    tags=["Schedules"]
)


@router.post("/", response_model=ScheduleRead)
def create_schedule(schedule: ScheduleCreate, db: Session = Depends(get_db)):

    new_schedule = MonthlySchedule(
        ano=schedule.ano,
        mes=schedule.mes,
        team_id=schedule.team_id
    )

    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)

    return new_schedule


@router.get("/", response_model=list[ScheduleRead])
def list_schedules(db: Session = Depends(get_db)):
    return db.query(MonthlySchedule).all()

@router.post("/import-pdf")
def import_pdf(db: Session = Depends(get_db)):

    created = 0
    skipped = 0

    shifts = parse_pdf()

    for s in shifts:

        user = db.query(User).filter(
            User.employee_number == s["employee"]
        ).first()

        if not user:
            user = User(
                nome=s["name"],
                email=f"{s['employee']}@import.local",
                employee_number=s["employee"],
                password_hash="imported",
                team_id=1
            )

            db.add(user)
            db.flush()

        shift_type = db.query(ShiftType).filter(
            ShiftType.code == s["code"]
        ).first()

        shift = Shift(
            user_id=user.id,
            data=s["date"],
            codigo=s["code"],
            shift_type_id=shift_type.id if shift_type else None,
            schedule_id=1
        )

        db.add(shift)
        created += 1

    db.commit()

    return {
        "created_shifts": created,
        "skipped": skipped
    }