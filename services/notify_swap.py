"""
Cria notificações para utilizadores que podem satisfazer um pedido de troca.

- Mesmo dia: um pedido → tipicamente um aviso por utilizador elegível (rules engine).
- Outros dias (`SwapWantedOption`), uma só data: um aviso por turno seu alternativo (OR).
- Várias datas no pedido: um único aviso em pacote por utilizador (todas as pernas em conjunto).

Só notifica quem tiver notifications_enabled=True.
"""
import json
from collections import defaultdict
from datetime import datetime
from itertools import product
from types import SimpleNamespace

from sqlalchemy.orm import Session

from services.multi_swap import validate_multi_swap_pairs

from models import (
    SwapRequest,
    Shift,
    User,
    SwapPreference,
    SwapNotification,
    SwapWantedOption,
    ShiftType,
)
from rules.shift_rules import is_next_day_incompatible, exceeds_max_consecutive_days


def _would_swap_break_rules(
    db: Session,
    offered_shift: Shift,
    accepter_shift: Shift,
    requester_id: int,
) -> bool:
    """
    Simula a troca: requester dá offered_shift, recebe accepter_shift;
    accepter dá accepter_shift, recebe offered_shift (datas podem ser diferentes).
    Devolve True se violar T/Mt→N ou >9 dias consecutivos.
    """
    accepter_id = accepter_shift.user_id

    requester_shifts = (
        db.query(Shift)
        .filter(Shift.user_id == requester_id, Shift.id != offered_shift.id)
        .all()
    )
    requester_after = sorted(
        [SimpleNamespace(data=s.data, codigo=s.codigo) for s in requester_shifts]
        + [
            SimpleNamespace(
                data=accepter_shift.data,
                codigo=accepter_shift.codigo,
            )
        ],
        key=lambda s: s.data,
    )

    accepter_shifts = (
        db.query(Shift)
        .filter(Shift.user_id == accepter_id, Shift.id != accepter_shift.id)
        .all()
    )
    accepter_after = sorted(
        [SimpleNamespace(data=s.data, codigo=s.codigo) for s in accepter_shifts]
        + [
            SimpleNamespace(
                data=offered_shift.data,
                codigo=offered_shift.codigo,
            )
        ],
        key=lambda s: s.data,
    )

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

    if exceeds_max_consecutive_days(requester_after):
        return True
    if exceeds_max_consecutive_days(accepter_after):
        return True

    return False


def _shift_matches_wanted_on_date(
    shift: Shift,
    date_d,
    allowed_type_ids: set[int],
    allowed_codes: set[str],
) -> bool:
    if shift.data != date_d:
        return False
    if shift.shift_type_id and shift.shift_type_id in allowed_type_ids:
        return True
    code = (shift.codigo or "").strip()
    if code and code in allowed_codes:
        return True
    return False


def _purge_pending_swap_notifications(db: Session, user_id: int, swap_id: int) -> None:
    """Remove avisos pendentes antigos (evita duplicados ao atualizar pacote)."""
    db.query(SwapNotification).filter(
        SwapNotification.user_id == user_id,
        SwapNotification.swap_request_id == swap_id,
        SwapNotification.read_at.is_(None),
        SwapNotification.notification_kind == "can_accept",
    ).delete(synchronize_session=False)


def notify_matching_users_wanted_options(db: Session, swap: SwapRequest) -> None:
    """
    Pedido com SwapWantedOption:
    - Uma data no pedido: um aviso por (utilizador, turno alternativo), regras por par.
    - Várias datas: pacote com o dia da oferta (se pedido) + uma das datas «outras» (OU),
      ou só uma data alternativa quando não há tipos pedidos no dia da oferta.
    """
    offered_shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()
    if not offered_shift or not offered_shift.data:
        return

    rows = (
        db.query(SwapWantedOption, ShiftType.code)
        .join(ShiftType, SwapWantedOption.shift_type_id == ShiftType.id)
        .filter(SwapWantedOption.swap_request_id == swap.id)
        .all()
    )
    if not rows:
        return

    wanted_by_date: dict = {}
    for opt, code in rows:
        d = opt.date
        if d not in wanted_by_date:
            wanted_by_date[d] = {"type_ids": set(), "codes": set()}
        wanted_by_date[d]["type_ids"].add(opt.shift_type_id)
        wanted_by_date[d]["codes"].add((code or "").strip())

    requester_id = swap.requester_id
    now = datetime.utcnow()
    offer_date = offered_shift.data

    # Turnos do pedinte por data (só entradas onde ele tem escala)
    req_by_date: dict = {offer_date: offered_shift}
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

    candidate_shifts = (
        db.query(Shift)
        .filter(
            Shift.user_id != requester_id,
            Shift.data.in_(list(wanted_by_date.keys())),
        )
        .all()
    )

    # --- Várias datas: pacote = dia da oferta (se pedido) + UMA data extra (OU) ---
    if len(wanted_by_date) > 1:
        by_user: dict[int, list[Shift]] = defaultdict(list)
        for sh in candidate_shifts:
            by_user[sh.user_id].append(sh)

        offer_in_wanted = offer_date in wanted_by_date
        other_dates = sorted(d for d in wanted_by_date if d != offer_date)

        for uid, user_shifts in by_user.items():
            user_b = db.query(User).filter(User.id == uid).first()
            if not user_b or not getattr(user_b, "notifications_enabled", True):
                continue

            package_ids: list[int] | None = None

            if offer_in_wanted:
                ospec = wanted_by_date[offer_date]
                offer_cands = [
                    sh
                    for sh in user_shifts
                    if sh.data == offer_date
                    and _shift_matches_wanted_on_date(
                        sh, offer_date, ospec["type_ids"], ospec["codes"]
                    )
                ]
                if not offer_cands:
                    continue
                for d in other_dates:
                    if d not in req_by_date:
                        continue
                    spec = wanted_by_date[d]
                    other_cands = [
                        sh
                        for sh in user_shifts
                        if sh.data == d
                        and _shift_matches_wanted_on_date(
                            sh, d, spec["type_ids"], spec["codes"]
                        )
                    ]
                    for osh in offer_cands:
                        for csh in other_cands:
                            pairs = [
                                (offered_shift, osh),
                                (req_by_date[d], csh),
                            ]
                            if validate_multi_swap_pairs(
                                db, requester_id, uid, pairs
                            ):
                                package_ids = [s.id for s in sorted((osh, csh), key=lambda x: x.data)]
                                break
                        if package_ids:
                            break
                    if package_ids:
                        break
            else:
                for d in sorted(wanted_by_date.keys()):
                    if d not in req_by_date:
                        continue
                    spec = wanted_by_date[d]
                    cands = [
                        sh
                        for sh in user_shifts
                        if sh.data == d
                        and _shift_matches_wanted_on_date(
                            sh, d, spec["type_ids"], spec["codes"]
                        )
                    ]
                    for csh in cands:
                        pairs = [(offered_shift, csh)]
                        if validate_multi_swap_pairs(
                            db, requester_id, uid, pairs
                        ):
                            package_ids = [csh.id]
                            break
                    if package_ids:
                        break

            if package_ids:
                _purge_pending_swap_notifications(db, uid, swap.id)
                db.add(
                    SwapNotification(
                        user_id=uid,
                        swap_request_id=swap.id,
                        created_at=now,
                        accepter_shift_id=None,
                        package_accepter_shift_ids=json.dumps(package_ids),
                    )
                )
        return

    # --- Uma só data: manter um aviso por turno alternativo (OR) ---
    seen_pairs: set[tuple[int, int]] = set()

    for accepter_shift in candidate_shifts:
        w = wanted_by_date.get(accepter_shift.data)
        if not w:
            continue
        if not _shift_matches_wanted_on_date(
            accepter_shift,
            accepter_shift.data,
            w["type_ids"],
            w["codes"],
        ):
            continue
        user_b = db.query(User).filter(User.id == accepter_shift.user_id).first()
        if not user_b or not getattr(user_b, "notifications_enabled", True):
            continue
        if _would_swap_break_rules(db, offered_shift, accepter_shift, requester_id):
            continue
        key = (user_b.id, accepter_shift.id)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        db.add(
            SwapNotification(
                user_id=user_b.id,
                swap_request_id=swap.id,
                created_at=now,
                accepter_shift_id=accepter_shift.id,
            )
        )


def notify_matching_users_same_day(db: Session, swap: SwapRequest) -> None:
    """
    Para um pedido sem WantedOption (troca mesmo dia): notifica quem pode satisfazer.
    Com preferências: só tipos indicados; sem: qualquer turno nesse dia (exceto pedinte).
    Se existir SwapWantedOption para este pedido, delega em notify_matching_users_wanted_options.
    """
    has_wanted = (
        db.query(SwapWantedOption.id)
        .filter(SwapWantedOption.swap_request_id == swap.id)
        .first()
    )
    if has_wanted:
        notify_matching_users_wanted_options(db, swap)
        return

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
