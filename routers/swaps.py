from fastapi import APIRouter, Depends, HTTPException, Security, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta
from database import get_db
from models import SwapRequest, Shift, SwapStatus, User, ShiftType, SwapPreference
from schemas.swap import SwapCreate, SwapRead
from security import get_current_user, oauth2_scheme
from rules.shift_rules import is_next_day_incompatible, exceeds_max_consecutive_days

router = APIRouter(
    prefix="/swap-requests",
    tags=["Swap Requests"]
)

# 🔹 CREATE SWAP (SEGURA)
@router.post("/", response_model=SwapRead)
def create_swap_request(
    swap: SwapCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()
    from datetime import date

    if shift.data < date.today():
        raise HTTPException(
        status_code=400,
        detail="Cannot create swap for past shifts"
    )

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    # Só pode pedir swap do próprio turno
    if shift.user_id != current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You can only request swap for your own shift"
        )

    # Já foi aceite?
    existing_accepted = db.query(SwapRequest).filter(
        SwapRequest.shift_id == swap.shift_id,
        SwapRequest.status == SwapStatus.ACCEPTED
    ).first()

    if existing_accepted:
        raise HTTPException(
            status_code=400,
            detail="This shift has already been swapped"
        )

    # Já existe OPEN?
    existing_open = db.query(SwapRequest).filter(
    SwapRequest.shift_id == swap.shift_id,
    SwapRequest.status == SwapStatus.OPEN
).first()

    if existing_open:
        raise HTTPException(
            status_code=400,
            detail="There is already an open swap request for this shift"
        )

    new_swap = SwapRequest(
        shift_id=swap.shift_id,
        requester_id=current_user.id,
        status=SwapStatus.OPEN
    )

    db.add(new_swap)
    db.commit()
    db.refresh(new_swap)

    return new_swap


# 🔹 ACCEPT SWAP
@router.post("/{swap_id}/accept")
def accept_swap(
    swap_id: int,
    confirm_incompatibility: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    swap = db.query(SwapRequest).filter(SwapRequest.id == swap_id).first()

    if not swap:
        raise HTTPException(status_code=404, detail="Swap request not found")

    if swap.status != SwapStatus.OPEN:
        raise HTTPException(status_code=400, detail="Swap already processed")

    if swap.requester_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot accept your own swap"
        )

    original_shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()

    if not original_shift:
        raise HTTPException(status_code=404, detail="Original shift not found")

    existing = db.query(SwapRequest).filter(
        SwapRequest.shift_id == original_shift.id,
        SwapRequest.status == SwapStatus.ACCEPTED
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Shift already swapped")
    accepter_shift = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.data == original_shift.data
    ).first()

    if not accepter_shift:
        raise HTTPException(
            status_code=400,
            detail="You do not have a shift on this date"
        )

    next_day = original_shift.data + timedelta(days=1)

    next_shift = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.data == next_day
    ).first()

    if next_shift:

        today_code = accepter_shift.codigo
        tomorrow_code = next_shift.codigo

        if is_next_day_incompatible(today_code, tomorrow_code):

            if not confirm_incompatibility:
                raise HTTPException(
                    status_code=409,
                    detail="Possible incompatibility with next day shift (T→N or Mt→N). Use confirm_incompatibility=true if you want to proceed."
                )

    # Verificar preferências de turno
    preferences = db.query(SwapPreference).filter(
        SwapPreference.swap_request_id == swap.id
    ).all()

    if preferences:
        allowed_types = [p.shift_type_id for p in preferences]

        if accepter_shift.shift_type_id not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Your shift type is not accepted for this swap"
            )

    try:

        original_user = original_shift.user_id
        temp_user_id = -1

        original_shift.user_id = temp_user_id
        db.flush()

        accepter_shift.user_id = original_user
        db.flush()

        original_shift.user_id = current_user.id
        db.flush()

                # verificar 9 dias consecutivos
        user_shifts = db.query(Shift).filter(
            Shift.user_id == current_user.id
        ).all()

        # incluir o turno recebido no swap
        user_shifts.append(original_shift)

        if exceeds_max_consecutive_days(user_shifts):
            raise HTTPException(
                status_code=400,
                detail="Swap would exceed 9 consecutive working days"
            )

        swap.accepter_id = current_user.id
        swap.status = SwapStatus.ACCEPTED

        db.query(SwapRequest).filter(
            SwapRequest.shift_id == original_shift.id,
            SwapRequest.id != swap.id,
            SwapRequest.status == SwapStatus.OPEN
        ).update({"status": SwapStatus.REJECTED})

        db.commit()

    except:
        db.rollback()
        raise HTTPException(status_code=500, detail="Swap transaction failed")

    return {"message": "Swap completed successfully"}

@router.get("/open", response_model=list[SwapRead])
def list_open_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    swaps = db.query(SwapRequest).filter(
        SwapRequest.status == SwapStatus.OPEN,
        SwapRequest.requester_id != current_user.id
    ).all()

    return swaps

@router.get("/matching", response_model=list[SwapRead])
def matching_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    my_shifts = db.query(Shift).filter(
        Shift.user_id == current_user.id
    ).all()

    my_shifts_by_date = {s.data: s for s in my_shifts}

    open_swaps = db.query(SwapRequest).filter(
        SwapRequest.status == SwapStatus.OPEN
    ).all()

    result = []

    for swap in open_swaps:

        if swap.requester_id == current_user.id:
            continue

        original_shift = db.query(Shift).filter(
            Shift.id == swap.shift_id
        ).first()

        if not original_shift:
            continue

        my_shift = my_shifts_by_date.get(original_shift.data)

        if not my_shift:
            continue

        preferences = db.query(SwapPreference).filter(
            SwapPreference.swap_request_id == swap.id
        ).all()

        # sem preferências → qualquer turno
        if not preferences:
            result.append(swap)
            continue

        allowed_types = [p.shift_type_id for p in preferences]

        if my_shift.shift_type_id in allowed_types:
            result.append(swap)

    return result

@router.get("/suggestions")
def swap_suggestions(
    db: Session = Depends(get_db)
):

    swaps = db.query(SwapRequest).filter(
        SwapRequest.status == SwapStatus.OPEN
    ).all()

    # carregar todos os shifts apenas uma vez
    all_shifts = db.query(Shift).all()
    shifts = {s.id: s for s in all_shifts}

    suggestions = []

    for swap_a in swaps:

        shift_a = shifts.get(swap_a.shift_id)

        if not shift_a:
            continue

        for swap_b in swaps:

            if swap_b.id <= swap_a.id:
                continue

            if swap_a.requester_id == swap_b.requester_id:
                continue

            shift_b = shifts.get(swap_b.shift_id)

            if not shift_b:
                continue

            if shift_a.data != shift_b.data:
                continue

            if shift_a.codigo == shift_b.codigo:
                continue

            suggestions.append({
                "swap_a": swap_a.id,
                "swap_b": swap_b.id,
                "date": str(shift_a.data),
                "shift_a": shift_a.codigo,
                "shift_b": shift_b.codigo,
                "message": "Possible swap detected"
            })

    return suggestions
@router.get("/cycles")
def find_swap_cycles(
    db: Session = Depends(get_db)
):

    try:

        swaps = db.query(SwapRequest).filter(
            SwapRequest.status == SwapStatus.OPEN
        ).all()

        shifts = db.query(Shift).all()
        shifts_by_id = {s.id: s for s in shifts}

        cycles = []

        for swap_a in swaps:

            shift_a = shifts_by_id.get(swap_a.shift_id)
            if not shift_a:
                continue

            for swap_b in swaps:

                if swap_b.id == swap_a.id:
                    continue

                shift_b = shifts_by_id.get(swap_b.shift_id)
                if not shift_b:
                    continue

                if shift_a.data != shift_b.data:
                    continue

                if shift_a.codigo == shift_b.codigo:
                    continue

                for swap_c in swaps:

                    if swap_c.id in [swap_a.id, swap_b.id]:
                        continue

                    shift_c = shifts_by_id.get(swap_c.shift_id)
                    if not shift_c:
                        continue

                    if shift_b.data != shift_c.data:
                        continue

                    if shift_c.codigo == shift_a.codigo:
                        continue

                    if shift_c.data != shift_a.data:
                        continue

                    cycles.append({
                        "cycle": [swap_a.id, swap_b.id, swap_c.id],
                        "date": str(shift_a.data),
                        "message": "3-way swap possible"
                    })

        return {"cycles": cycles}

    except Exception as e:
        return {"error": str(e)}
@router.get("/possible")
def possible_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    allowed_codes = ["M", "T", "N", "MG", "Mt", "DC", "DS"]

    my_shifts = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.codigo.in_(allowed_codes)
    ).all()

    results = []

    for my_shift in my_shifts:

        other_shifts = db.query(Shift).filter(
            Shift.data == my_shift.data,
            Shift.user_id != current_user.id,
            Shift.codigo.in_(allowed_codes)
        ).all()

        for other in other_shifts:

            if other.codigo == my_shift.codigo:
                continue

            other_user = db.query(User).filter(
                User.id == other.user_id
            ).first()

            results.append({
                "date": my_shift.data,
                "my_shift": my_shift.codigo,
                "other_shift": other.codigo,
                "other_user_id": other.user_id,
                "other_user_name": other_user.nome
            })

    return results
@router.get("/possible")
def possible_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    allowed_codes = ["M", "T", "N", "MG", "Mt", "DC", "DS"]

    my_shifts = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.codigo.in_(allowed_codes)
    ).all()

    results = []

    for my_shift in my_shifts:

        other_shifts = db.query(Shift).filter(
            Shift.data == my_shift.data,
            Shift.user_id != current_user.id,
            Shift.codigo.in_(allowed_codes)
        ).all()

        for other in other_shifts:

            if other.codigo == my_shift.codigo:
                continue

            other_user = db.query(User).filter(
                User.id == other.user_id
            ).first()

            results.append({
                "date": my_shift.data,
                "my_shift": my_shift.codigo,
                "other_shift": other.codigo,
                "other_user_id": other.user_id,
                "TEST": "HELLO"
            })

    return results