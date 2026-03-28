from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Shift, User, ShiftType, Team, SwapRequest
from models import SwapStatus
from services.swap_display import (
    shift_ids_in_accepted_swaps,
    single_shift_involved_in_accepted_swap,
    swap_partner_labels_for_user_shifts,
)
from rules.manual_shift import (
    VALID_COLOR_BUCKETS,
    VALID_ORIGIN_STATUS,
    resolve_manual_shift_fields,
)
from schemas.shift import ShiftCreate, ShiftManualUpdate, ShiftRead
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
    # Turnos que foram trocados (aceites): oferecido ou recebido noutra escala
    shift_ids = [s.id for s, _, _ in shifts]
    swapped_ids = shift_ids_in_accepted_swaps(db, shift_ids)
    return [
        {
            "employee_number": u.employee_number,
            "nome": u.nome,
            "team": t.nome if t else None,
            "origin_status": s.origin_status,
            "show_troca_bht": s.origin_status == "bht" and s.id in swapped_ids,
            "show_troca_ts": s.origin_status == "ts" and s.id in swapped_ids,
        }
        for s, u, t in shifts
    ]


@router.patch("/{shift_id}", response_model=ShiftRead)
def patch_shift_manual(
    shift_id: int,
    body: ShiftManualUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Edição manual de um turno (correção de import ou erro):
    só o dono do turno; bloqueado se existir pedido de troca OPEN para esse shift.
    """
    shift = db.get(Shift, shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Turno não encontrado.")
    if shift.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só pode editar turnos da sua escala.")

    pending_swap = (
        db.query(SwapRequest)
        .filter(
            SwapRequest.shift_id == shift_id,
            SwapRequest.status.in_([SwapStatus.OPEN, SwapStatus.PROPOSED]),
        )
        .first()
    )
    if pending_swap:
        raise HTTPException(
            status_code=400,
            detail="Existe um pedido de troca em curso para este dia. Cancele ou conclua-o antes de corrigir o turno.",
        )

    if body.color_bucket is not None:
        cb = body.color_bucket.strip()
        if cb not in VALID_COLOR_BUCKETS:
            raise HTTPException(
                status_code=400,
                detail=f"color_bucket inválido. Use: {', '.join(sorted(VALID_COLOR_BUCKETS))}.",
            )
        body_color = cb
    else:
        body_color = None

    if body.origin_status is not None:
        os_norm = body.origin_status.strip()
        if os_norm not in VALID_ORIGIN_STATUS:
            raise HTTPException(
                status_code=400,
                detail="origin_status inválido.",
            )
        body_origin = os_norm
    else:
        body_origin = None

    codigo = body.codigo.strip()
    color_bucket, origin_status = resolve_manual_shift_fields(
        codigo, body_color, body_origin
    )

    st = db.query(ShiftType).filter(ShiftType.code == codigo).first()
    shift_type_id = st.id if st else None

    shift.codigo = codigo
    shift.color_bucket = color_bucket
    shift.origin_status = origin_status
    shift.shift_type_id = shift_type_id
    shift.inconsistency_flag = False
    shift.inconsistency_message = None

    db.commit()
    db.refresh(shift)

    in_swapped = single_shift_involved_in_accepted_swap(db, shift.id)
    pl = swap_partner_labels_for_user_shifts(db, current_user.id, [shift.id]).get(shift.id, (None, None))

    return ShiftRead(
        id=shift.id,
        user_id=shift.user_id,
        schedule_id=shift.schedule_id,
        data=shift.data,
        codigo=shift.codigo,
        color_bucket=shift.color_bucket,
        inconsistency_flag=shift.inconsistency_flag,
        inconsistency_message=shift.inconsistency_message,
        origin_status=shift.origin_status,
        show_troca_bht=(shift.origin_status == "bht" and in_swapped),
        show_troca_ts=(shift.origin_status == "ts" and in_swapped),
        swap_partner_name=pl[0],
        swap_partner_employee_number=pl[1],
    )