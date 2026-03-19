from datetime import date, datetime
from typing import Literal

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
    direct_target_ids: list[int] | None = None


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


class DirectTargetBrief(BaseModel):
    nome: str
    employee_number: str


class WantedOptionBrief(BaseModel):
    date: date
    shift_types: list[str]


class MySwapRequestRead(BaseModel):
    """Pedido criado pelo utilizador (lista «Os meus pedidos»)."""

    id: int
    status: SwapStatus
    kind: Literal["direct", "same_day", "other_days"]
    offered_shift_date: date
    offered_shift_code: str
    acceptable_shift_types: list[str] | None = None
    wanted_options: list[WantedOptionBrief] | None = None
    direct_targets: list[DirectTargetBrief] | None = None
    accepter_name: str | None = None