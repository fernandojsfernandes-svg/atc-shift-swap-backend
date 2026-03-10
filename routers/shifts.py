from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Shift, User
from schemas.shift import ShiftRead, ShiftCreate
from security import get_current_user

router = APIRouter(
    prefix="/shifts",
    tags=["Shifts"]
)


# listar todos os shifts (admin/debug)
@router.get("/", response_model=list[ShiftRead])
def list_shifts(db: Session = Depends(get_db)):
    return db.query(Shift).all()


# turnos do utilizador autenticado
@router.get("/my", response_model=list[ShiftRead])
def my_shifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Shift).filter(
        Shift.user_id == current_user.id
    ).all()

@router.post("/", response_model=ShiftRead)
def create_shift(shift: ShiftCreate, db: Session = Depends(get_db)):

    new_shift = Shift(
        data=shift.data,
        codigo=shift.codigo,
        user_id=shift.user_id,
        schedule_id=shift.schedule_id
    )

    db.add(new_shift)
    db.commit()
    db.refresh(new_shift)

    return new_shift
@router.get("/user/{user_id}")
def get_user_shifts(
    user_id: int,
    db: Session = Depends(get_db)
):

    shifts = db.query(Shift).filter(
        Shift.user_id == user_id
    ).order_by(Shift.data).all()

    return shifts
@router.get("/me")
def my_shifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    shifts = db.query(Shift).filter(
        Shift.user_id == current_user.id
    ).order_by(Shift.data).all()

    return shifts
@router.get("/me/tradable")
def my_tradable_shifts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    allowed_codes = ["M", "T", "N", "MG", "Mt", "DC", "DS"]

    shifts = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.codigo.in_(allowed_codes)
    ).order_by(Shift.data).all()

    return shifts