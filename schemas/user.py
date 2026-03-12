from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    nome: str
    email: str
    employee_number: str
    team_id: int | None = None


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)