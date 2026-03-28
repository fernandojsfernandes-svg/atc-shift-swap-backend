from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    show_troca_bht: bool = False
    show_troca_ts: bool = False
    swap_partner_name: str | None = None
    swap_partner_employee_number: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ShiftManualUpdate(BaseModel):
    """Correção manual de um turno já existente (apenas dono autenticado)."""

    codigo: str = Field(..., max_length=32)
    color_bucket: str | None = None
    origin_status: str | None = None

    @field_validator("codigo")
    @classmethod
    def normalize_codigo(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("Código do turno em falta.")
        return s