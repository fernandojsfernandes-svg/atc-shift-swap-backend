"""Flags de UI para turnos que participaram numa troca aceite (oferecido ou recebido)."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models import SwapHistory, SwapRequest, SwapStatus, User


def shift_ids_in_accepted_swaps(db: Session, shift_ids: list[int]) -> set[int]:
    """
    IDs de turnos ligados a trocas concluídas: pedido (shift_id do SwapRequest) ou
    registo recebido noutro utilizador (SwapHistory.shift_id_received).
    Usado para show_troca_bht / show_troca_ts (split vermelho/amarelo + cinzento).

    Usa select() + scalars() (SQLAlchemy 2.x); o antigo db.query(Col).all() devolvia Row
    sem .shift_id em alguns casos → AttributeError e HTTP 500 no Render.
    """
    if not shift_ids:
        return set()
    offered_raw = db.execute(
        select(SwapRequest.shift_id).where(
            SwapRequest.shift_id.in_(shift_ids),
            SwapRequest.status == SwapStatus.ACCEPTED,
        )
    ).scalars().all()
    received_raw = db.execute(
        select(SwapHistory.shift_id_received).where(
            SwapHistory.shift_id_received.in_(shift_ids),
        )
    ).scalars().all()
    offered = {x for x in offered_raw if x is not None}
    received = {x for x in received_raw if x is not None}
    return offered | received


def single_shift_involved_in_accepted_swap(db: Session, shift_id: int) -> bool:
    return shift_id in shift_ids_in_accepted_swaps(db, [shift_id])


def swap_partner_labels_for_user_shifts(
    db: Session, user_id: int, shift_ids: list[int]
) -> dict[int, tuple[str | None, str | None]]:
    """
    Por cada turno do utilizador que aparece num SwapHistory aceite, devolve
    (nome, n.º funcionário) do colega com quem foi feita a troca.
    - shift_id_offered: o aceitante ficou com o turno oferecido → colega = pedinte.
    - shift_id_received: o pedinte ficou com o turno recebido → colega = aceitante.
    Vários registos para o mesmo shift_id: usa o mais recente (accepted_at desc).
    """
    if not shift_ids:
        return {}
    histories = (
        db.query(SwapHistory)
        .filter(
            or_(
                SwapHistory.shift_id_offered.in_(shift_ids),
                SwapHistory.shift_id_received.in_(shift_ids),
            )
        )
        .order_by(SwapHistory.accepted_at.desc())
        .all()
    )
    partner_id_by_shift: dict[int, int] = {}
    for h in histories:
        if h.shift_id_offered in shift_ids and h.shift_id_offered not in partner_id_by_shift:
            if user_id == h.accepter_id and h.requester_id:
                partner_id_by_shift[h.shift_id_offered] = h.requester_id
        if h.shift_id_received in shift_ids and h.shift_id_received not in partner_id_by_shift:
            if user_id == h.requester_id and h.accepter_id:
                partner_id_by_shift[h.shift_id_received] = h.accepter_id
    if not partner_id_by_shift:
        return {}
    partner_ids = set(partner_id_by_shift.values())
    users = db.query(User).filter(User.id.in_(partner_ids)).all()
    by_id = {u.id: u for u in users}
    out: dict[int, tuple[str | None, str | None]] = {}
    for sid, pid in partner_id_by_shift.items():
        u = by_id.get(pid)
        if not u:
            continue
        out[sid] = ((u.nome or "").strip() or None, (u.employee_number or "").strip() or None)
    return out
