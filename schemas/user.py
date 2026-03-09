from pydantic import BaseModel


class UserBase(BaseModel):
    nome: str
    email: str
    employee_number: str
    team_id: int | None = None


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int

    class Config:
        orm_mode = True