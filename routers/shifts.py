from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Shift, User, ShiftType, Team, SwapRequest
from models import SwapStatus
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

    shift_type_id = None
    if shift.codigo:
        st = db.query(ShiftType).filter(ShiftType.code == shift.codigo.strip()).first()
        if st:
            shift_type_id = st.id

    new_shift = Shift(
        data=shift.data,
        codigo=shift.codigo,
        user_id=shift.user_id,
        schedule_id=shift.schedule_id,
        shift_type_id=shift_type_id,
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


@router.get("/on-duty")
def who_is_on_duty(
    date_q: date,
    code: str,
    db: Session = Depends(get_db),
):
    """
    Lista quem está de serviço num dado dia e turno (todas as equipas).
    Ex.: GET /shifts/on-duty?date_q=2026-03-05&code=M
    """
    code_clean = (code or "").strip()
    if not code_clean:
        return []
    # Comparação exata: Mt e MT são turnos diferentes
    shifts = (
        db.query(Shift, User, Team)
        .join(User, Shift.user_id == User.id)
        .outerjoin(Team, User.team_id == Team.id)
        .filter(Shift.data == date_q, Shift.codigo == code_clean)
        .all()
    )
    # Turnos que foram trocados (aceites): mostrar "TROCA BHT" só quando BHT foi obtido por troca
    shift_ids = [s.id for s, _, _ in shifts]
    accepted_swap_shift_ids = set(
        r.shift_id for r in db.query(SwapRequest.shift_id).filter(
            SwapRequest.shift_id.in_(shift_ids),
            SwapRequest.status == SwapStatus.ACCEPTED,
        ).all()
    )
    return [
        {
            "employee_number": u.employee_number,
            "nome": u.nome,
            "team": t.nome if t else None,
            "origin_status": s.origin_status,
            "show_troca_bht": s.origin_status == "bht" and s.id in accepted_swap_shift_ids,
        }
        for s, u, t in shifts
    ]