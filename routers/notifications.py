import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from datetime import datetime

from database import get_db
from models import (
    SwapNotification,
    SwapRequest,
    SwapStatus,
    Shift,
    User,
    SwapPreference,
    ShiftType,
    SwapWantedOption,
    SwapDirectTarget,
)
from schemas.notification import NotificationRead, NotificationWithSwapRead
from schemas.swap import WantedOptionBrief
from security import get_current_user

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


def _notification_package_ids_raw(n: SwapNotification) -> list[int] | None:
    raw = getattr(n, "package_accepter_shift_ids", None)
    if not raw:
        return None
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list) or not arr:
            return None
        return [int(x) for x in arr]
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _consolidate_duplicate_packages(db: Session, user_id: int) -> None:
    """
    Migração em tempo de leitura: vários avisos can_accept para o mesmo pedido
    e datas distintas do aceitante → um único pacote.
    """
    groups = (
        db.query(
            SwapNotification.swap_request_id,
            func.count(SwapNotification.id),
        )
        .filter(
            SwapNotification.user_id == user_id,
            SwapNotification.read_at.is_(None),
            SwapNotification.notification_kind == "can_accept",
            SwapNotification.accepter_shift_id.isnot(None),
        )
        .group_by(SwapNotification.swap_request_id)
        .having(func.count(SwapNotification.id) > 1)
        .all()
    )
    for swap_request_id, _cnt in groups:
        rows = (
            db.query(SwapNotification)
            .filter(
                SwapNotification.user_id == user_id,
                SwapNotification.swap_request_id == swap_request_id,
                SwapNotification.read_at.is_(None),
                SwapNotification.notification_kind == "can_accept",
                SwapNotification.accepter_shift_id.isnot(None),
            )
            .order_by(SwapNotification.id)
            .all()
        )
        if len(rows) < 2:
            continue
        shifts: list[tuple[SwapNotification, Shift | None]] = []
        for r in rows:
            sh = db.get(Shift, r.accepter_shift_id)
            shifts.append((r, sh))
        if not all(s for _, s in shifts):
            continue
        by_date = {s.data for _, s in shifts if s}
        if len(by_date) != len(shifts):
            continue
        if len(by_date) < 2:
            continue
        sorted_rows = sorted(shifts, key=lambda x: x[1].data)
        ordered_ids = [s.id for _, s in sorted_rows]
        keeper = sorted_rows[0][0]
        keeper.package_accepter_shift_ids = json.dumps(ordered_ids)
        keeper.accepter_shift_id = None
        for r, _ in sorted_rows[1:]:
            db.delete(r)
    try:
        db.commit()
    except Exception:
        db.rollback()


def _wanted_options_brief(db: Session, swap_id: int) -> list[WantedOptionBrief] | None:
    """Agrupa swap_wanted_options por data com códigos de turno (para a UI do aceitante)."""
    rows = (
        db.query(SwapWantedOption.date, ShiftType.code)
        .join(ShiftType, SwapWantedOption.shift_type_id == ShiftType.id)
        .filter(SwapWantedOption.swap_request_id == swap_id)
        .order_by(SwapWantedOption.date, ShiftType.code)
        .all()
    )
    if not rows:
        return None
    by_date: dict = {}
    for d, code in rows:
        by_date.setdefault(d, set()).add(code)
    return [
        WantedOptionBrief(date=d, shift_types=sorted(by_date[d]))
        for d in sorted(by_date.keys())
    ]


def _enrich_notification(db: Session, n: SwapNotification) -> dict:
    """Junta dados do pedido de troca para a mensagem na UI."""
    swap = (
        db.query(SwapRequest)
        .options(joinedload(SwapRequest.shift), joinedload(SwapRequest.requester))
        .filter(SwapRequest.id == n.swap_request_id)
        .first()
    )
    if not swap or not swap.shift:
        return {
            "id": n.id,
            "user_id": n.user_id,
            "swap_request_id": n.swap_request_id,
            "created_at": n.created_at,
            "read_at": n.read_at,
            "notification_kind": getattr(n, "notification_kind", "can_accept"),
            "rejected_by_name": getattr(n, "rejected_by_name", None),
            "body_text": getattr(n, "body_text", None),
            "requester_name": None,
            "offered_shift_date": None,
            "offered_shift_code": None,
            "accepted_shift_types": None,
            "wanted_options": None,
            "accepter_shift_date": None,
            "accepter_shift_code": None,
            "accepter_package_legs": None,
            "requester_package_legs": None,
        }
    prefs = (
        db.query(SwapPreference)
        .join(ShiftType, SwapPreference.shift_type_id == ShiftType.id)
        .filter(SwapPreference.swap_request_id == swap.id)
        .all()
    )
    codes = [p.shift_type.code for p in prefs] if prefs else []
    pkg_ids = _notification_package_ids_raw(n)
    accepter_sid = getattr(n, "accepter_shift_id", None)
    accepter_date = None
    accepter_code = None
    accepter_package_legs: list[dict] | None = None
    requester_package_legs: list[dict] | None = None
    wanted: list[WantedOptionBrief] | None = None

    if pkg_ids:
        wanted = _wanted_options_brief(db, swap.id)
        acq_shifts = [db.get(Shift, sid) for sid in pkg_ids]
        acq_shifts = [s for s in acq_shifts if s]
        if len(acq_shifts) == len(pkg_ids):
            acq_shifts.sort(key=lambda s: s.data)
            accepter_package_legs = [
                {"date": str(s.data), "code": s.codigo} for s in acq_shifts
            ]
            offer_sh = swap.shift
            req_legs: list[Shift] = []
            for ash in acq_shifts:
                d = ash.data
                if offer_sh and d == offer_sh.data:
                    req_legs.append(offer_sh)
                else:
                    rs = (
                        db.query(Shift)
                        .filter(Shift.user_id == swap.requester_id, Shift.data == d)
                        .first()
                    )
                    if rs:
                        req_legs.append(rs)
            if len(req_legs) == len(acq_shifts):
                requester_package_legs = [
                    {"date": str(s.data), "code": s.codigo} for s in req_legs
                ]
            else:
                accepter_package_legs = None
                requester_package_legs = None
    elif accepter_sid:
        ash = db.get(Shift, accepter_sid)
        if ash:
            accepter_date = str(ash.data)
            accepter_code = ash.codigo
        wanted = None
    else:
        wanted = _wanted_options_brief(db, swap.id)

    # Troca direta: o destinatário vê o turno concreto dele no mesmo dia (não "qualquer turno").
    if (
        swap.shift
        and swap.shift.data
        and not pkg_ids
        and not accepter_sid
        and db.query(SwapDirectTarget)
        .filter(
            SwapDirectTarget.swap_request_id == swap.id,
            SwapDirectTarget.user_id == n.user_id,
        )
        .first()
    ):
        ash = (
            db.query(Shift)
            .filter(
                Shift.user_id == n.user_id,
                Shift.data == swap.shift.data,
            )
            .first()
        )
        if ash:
            accepter_date = str(ash.data)
            accepter_code = ash.codigo

    return {
        "id": n.id,
        "user_id": n.user_id,
        "swap_request_id": n.swap_request_id,
        "created_at": n.created_at,
        "read_at": n.read_at,
        "notification_kind": getattr(n, "notification_kind", "can_accept"),
        "rejected_by_name": getattr(n, "rejected_by_name", None),
        "body_text": getattr(n, "body_text", None),
        "requester_name": swap.requester.nome if swap.requester else None,
        "offered_shift_date": str(swap.shift.data),
        "offered_shift_code": swap.shift.codigo,
        "accepted_shift_types": codes,
        "wanted_options": wanted,
        "accepter_shift_date": accepter_date,
        "accepter_shift_code": accepter_code,
        "accepter_package_legs": accepter_package_legs,
        "requester_package_legs": requester_package_legs,
    }


@router.get("/", response_model=list[NotificationWithSwapRead])
def list_my_notifications(
    unread_only: bool = Query(False, description="Só não lidas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista notificações do utilizador: pedidos de troca que pode satisfazer
    (ex.: «Um colega quer trocar o turno T do dia X por um MG ou M»).
    """
    _consolidate_duplicate_packages(db, current_user.id)
    q = (
        db.query(SwapNotification)
        .filter(SwapNotification.user_id == current_user.id)
        .order_by(SwapNotification.created_at.desc())
    )
    if unread_only:
        q = q.filter(SwapNotification.read_at.is_(None))
    notifications = q.limit(100).all()
    # Não mostrar «can_accept» se o pedido já fechou (ex.: cancelado pelo proponente antes de limpar read_at).
    out: list[dict] = []
    for n in notifications:
        kind = n.notification_kind or "can_accept"
        if kind == "can_accept":
            sw = (
                db.query(SwapRequest)
                .filter(SwapRequest.id == n.swap_request_id)
                .first()
            )
            if not sw or sw.status != SwapStatus.OPEN:
                continue
        out.append(_enrich_notification(db, n))
    return out


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca uma notificação como lida."""
    n = (
        db.query(SwapNotification)
        .filter(
            SwapNotification.id == notification_id,
            SwapNotification.user_id == current_user.id,
        )
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.read_at = datetime.utcnow()
    db.commit()
    db.refresh(n)
    return n
