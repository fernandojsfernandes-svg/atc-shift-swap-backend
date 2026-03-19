from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from security import hash_password
from database import get_db
from models import (
    Team,
    User,
    MonthlySchedule,
    Shift,
    SwapRequest,
    SwapHistory,
    SwapNotification,
    SwapActionHistory,
    SwapActionDismissal,
    SwapPreference,
    SwapWantedOption,
    CycleProposal,
    CycleSwap,
    CycleConfirmation,
    SwapDirectTarget,
)

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


@router.post("/seed-demo-users")
def seed_demo_users(db: Session = Depends(get_db)):
    """
    Prepara TODOS os utilizadores existentes (com número de funcionário) para login de testes em local.

    - Remove utilizadores "dummy" antigos (employee_number a começar por 'DEMO-')
    - Para cada utilizador real:
      - Email: <número>@demo.local (ex.: 404527@demo.local)
      - Password: "test"
    - Na app:
      - Login: <número>@demo.local
      - Nº funcionário: <número> (ex.: 404527)
    """
    updated: list[dict] = []

    # 1) Apagar dummies antigos (se existirem)
    dummy_users = db.query(User).filter(User.employee_number.like("DEMO-%")).all()
    if dummy_users:
        dummy_ids = [u.id for u in dummy_users]
        # apagar eventuais shifts associados a esses dummies, por segurança
        db.query(Shift).filter(Shift.user_id.in_(dummy_ids)).delete(synchronize_session=False)
        for u in dummy_users:
            db.delete(u)
        db.flush()

    # 2) Atualizar todos os utilizadores reais com email/password de demo
    pwd_hash = hash_password("test")
    real_users = db.query(User).all()
    for u in real_users:
        emp = (u.employee_number or "").strip()
        if not emp:
            continue
        u.email = f"{emp}@demo.local"
        u.password_hash = pwd_hash
        updated.append(
            {
                "id": u.id,
                "nome": u.nome,
                "email": u.email,
                "employee_number": u.employee_number,
                "password": "test",
            }
        )

    db.commit()
    return {
        "updated": updated,
        "total_updated": len(updated),
        "hint": "Login: <número>@demo.local (ex.: 404527@demo.local). Nº funcionário: o mesmo número (404527).",
    }


@router.post("/clear-swaps")
def clear_swaps(db: Session = Depends(get_db)):
    """
    Apaga todos os pedidos de troca e notificações associados (para começar testes de troca com a base limpa).
    Não mexe em utilizadores nem em turnos.
    """
    # apagar confirmações / ciclos primeiro (dependem de SwapRequest)
    db.query(CycleConfirmation).delete(synchronize_session=False)
    db.query(CycleSwap).delete(synchronize_session=False)
    db.query(CycleProposal).delete(synchronize_session=False)

    # apagar históricos e notificações
    db.query(SwapHistory).delete(synchronize_session=False)
    db.query(SwapActionDismissal).delete(synchronize_session=False)
    db.query(SwapActionHistory).delete(synchronize_session=False)
    db.query(SwapNotification).delete(synchronize_session=False)

    # apagar preferências, opções e destinatários diretos
    db.query(SwapPreference).delete(synchronize_session=False)
    db.query(SwapWantedOption).delete(synchronize_session=False)
    db.query(SwapDirectTarget).delete(synchronize_session=False)

    # finalmente, apagar os pedidos de troca
    db.query(SwapRequest).delete(synchronize_session=False)

    db.commit()
    return {"message": "Todos os pedidos de troca e notificações foram apagados."}