from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from security import hash_password
from database import get_db
from models import Team, User, MonthlySchedule, Shift

router = APIRouter(
    prefix="/dev",
    tags=["Development"]
)


@router.post("/seed-data")
def seed_data(db: Session = Depends(get_db)):

    # Team
    team = Team(nome="Test Team")
    db.add(team)
    db.flush()

    # Users
    user1 = User(
    nome="ATCO 1",
    email="atco1@test.com",
    password_hash=hash_password("test"),
    employee_number="1001",
    team_id=team.id
)

    user2 = User(
    nome="ATCO 2",
    email="atco2@test.com",
    password_hash=hash_password("test"),
    employee_number="1002",
    team_id=team.id
)
    db.add_all([user1, user2])
    db.flush()

    # Schedule
    schedule = MonthlySchedule(
        mes=3,
        ano=2026,
        team_id=team.id
    )

    db.add(schedule)
    db.flush()

    # Shifts
    shift1 = Shift(
        data=date(2026, 3, 10),
        codigo="N",
        user_id=user1.id,
        schedule_id=schedule.id
    )

    shift2 = Shift(
        data=date(2026, 3, 10),
        codigo="M",
        user_id=user2.id,
        schedule_id=schedule.id
    )

    db.add_all([shift1, shift2])

    db.commit()

    return {
        "message": "Test data created"
    }