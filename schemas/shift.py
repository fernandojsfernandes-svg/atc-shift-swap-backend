from pydantic import BaseModel
from datetime import date


class ShiftBase(BaseModel):
    user_id: int
    schedule_id: int
    data: date
    codigo: str


class ShiftCreate(ShiftBase):
    pass


class ShiftRead(ShiftBase):
    id: int

    class Config:
        from_attributes = True