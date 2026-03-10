from sqlalchemy import Column, Integer, String, Date, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from database import Base
from enum import Enum
from sqlalchemy import Enum as SQLEnum


class SwapStatus(str, Enum):
    OPEN = "OPEN"
    PROPOSED = "PROPOSED"
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
    nome = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)

    employee_number = Column(String, unique=True, index=True)

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
    data = Column(Date, nullable=False, index=True)
    codigo = Column(String, nullable=False, index=True)

    shift_type_id = Column(Integer, ForeignKey("shift_types.id"))

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("monthly_schedules.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "data", name="unique_user_day"),
    )

    user = relationship("User", back_populates="shifts")
    schedule = relationship("MonthlySchedule", back_populates="shifts")


class SwapRequest(Base):
    __tablename__ = "swap_requests"

    id = Column(Integer, primary_key=True, index=True)

    shift_id = Column(Integer, ForeignKey("shifts.id"))

    requester_id = Column(Integer, ForeignKey("users.id"))
    accepter_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    status = Column(
        SQLEnum(SwapStatus),
        default=SwapStatus.OPEN,
        nullable=False
    )

    shift = relationship("Shift")

    requester = relationship("User", foreign_keys=[requester_id])
    accepter = relationship("User", foreign_keys=[accepter_id])

    preferences = relationship("SwapPreference", back_populates="swap_request")


class ShiftType(Base):
    __tablename__ = "shift_types"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, index=True)


class SwapPreference(Base):
    __tablename__ = "swap_preferences"

    id = Column(Integer, primary_key=True)

    swap_request_id = Column(Integer, ForeignKey("swap_requests.id"))
    shift_type_id = Column(Integer, ForeignKey("shift_types.id"))

    swap_request = relationship("SwapRequest", back_populates="preferences")
    shift_type = relationship("ShiftType")


class CycleProposal(Base):
    __tablename__ = "cycle_proposals"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="PROPOSED")


class CycleSwap(Base):
    __tablename__ = "cycle_swaps"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("cycle_proposals.id"))
    swap_id = Column(Integer, ForeignKey("swap_requests.id"))


class CycleConfirmation(Base):
    __tablename__ = "cycle_confirmations"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("cycle_proposals.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    confirmed = Column(Boolean, default=False)