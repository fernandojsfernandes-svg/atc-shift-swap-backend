from datetime import datetime
from pydantic import BaseModel, ConfigDict

from schemas.swap import WantedOptionBrief


class NotificationRead(BaseModel):
    id: int
    user_id: int
    swap_request_id: int
    created_at: datetime
    read_at: datetime | None
    notification_kind: str = "can_accept"  # can_accept | request_fulfilled
    rejected_by_name: str | None = None
    body_text: str | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationWithSwapRead(NotificationRead):
    """Notificação com dados do pedido de troca para mostrar na UI."""
    requester_name: str | None = None
    offered_shift_date: str | None = None
    offered_shift_code: str | None = None
    accepted_shift_types: list[str] | None = None
    # Troca «outros dias»: em que dias e que tipos de turno o pedinte aceita receber (turnos do aceitante)
    wanted_options: list[WantedOptionBrief] | None = None
    # Quando a notificação é por combinação concreta (um turno seu):
    accepter_shift_date: str | None = None
    accepter_shift_code: str | None = None
    # Pacote multi-perna (várias datas em conjunto)
    accepter_package_legs: list[dict] | None = None
    requester_package_legs: list[dict] | None = None
