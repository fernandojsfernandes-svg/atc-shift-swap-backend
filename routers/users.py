import unicodedata
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Security
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi.security import OAuth2PasswordRequestForm

from database import get_db


def _normalize(s: str) -> str:
    """Remove acentos para pesquisa insensível (ex.: Mário -> mario)."""
    if not s:
        return ""
    n = unicodedata.normalize("NFD", s)
    return "".join(c for c in n if unicodedata.category(c) != "Mn").lower()
from models import User, Shift, Team
from services.swap_display import shift_ids_in_accepted_swaps, swap_partner_labels_for_user_shifts
from schemas.user import UserCreate, UserRead, UserPreferencesUpdate
from schemas.shift import ShiftRead

from security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    oauth2_scheme
)

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.post("/", response_model=UserRead)
def create_user(user: UserCreate, db: Session = Depends(get_db)):

    novo_user = User(
        nome=user.nome,
        email=user.email,
        employee_number=user.employee_number,
        password_hash=hash_password(user.password),
        team_id=user.team_id
    )

    db.add(novo_user)
    db.commit()
    db.refresh(novo_user)

    return novo_user


@router.get("/", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
):
    return db.query(User).all()


@router.get("/search", response_model=list[UserRead])
def search_users(
    q: str,
    limit: int = 15,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Procura utilizadores por nome ou número (autocomplete troca direta).
    Pesquisa insensível a acentos (ex.: "Mario" encontra "Mário Ribeiro").
    """
    term = (q or "").strip()
    if not term:
        return []
    norm_term = _normalize(term)
    users = db.query(User).order_by(User.nome).all()
    matches = []
    for u in users:
        nome = (u.nome or "").strip()
        emp = (u.employee_number or "").strip()
        if norm_term in _normalize(nome) or norm_term in _normalize(emp):
            matches.append(u)
        elif term.lower() in nome.lower() or term in emp:
            if u not in matches:
                matches.append(u)
    return matches[:limit]


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    return {"message": f"User {user_id} deleted successfully"}


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(User.email == form_data.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id)})

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserRead)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Perfil do utilizador autenticado (inclui preferência de notificações)."""
    return current_user


@router.patch("/me", response_model=UserRead)
def update_current_user_preferences(
    prefs: UserPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualizar preferências (ex.: desativar notificações de pedidos de troca)."""
    if prefs.notifications_enabled is not None:
        current_user.notifications_enabled = prefs.notifications_enabled
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/{employee_number}/shifts/{year}/{month}", response_model=list[ShiftRead])
def user_month_shifts(
    employee_number: str,
    year: int,
    month: int,
    db: Session = Depends(get_db),
):
    """
    Devolve todos os turnos (Shift) de um utilizador num determinado mês/ano.
    Inclui cor e flags de inconsistência para o frontend poder mostrar a bandeira vermelha.
    """
    emp = (employee_number or "").strip()
    if not emp:
        raise HTTPException(status_code=404, detail="User not found")
    # 1) Procurar por número (com trim na BD para equipas importadas com espaços)
    user = db.query(User).filter(func.trim(User.employee_number) == emp).first()
    # 2) Fallback: PDF com colunas trocadas (nome na 1.ª coluna, número na 2.ª) → employee_number=nome, nome=número
    if not user:
        user = db.query(User).filter(func.trim(User.nome) == emp).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    start = date_type(year, month, 1)
    end = date_type(year + 1, 1, 1) if month == 12 else date_type(year, month + 1, 1)
    shifts = db.query(Shift).filter(
        Shift.user_id == user.id,
        Shift.data >= start,
        Shift.data < end,
    ).all()

    shift_ids = [s.id for s in shifts]
    swapped_ids = shift_ids_in_accepted_swaps(db, shift_ids)
    partner_labels = swap_partner_labels_for_user_shifts(db, user.id, shift_ids)

    # Serializar enquanto a sessão está aberta (evita e3q8 / "not bound to a Session")
    return [
        ShiftRead(
            id=s.id,
            user_id=s.user_id,
            schedule_id=s.schedule_id,
            data=s.data,
            codigo=s.codigo,
            color_bucket=s.color_bucket,
            inconsistency_flag=s.inconsistency_flag,
            inconsistency_message=s.inconsistency_message,
            origin_status=s.origin_status,
            show_troca_bht=(s.origin_status == "bht" and s.id in swapped_ids),
            show_troca_ts=(s.origin_status == "ts" and s.id in swapped_ids),
            swap_partner_name=partner_labels.get(s.id, (None, None))[0],
            swap_partner_employee_number=partner_labels.get(s.id, (None, None))[1],
        )
        for s in shifts
    ]