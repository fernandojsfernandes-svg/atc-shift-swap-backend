from pydantic import BaseModel


class ScheduleBase(BaseModel):
    ano: int
    mes: int
    team_id: int


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleRead(ScheduleBase):
    id: int

    class Config:
        from_attributes = True