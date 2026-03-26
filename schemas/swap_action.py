from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class SwapPackageLegRead(BaseModel):
    requester_code: str
    requester_date: str
    accepter_code: str
    accepter_date: str


class SwapActionHistoryRead(BaseModel):
    id: int
    swap_request_id: int
    action_type: str  # ACCEPTED | REJECTED

    actor_id: int
    requester_id: int

    offered_shift_code: str
    offered_shift_date: date
    accepter_shift_code: str | None = None

    requester_name: str
    actor_name: str

    created_at: datetime
    package_legs: list[SwapPackageLegRead] | None = None
    # True se o pedido era troca direta (SwapDirectTarget); a recusa fecha para todos os destinatários.
    direct_swap: bool = False

    model_config = ConfigDict(from_attributes=True)

