"""Flags de UI para turnos que participaram numa troca aceite (oferecido ou recebido)."""

from sqlalchemy.orm import Session

from models import SwapHistory, SwapRequest, SwapStatus


def shift_ids_in_accepted_swaps(db: Session, shift_ids: list[int]) -> set[int]:
    """
    IDs de turnos ligados a trocas concluídas: pedido (shift_id do SwapRequest) ou
    registo recebido noutro utilizador (SwapHistory.shift_id_received).
    Usado para show_troca_bht / show_troca_ts (split vermelho/amarelo + cinzento).
    """
    if not shift_ids:
        return set()
    offered = {
        r.shift_id
        for r in db.query(SwapRequest.shift_id).filter(
            SwapRequest.shift_id.in_(shift_ids),
            SwapRequest.status == SwapStatus.ACCEPTED,
        ).all()
    }
    received = {
        r.shift_id_received
        for r in db.query(SwapHistory.shift_id_received).filter(
            SwapHistory.shift_id_received.in_(shift_ids),
        ).all()
    }
    return offered | received


def single_shift_involved_in_accepted_swap(db: Session, shift_id: int) -> bool:
    return shift_id in shift_ids_in_accepted_swaps(db, [shift_id])
