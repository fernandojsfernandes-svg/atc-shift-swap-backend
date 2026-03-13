from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from datetime import datetime

from database import get_db
from models import SwapNotification, SwapRequest, Shift, User, SwapPreference, ShiftType
from schemas.notification import NotificationRead, NotificationWithSwapRead
from security import get_current_user

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


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
            "requester_name": None,
            "offered_shift_date": None,
            "offered_shift_code": None,
            "accepted_shift_types": None,
        }
    prefs = (
        db.query(SwapPreference)
        .join(ShiftType, SwapPreference.shift_type_id == ShiftType.id)
        .filter(SwapPreference.swap_request_id == swap.id)
        .all()
    )
    codes = [p.shift_type.code for p in prefs] if prefs else []
    return {
        "id": n.id,
        "user_id": n.user_id,
        "swap_request_id": n.swap_request_id,
        "created_at": n.created_at,
        "read_at": n.read_at,
        "requester_name": swap.requester.nome if swap.requester else None,
        "offered_shift_date": str(swap.shift.data),
        "offered_shift_code": swap.shift.codigo,
        "accepted_shift_types": codes,
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
    q = (
        db.query(SwapNotification)
        .filter(SwapNotification.user_id == current_user.id)
        .order_by(SwapNotification.created_at.desc())
    )
    if unread_only:
        q = q.filter(SwapNotification.read_at.is_(None))
    notifications = q.limit(100).all()
    return [_enrich_notification(db, n) for n in notifications]


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
