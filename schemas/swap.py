from datetime import date, datetime
from pydantic import BaseModel, ConfigDict
from models import SwapStatus


class SwapBase(BaseModel):
    shift_id: int


class WantedOption(BaseModel):
    date: date
    shift_types: list[str]


class SwapCreate(SwapBase):
    acceptable_shift_types: list[str] | None = None
    wanted_options: list[WantedOption] | None = None


class SwapRead(SwapBase):
    id: int
    requester_id: int
    status: SwapStatus

    model_config = ConfigDict(from_attributes=True)


class SwapHistoryRead(BaseModel):
    id: int
    swap_request_id: int | None
    requester_id: int
    accepter_id: int | None
    shift_id_offered: int
    shift_id_received: int
    accepted_at: datetime
    cycle_id: int | None

    model_config = ConfigDict(from_attributes=True)