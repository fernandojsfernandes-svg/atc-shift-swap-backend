from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import MonthlySchedule, Team, Shift, User
from schemas.schedule import ScheduleCreate, ScheduleRead
from schemas.shift import ShiftRead

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


@router.get("/{team_code}/{year}/{month}", response_model=list[ShiftRead])
def team_month_schedule(
    team_code: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    """
    Devolve a escala completa de uma equipa num determinado mês/ano.
    Cada item é um turno (Shift) com informação do utilizador, cor e flags.
    """
    team = db.query(Team).filter(Team.nome == team_code).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    schedule = db.query(MonthlySchedule).filter(
        MonthlySchedule.team_id == team.id,
        MonthlySchedule.ano == year,
        MonthlySchedule.mes == month,
    ).first()
    if not schedule:
        return []

    shifts = db.query(Shift).filter(Shift.schedule_id == schedule.id).all()
    return shifts