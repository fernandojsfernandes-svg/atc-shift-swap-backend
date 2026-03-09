from pydantic import BaseModel

class TeamBase(BaseModel):
    nome: str


class TeamCreate(TeamBase):
    pass


class TeamRead(TeamBase):
    id: int

    class Config:
        from_attributes = True  # necessário para SQLAlchemy