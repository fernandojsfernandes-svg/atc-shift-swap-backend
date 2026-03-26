"""
Validação e aplicação de trocas em pacote (várias pernas, mesmo par requester/aceitante).
"""
from __future__ import annotations

from typing import Any

from types import SimpleNamespace

from sqlalchemy.orm import Session

from models import Shift
from rules.shift_rules import exceeds_max_consecutive_days, is_next_day_incompatible


def _to_sorted_mem(shifts: list[Any]) -> list[SimpleNamespace]:
    return sorted(
        (SimpleNamespace(data=s.data, codigo=s.codigo) for s in shifts),
        key=lambda s: s.data,
    )


def _has_two_shifts_same_day_from_shifts(shifts: list[Any]) -> bool:
    """Após a troca simulada, cada utilizador não pode ter dois turnos no mesmo dia."""
    dates = [s.data for s in shifts]
    return len(dates) != len(set(dates))


def _violates_next_day_rule_from_shifts(shifts_mem: list[SimpleNamespace]) -> bool:
    n = len(shifts_mem)
    for i in range(n - 1):
        today = shifts_mem[i]
        tomorrow = shifts_mem[i + 1]
        if (tomorrow.data - today.data).days == 1:
            if is_next_day_incompatible(today.codigo, tomorrow.codigo):
                return True
    return False


def validate_multi_swap_pairs(
    db: Session,
    requester_id: int,
    accepter_id: int,
    pairs: list[tuple[Shift, Shift]],
) -> bool:
    """
    pairs: (turno do pedinte, turno do aceitante) por cada perna.
    Simula todas as trocas e verifica regras.
    """
    if not pairs:
        return False
    r_ids = {rs.id for rs, _ in pairs}
    a_ids = {as_.id for _, as_ in pairs}
    if len(r_ids) != len(pairs) or len(a_ids) != len(pairs):
        return False
    for rs, as_ in pairs:
        if rs.user_id != requester_id or as_.user_id != accepter_id:
            return False

    requester_shifts = db.query(Shift).filter(Shift.user_id == requester_id).all()
    accepter_shifts = db.query(Shift).filter(Shift.user_id == accepter_id).all()

    r_after_list = [s for s in requester_shifts if s.id not in r_ids] + [as_ for _, as_ in pairs]
    a_after_list = [s for s in accepter_shifts if s.id not in a_ids] + [rs for rs, _ in pairs]

    if _has_two_shifts_same_day_from_shifts(r_after_list) or _has_two_shifts_same_day_from_shifts(
        a_after_list
    ):
        return False

    r_mem = _to_sorted_mem(r_after_list)
    a_mem = _to_sorted_mem(a_after_list)

    if _violates_next_day_rule_from_shifts(r_mem) or _violates_next_day_rule_from_shifts(a_mem):
        return False

    if exceeds_max_consecutive_days(r_mem) or exceeds_max_consecutive_days(a_mem):
        return False

    return True


def proponent_violation_code_for_pairs(
    db: Session,
    requester_id: int,
    pairs: list[tuple[Shift, Any]],
) -> str | None:
    """
    Simula só o efeito no pedinte após as pernas indicadas.
    Devolve None se válido; senão um código: 'next_day', 'nine_days', 'double_same_day'.
    """
    if not pairs:
        return None
    r_ids = {rs.id for rs, _ in pairs}
    requester_shifts = db.query(Shift).filter(Shift.user_id == requester_id).all()
    r_after_list = [s for s in requester_shifts if s.id not in r_ids] + [as_ for _, as_ in pairs]
    if _has_two_shifts_same_day_from_shifts(r_after_list):
        return "double_same_day"
    r_mem = _to_sorted_mem(r_after_list)
    if _violates_next_day_rule_from_shifts(r_mem):
        return "next_day"
    if exceeds_max_consecutive_days(r_mem):
        return "nine_days"
    return None
