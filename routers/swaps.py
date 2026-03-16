from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session, joinedload
from datetime import date, datetime, time, timedelta

from database import get_db
from models import (
    SwapRequest,
    Shift,
    SwapStatus,
    User,
    ShiftType,
    SwapPreference,
    SwapWantedOption,
    SwapHistory,
    SwapNotification,
    CycleProposal,
    CycleSwap,
    CycleConfirmation,
    SwapDirectTarget,
)
from services.notify_swap import notify_matching_users_same_day
from schemas.swap import SwapCreate, SwapRead, SwapHistoryRead
from security import get_current_user
from rules.shift_rules import is_next_day_incompatible, exceeds_max_consecutive_days
from services.swap_engine import detect_swap_cycles

router = APIRouter(
    prefix="/swap-requests",
    tags=["Swap Requests"]
)


def _validate_cycle_execution(db: Session, shifts: list, users: list) -> None:
    """
    Validates that executing the cycle would not break operational rules.
    Raises HTTPException if invalid (same-day double shift; T or Mt followed by N next day; or >9 consecutive working days).
    """
    n = len(shifts)
    if n != len(users):
        raise HTTPException(status_code=400, detail="Invalid cycle data")

    # Load all current shifts for each user in the cycle
    user_shifts_map = {}
    for uid in users:
        user_shifts_map[uid] = db.query(Shift).filter(Shift.user_id == uid).all()

    # After cycle: user at index k gives shifts[k], receives shifts[(k+1) % n]
    for k in range(n):
        uid = users[k]
        give_away = shifts[k]
        receive = shifts[(k + 1) % n]
        resulting = [s for s in user_shifts_map[uid] if s.id != give_away.id] + [receive]

        # 1) No two shifts on same day
        by_date = {}
        for s in resulting:
            by_date.setdefault(s.data, []).append(s)
        for d, shs in by_date.items():
            if len(shs) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cycle would give user {uid} more than one shift on the same day"
                )

        # 2) Only T and Mt cannot have N the next day
        resulting_sorted = sorted(resulting, key=lambda s: s.data)
        for i in range(len(resulting_sorted) - 1):
            today_s = resulting_sorted[i]
            next_s = resulting_sorted[i + 1]
            if (next_s.data - today_s.data).days != 1:
                continue
            if is_next_day_incompatible(today_s.codigo, next_s.codigo):
                raise HTTPException(
                    status_code=400,
                    detail="Cycle would create forbidden sequence: only T and Mt cannot have N the next day"
                )

        # 3) Max 9 consecutive working days
        if exceeds_max_consecutive_days(resulting):
            raise HTTPException(
                status_code=400,
                detail="Cycle would exceed 9 consecutive working days for one or more users"
            )


# 🔹 CREATE SWAP (SEGURA)
@router.post("/", response_model=SwapRead)
def create_swap_request(
    swap: SwapCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only create a swap for your own shift")

    from datetime import date

    if shift.data < date.today():
        raise HTTPException(
            status_code=400,
            detail="Cannot create swap for past shifts"
        )

    # verificar se turno já está numa proposta de ciclo
    existing_cycle = db.query(CycleSwap).join(
        SwapRequest, CycleSwap.swap_id == SwapRequest.id
    ).join(
        CycleProposal, CycleSwap.cycle_id == CycleProposal.id
    ).filter(
        SwapRequest.shift_id == swap.shift_id,
        CycleProposal.status == "PROPOSED"
    ).first()

    if existing_cycle:
        raise HTTPException(
            status_code=400,
            detail="This shift is already part of a pending cycle proposal"
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
    db.flush()  # need new_swap.id for preferences / direct targets

    if swap.acceptable_shift_types:
        for code in swap.acceptable_shift_types:
            shift_type = db.query(ShiftType).filter(ShiftType.code == code.strip()).first()
            if shift_type:
                db.add(SwapPreference(
                    swap_request_id=new_swap.id,
                    shift_type_id=shift_type.id
                ))

    # gravar opções de dias/tipos desejados, se existirem
    if swap.wanted_options:
        for opt in swap.wanted_options:
            for code in opt.shift_types:
                shift_type = db.query(ShiftType).filter(ShiftType.code == code.strip()).first()
                if not shift_type:
                    continue
                db.add(SwapWantedOption(
                    swap_request_id=new_swap.id,
                    date=opt.date,
                    shift_type_id=shift_type.id
                ))

    # alvos diretos (troca direta)
    if swap.direct_target_ids:
        for uid in swap.direct_target_ids:
            if uid == current_user.id:
                # ignorar a si próprio como alvo direto
                continue
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                continue
            db.add(SwapDirectTarget(
                swap_request_id=new_swap.id,
                user_id=user.id,
            ))

    db.commit()
    db.refresh(new_swap)

    try:
        notify_matching_users_same_day(db, new_swap)
        db.commit()
    except Exception:
        db.rollback()
        # não falhar o pedido por causa das notificações

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

    # Se houver destinatários diretos, apenas eles podem aceitar
    direct_targets = [t.user_id for t in getattr(swap, "direct_targets", [])]
    if direct_targets and current_user.id not in direct_targets:
        raise HTTPException(
            status_code=403,
            detail="This swap request is directed to specific users and you are not one of them",
        )

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
                    detail="Only T and Mt cannot have N the next day. Use confirm_incompatibility=true if you want to proceed."
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

        db.add(SwapHistory(
            swap_request_id=swap.id,
            requester_id=swap.requester_id,
            accepter_id=current_user.id,
            shift_id_offered=original_shift.id,
            shift_id_received=accepter_shift.id,
            accepted_at=datetime.utcnow(),
        ))

        db.commit()

    except Exception as e:
        db.rollback()
        print("Swap error:", e)
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


@router.get("/history", response_model=list[SwapHistoryRead])
def list_swap_history(
    limit: int = 100,
    before: date | None = None,
    db: Session = Depends(get_db),
):
    """Lista trocas aceites (histórico). Opcional: limit, before (só registos com accepted_at < before)."""
    q = db.query(SwapHistory).order_by(SwapHistory.accepted_at.desc())
    if before is not None:
        q = q.filter(SwapHistory.accepted_at < datetime.combine(before, time.min))
    return q.limit(limit).all()


@router.delete("/history")
def clear_swap_history(
    before: date,
    db: Session = Depends(get_db),
):
    """Remove registos de histórico com accepted_at anterior a `before` (ex.: fim do mês passado)."""
    deleted = db.query(SwapHistory).filter(
        SwapHistory.accepted_at < datetime.combine(before, time.min)
    ).delete()
    db.commit()
    return {"deleted": deleted, "before": str(before)}

@router.get("/matching", response_model=list[SwapRead])
def matching_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # todos os turnos do utilizador atual
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

        # 1) Se o pedido tiver wanted_options, verificar se algum turno meu encaixa
        wanted_opts = db.query(SwapWantedOption).filter(
            SwapWantedOption.swap_request_id == swap.id
        ).all()

        if wanted_opts:
            # mapa (date -> {shift_type_id,...}) para as opções deste swap
            wanted_by_date: dict[date, set[int]] = {}
            for opt in wanted_opts:
                wanted_by_date.setdefault(opt.date, set()).add(opt.shift_type_id)

            compatible = False

            for my_shift in my_shifts:
                if my_shift.shift_type_id is None:
                    continue
                allowed_types = wanted_by_date.get(my_shift.data)
                if not allowed_types:
                    continue
                if my_shift.shift_type_id in allowed_types:
                    compatible = True
                    break

            if compatible:
                result.append(swap)

            # já decidimos com base em wanted_options; não precisamos da lógica antiga
            continue

        # 2) Sem wanted_options → comportamento antigo (mesmo dia + SwapPreference)
        my_shift = my_shifts_by_date.get(original_shift.data)

        if not my_shift:
            continue

        preferences = db.query(SwapPreference).filter(
            SwapPreference.swap_request_id == swap.id
        ).all()

        # sem preferências → qualquer turno no mesmo dia
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

        swaps = db.query(SwapRequest).options(
            joinedload(SwapRequest.shift)
        ).filter(
            SwapRequest.status == SwapStatus.OPEN
        ).all()

        cycles = detect_swap_cycles(swaps, db=db)

        result = []

        for cycle in cycles:

            result.append({
                "cycle": cycle,
                "message": "swap cycle possible"
            })

        return {"cycles": result}

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
                "TEST": "HELLO"
            })

    return results
@router.post("/execute-cycle")
def execute_cycle(cycle: list[int], db: Session = Depends(get_db)):

    swaps = db.query(SwapRequest).filter(SwapRequest.id.in_(cycle)).all()

    if len(swaps) < 2:
        raise HTTPException(status_code=400, detail="Invalid cycle")

    shifts = []
    users = []
    for swap in swaps:
        shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()
        if not shift:
            raise HTTPException(status_code=404, detail=f"Shift for swap {swap.id} not found")
        shifts.append(shift)
        users.append(shift.user_id)

    _validate_cycle_execution(db, shifts, users)

    try:

        temp_user = -999

        # libertar primeiro turno
        shifts[0].user_id = temp_user
        db.flush()

        # mover restantes
        for i in range(1, len(shifts)):
            shifts[i].user_id = users[i-1]
            db.flush()

        # fechar ciclo
        shifts[0].user_id = users[-1]
        db.flush()

        for swap in swaps:
            swap.status = SwapStatus.ACCEPTED

        n = len(swaps)
        for i in range(n):
            db.add(SwapHistory(
                swap_request_id=swaps[i].id,
                requester_id=swaps[i].requester_id,
                accepter_id=users[(i + 1) % n],
                shift_id_offered=shifts[i].id,
                shift_id_received=shifts[(i + 1) % n].id,
                accepted_at=datetime.utcnow(),
                cycle_id=None,
            ))

        db.commit()

    except Exception as e:
        db.rollback()
        print("Cycle error:", e)
        raise HTTPException(status_code=500, detail="Cycle execution failed")

    return {"message": "Swap cycle executed successfully"}

@router.post("/cycles/propose")
def propose_cycle(
    cycle: list[int],
    db: Session = Depends(get_db)
):

    # buscar swaps abertos
    swaps = db.query(SwapRequest).filter(
        SwapRequest.id.in_(cycle),
        SwapRequest.status == SwapStatus.OPEN
    ).all()

    if len(swaps) != len(cycle):
        raise HTTPException(
            status_code=400,
            detail="Some swaps are not available"
        )

    # criar proposta de ciclo
    proposal = CycleProposal(
        status="PROPOSED"
    )
    db.add(proposal)
    db.flush()  # gera proposal.id

    involved_users = set()

    # ligar swaps ao ciclo e recolher todos os utilizadores
    for swap in swaps:
        # criar ligação Swap <-> Cycle
        db.add(CycleSwap(
            cycle_id=proposal.id,
            swap_id=swap.id
        ))

        # adicionar requester
        involved_users.add(swap.requester_id)

        # adicionar accepter se existir
        if swap.accepter_id:
            involved_users.add(swap.accepter_id)

    # se houver utilizadores adicionais do ciclo que devem participar,
    # podes adicioná-los manualmente aqui:
    # involved_users.update([user_id_1, user_id_2, ...])

    # criar confirmações para cada utilizador do ciclo
    for user_id in involved_users:
        db.add(CycleConfirmation(
            cycle_id=proposal.id,
            user_id=user_id,
            confirmed=False
        ))

    # marcar swaps como PROPOSED
    for swap in swaps:
        swap.status = SwapStatus.PROPOSED

    db.commit()

    return {
        "cycle_id": proposal.id,
        "swaps": cycle,
        "users": list(involved_users),
        "status": "PROPOSED"
    }

@router.post("/cycles/{cycle_id}/confirm")
def confirm_cycle(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    confirmation = db.query(CycleConfirmation).filter(
        CycleConfirmation.cycle_id == cycle_id,
        CycleConfirmation.user_id == current_user.id
    ).first()

    if not confirmation:
        raise HTTPException(
            status_code=404,
            detail="Confirmation not found for this user"
        )

    confirmation.confirmed = True
    db.flush()

    # verificar se todos confirmaram
    confirmations = db.query(CycleConfirmation).filter(
        CycleConfirmation.cycle_id == cycle_id
    ).all()

    all_confirmed = all(c.confirmed for c in confirmations)

    if all_confirmed:

        cycle_swaps = db.query(CycleSwap).filter(
            CycleSwap.cycle_id == cycle_id
        ).all()

        swap_ids = [cs.swap_id for cs in cycle_swaps]

        # executar ciclo
        execute_cycle(swap_ids, db)

        proposal = db.query(CycleProposal).filter(
            CycleProposal.id == cycle_id
        ).first()

        proposal.status = "EXECUTED"

    db.commit()

    return {
        "cycle_id": cycle_id,
        "user": current_user.id,
        "confirmed": True,
        "all_confirmed": all_confirmed
    }