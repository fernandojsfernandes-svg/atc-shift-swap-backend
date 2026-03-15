from fastapi import APIRouter, Depends, HTTPException, Security
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi.security import OAuth2PasswordRequestForm

from database import get_db
from models import User, Shift
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

    shifts = db.query(Shift).filter(
        Shift.user_id == user.id,
        Shift.data >= f"{year:04d}-{month:02d}-01",
        Shift.data < f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01",
    ).all()

    # Serializar enquanto a sessão está aberta (evita e3q8 / "not bound to a Session")
    return [ShiftRead.model_validate(s) for s in shifts]