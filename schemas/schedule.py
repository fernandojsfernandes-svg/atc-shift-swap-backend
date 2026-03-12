from pydantic import BaseModel, ConfigDict


class ScheduleBase(BaseModel):
    ano: int
    mes: int
    team_id: int


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleRead(ScheduleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)