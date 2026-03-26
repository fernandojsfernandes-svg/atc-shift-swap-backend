"""
Validação ao criar pedido de troca: o proponente não pode ficar com escala inválida
para qualquer desfecho admissível do pedido (mesmas regras que no aceite).
"""
from __future__ import annotations

from datetime import date
from itertools import product
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Shift, ShiftType
from schemas.swap import SwapCreate
from services.multi_swap import proponent_violation_code_for_pairs

_FAKE_ID = -8_000_000


def _fake_shift(d: date, codigo: str, idx: int) -> SimpleNamespace:
    return SimpleNamespace(id=_FAKE_ID - idx, data=d, codigo=codigo)


def _message_for_code(code: str) -> str:
    if code == "next_day":
        return (
            "Este pedido não pode ser processado porque viola a regra da N após T ou Mt "
            "no dia seguinte."
        )
    if code == "nine_days":
        return (
            "Este pedido não pode ser processado porque viola a regra dos mais de "
            "nove dias consecutivos a trabalhar."
        )
    if code == "double_same_day":
        return (
            "Este pedido não pode ser processado porque violaria dois turnos no mesmo dia."
        )
    return "Este pedido não pode ser processado por violar regras de escalas."


def _collect_shift_type_codes(db: Session, raw_codes: list[str]) -> list[str]:
    out: list[str] = []
    for raw in raw_codes:
        st = db.query(ShiftType).filter(ShiftType.code == raw.strip()).first()
        if st and (st.code or "").strip():
            out.append((st.code or "").strip())
    return out


def validate_proponent_swap_create(
    db: Session,
    swap: SwapCreate,
    offered_shift: Shift,
    requester_id: int,
) -> None:
    """Levanta HTTPException 400 se o pedinte ficaria sempre inválido após a troca."""
    if swap.direct_target_ids:
        return

    if swap.wanted_options:
        _validate_wanted(db, swap, offered_shift, requester_id)
    else:
        _validate_same_day(db, swap, offered_shift, requester_id)


def _validate_same_day(
    db: Session,
    swap: SwapCreate,
    offered_shift: Shift,
    requester_id: int,
) -> None:
    offer_date = offered_shift.data
    codes: list[str] = []
    if swap.acceptable_shift_types:
        codes = _collect_shift_type_codes(db, swap.acceptable_shift_types)
    else:
        rows = (
            db.query(Shift.codigo)
            .filter(Shift.data == offer_date, Shift.user_id != requester_id)
            .distinct()
            .all()
        )
        codes = list({(r[0] or "").strip() for r in rows if (r[0] or "").strip()})
        if not codes:
            codes = _collect_shift_type_codes(
                db, [st.code for st in db.query(ShiftType).all() if st.code]
            )

    if not codes:
        return

    first_v: str | None = None
    for idx, codigo in enumerate(codes):
        fake = _fake_shift(offer_date, codigo, idx)
        v = proponent_violation_code_for_pairs(db, requester_id, [(offered_shift, fake)])
        if v is None:
            return
        if first_v is None:
            first_v = v

    raise HTTPException(status_code=400, detail=_message_for_code(first_v or "nine_days"))


def _wanted_codes_by_date(db: Session, swap: SwapCreate) -> dict[date, set[str]]:
    out: dict[date, set[str]] = {}
    for opt in swap.wanted_options or []:
        for raw in opt.shift_types:
            st = db.query(ShiftType).filter(ShiftType.code == raw.strip()).first()
            if st and (st.code or "").strip():
                out.setdefault(opt.date, set()).add((st.code or "").strip())
    return out


def _validate_wanted(
    db: Session,
    swap: SwapCreate,
    offered_shift: Shift,
    requester_id: int,
) -> None:
    wanted_by_date = _wanted_codes_by_date(db, swap)
    if not wanted_by_date:
        return

    offer_date = offered_shift.data
    req_by_date: dict[date, Shift] = {offer_date: offered_shift}
    for d in wanted_by_date:
        if d == offer_date:
            continue
        rs_other = (
            db.query(Shift)
            .filter(Shift.user_id == requester_id, Shift.data == d)
            .first()
        )
        if rs_other:
            req_by_date[d] = rs_other

    if len(wanted_by_date) == 1:
        d = next(iter(wanted_by_date))
        first_v: str | None = None
        for idx, code in enumerate(wanted_by_date[d]):
            fake = _fake_shift(d, code, idx)
            v = proponent_violation_code_for_pairs(
                db, requester_id, [(offered_shift, fake)]
            )
            if v is None:
                return
            if first_v is None:
                first_v = v
        raise HTTPException(status_code=400, detail=_message_for_code(first_v or "nine_days"))

    offer_in_wanted = offer_date in wanted_by_date
    other_dates = sorted(d for d in wanted_by_date if d != offer_date)

    if offer_in_wanted:
        first_v: str | None = None
        tried = False
        idx = 0
        for d in other_dates:
            if d not in req_by_date:
                continue
            for code1, code2 in product(
                wanted_by_date[offer_date],
                wanted_by_date[d],
            ):
                tried = True
                p1 = _fake_shift(offer_date, code1, idx)
                idx += 1
                p2 = _fake_shift(d, code2, idx)
                idx += 1
                v = proponent_violation_code_for_pairs(
                    db,
                    requester_id,
                    [(offered_shift, p1), (req_by_date[d], p2)],
                )
                if v is None:
                    return
                if first_v is None:
                    first_v = v
        if tried:
            raise HTTPException(
                status_code=400, detail=_message_for_code(first_v or "nine_days")
            )
        return

    # Várias datas, dia da oferta não está nas opções: uma perna (oferta → turno pedido numa data)
    first_v = None
    tried = False
    idx = 0
    for d in sorted(wanted_by_date.keys()):
        if d not in req_by_date:
            continue
        for code in wanted_by_date[d]:
            tried = True
            fake = _fake_shift(d, code, idx)
            idx += 1
            v = proponent_violation_code_for_pairs(
                db, requester_id, [(offered_shift, fake)]
            )
            if v is None:
                return
            if first_v is None:
                first_v = v
    if tried:
        raise HTTPException(status_code=400, detail=_message_for_code(first_v or "nine_days"))
