from pydantic import BaseModel, ConfigDict
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
    color_bucket: str | None = None
    inconsistency_flag: bool | None = None
    inconsistency_message: str | None = None
    origin_status: str | None = None

    model_config = ConfigDict(from_attributes=True)