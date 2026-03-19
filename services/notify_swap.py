"""
Cria notificações para utilizadores que podem satisfazer um pedido de troca (mesmo dia)
e que cumprem as regras: apenas T e Mt não podem ter N no dia seguinte; máx. 9 dias consecutivos.
Só notifica quem tiver notifications_enabled=True.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import (
    SwapRequest,
    Shift,
    User,
    SwapPreference,
    SwapNotification,
)
from rules.shift_rules import is_next_day_incompatible, exceeds_max_consecutive_days


def _would_swap_break_rules(
    db: Session,
    offered_shift: Shift,
    accepter_shift: Shift,
    requester_id: int,
) -> bool:
    """
    Simula a troca direta (mesmo dia): requester dá offered_shift, recebe accepter_shift;
    accepter dá accepter_shift, recebe offered_shift.
    Devolve True se a troca violaria regras (apenas T→N e Mt→N no dia seguinte, ou >9 dias consecutivos).
    """
    accepter_id = accepter_shift.user_id
    date_d = offered_shift.data

    # Shifts do requester após troca: os dele exceto offered_shift, mais o que receberia
    from types import SimpleNamespace
    requester_shifts = (
        db.query(Shift)
        .filter(Shift.user_id == requester_id, Shift.id != offered_shift.id)
        .all()
    )
    req_received = SimpleNamespace(
        data=accepter_shift.data,
        codigo=accepter_shift.codigo,
    )
    requester_after = sorted(
        [s for s in requester_shifts if s.data != date_d] + [req_received],
        key=lambda s: s.data,
    )

    # Shifts do accepter após troca: os dele exceto accepter_shift, mais offered_shift
    accepter_shifts = (
        db.query(Shift)
        .filter(Shift.user_id == accepter_id, Shift.id != accepter_shift.id)
        .all()
    )
    acc_received = SimpleNamespace(
        data=offered_shift.data,
        codigo=offered_shift.codigo,
    )
    accepter_after = sorted(
        [s for s in accepter_shifts if s.data != date_d]
        + [acc_received],
        key=lambda s: s.data,
    )

    # Next-day: requester com accepter_shift.codigo no dia D → dia D+1
    for i in range(len(requester_after) - 1):
        today_s = requester_after[i]
        next_s = requester_after[i + 1]
        if (next_s.data - today_s.data).days == 1 and is_next_day_incompatible(
            today_s.codigo, next_s.codigo
        ):
            return True
    for i in range(len(accepter_after) - 1):
        today_s = accepter_after[i]
        next_s = accepter_after[i + 1]
        if (next_s.data - today_s.data).days == 1 and is_next_day_incompatible(
            today_s.codigo, next_s.codigo
        ):
            return True

    # Consecutive working days (precisa de objetos com .data e .codigo)
    if exceeds_max_consecutive_days(requester_after):
        return True
    if exceeds_max_consecutive_days(accepter_after):
        return True

    return False


def notify_matching_users_same_day(db: Session, swap: SwapRequest) -> None:
    """
    Para um pedido de troca no mesmo dia: notifica quem pode satisfazer o pedido.
    - Com preferências (DC, DS, …): só quem tem nesse dia um turno desse tipo.
    - Sem preferências (“aceita qualquer”): todos os que têm algum turno nesse dia
      (exceto o pedinte), desde que a troca respeite as regras.
    """
    offered_shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()
    if not offered_shift or not offered_shift.data:
        return

    prefs = (
        db.query(SwapPreference)
        .filter(SwapPreference.swap_request_id == swap.id)
        .all()
    )
    date_d = offered_shift.data
    requester_id = swap.requester_id

    if prefs:
        allowed_type_ids = [p.shift_type_id for p in prefs]
        candidate_shifts = (
            db.query(Shift)
            .filter(
                Shift.data == date_d,
                Shift.user_id != requester_id,
                Shift.shift_type_id.in_(allowed_type_ids),
            )
            .all()
        )
    else:
        candidate_shifts = (
            db.query(Shift)
            .filter(
                Shift.data == date_d,
                Shift.user_id != requester_id,
            )
            .all()
        )

    now = datetime.utcnow()
    for accepter_shift in candidate_shifts:
        user_b = db.query(User).filter(User.id == accepter_shift.user_id).first()
        if not user_b or not getattr(user_b, "notifications_enabled", True):
            continue
        if _would_swap_break_rules(db, offered_shift, accepter_shift, requester_id):
            continue
        db.add(
            SwapNotification(
                user_id=user_b.id,
                swap_request_id=swap.id,
                created_at=now,
            )
        )
