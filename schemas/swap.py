from pydantic import BaseModel
from models import SwapStatus


class SwapBase(BaseModel):
    shift_id: int


class SwapCreate(SwapBase):
    acceptable_shift_types: list[str] | None = None


class SwapRead(SwapBase):
    id: int
    requester_id: int
    status: SwapStatus

    class Config:
        from_attributes = True