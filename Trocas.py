from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from enum import Enum
from sqlalchemy import Enum as SQLEnum


class SwapStatus(str, Enum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True)

    users = relationship("User", back_populates="team")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, index=True)
    email = Column(String, unique=True, index=True)

    team_id = Column(Integer, ForeignKey("teams.id"))

    team = relationship("Team", back_populates="users")
    shifts = relationship("Shift", back_populates="user")


class MonthlySchedule(Base):
    __tablename__ = "monthly_schedules"

    id = Column(Integer, primary_key=True, index=True)
    mes = Column(Integer)
    ano = Column(Integer)

    team_id = Column(Integer, ForeignKey("teams.id"))

    shifts = relationship("Shift", back_populates="schedule")


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(Date, index=True)
    codigo = Column(String, index=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    schedule_id = Column(Integer, ForeignKey("monthly_schedules.id"))

    user = relationship("User", back_populates="shifts")
    schedule = relationship("MonthlySchedule", back_populates="shifts")


class SwapRequest(Base):
    __tablename__ = "swap_requests"

    id = Column(Integer, primary_key=True, index=True)

    shift_id = Column(Integer, ForeignKey("shifts.id"))
    requester_id = Column(Integer, ForeignKey("users.id"))

    status = Column(
        SQLEnum(SwapStatus),
        default=SwapStatus.OPEN,
        nullable=False
    )

    shift = relationship("Shift")
    requester = relationship("User")