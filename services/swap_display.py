"""Flags de UI para turnos que participaram numa troca aceite (oferecido ou recebido)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import SwapHistory, SwapRequest, SwapStatus


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
