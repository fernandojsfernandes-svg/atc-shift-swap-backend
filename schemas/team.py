from pydantic import BaseModel, ConfigDict


class TeamBase(BaseModel):
    nome: str


class TeamCreate(TeamBase):
    pass


class TeamRead(TeamBase):
    id: int

    model_config = ConfigDict(from_attributes=True)