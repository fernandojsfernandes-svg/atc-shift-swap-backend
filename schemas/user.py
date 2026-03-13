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
    notifications_enabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class UserPreferencesUpdate(BaseModel):
    notifications_enabled: bool | None = None