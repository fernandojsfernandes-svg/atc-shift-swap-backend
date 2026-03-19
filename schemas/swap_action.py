from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class SwapActionHistoryRead(BaseModel):
    id: int
    swap_request_id: int
    action_type: str  # ACCEPTED | REJECTED

    actor_id: int
    requester_id: int

    offered_shift_code: str
    offered_shift_date: date

    requester_name: str
    actor_name: str

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

