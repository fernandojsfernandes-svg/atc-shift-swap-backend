from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from security import hash_password
from database import get_db
from models import Team, User, MonthlySchedule, Shift

router = APIRouter(
    prefix="/dev",
    tags=["Development"]
)


@router.get("/user-lookup/{number}")
def user_lookup(number: str, db: Session = Depends(get_db)):
    """
    Diagnóstico: lista utilizadores que coincidem com o número (por employee_number ou nome).
    Mostra quantos turnos têm em Março e Abril 2026.
    """
    num = (number or "").strip()
    if not num:
        return {"users": [], "message": "Número vazio."}
    # Utilizadores com employee_number ou nome = num (com trim)
    users = (
        db.query(User)
        .filter(
            (func.trim(User.employee_number) == num) | (func.trim(User.nome) == num)
        )
        .all()
    )
    team_names = {}
    result = []
    for u in users:
        team = db.query(Team).filter(Team.id == u.team_id).first() if u.team_id else None
        team_name = team.nome if team else None
        shifts_mar = db.query(Shift).filter(
            Shift.user_id == u.id,
            Shift.data >= date(2026, 3, 1),
            Shift.data < date(2026, 4, 1),
        ).count()
        shifts_abr = db.query(Shift).filter(
            Shift.user_id == u.id,
            Shift.data >= date(2026, 4, 1),
            Shift.data < date(2026, 5, 1),
        ).count()
        result.append({
            "id": u.id,
            "employee_number": u.employee_number,
            "nome": u.nome,
            "team": team_name,
            "shifts_marco_2026": shifts_mar,
            "shifts_abril_2026": shifts_abr,
        })
    return {"number_searched": num, "users": result}


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