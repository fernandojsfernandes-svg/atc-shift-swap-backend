from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, Boolean, Text
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

    # Notificações de pedidos de troca que o utilizador pode satisfazer (pode desativar)
    notifications_enabled = Column(Boolean, default=True)

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

    # Cor/bucket extraído do PDF (ex.: red, yellow, pink, gray_light, gray_dark, lime, ...)
    color_bucket = Column(String, nullable=True)
    # Estatuto de origem do turno (ex.: rota, troca_nav, troca_servico, bht, ts, outros)
    origin_status = Column(String, nullable=True)
    # Flag para inconsistência entre trocas aceites e escala importada
    inconsistency_flag = Column(Boolean, default=False)
    inconsistency_message = Column(String, nullable=True)

    shift_type_id = Column(Integer, ForeignKey("shift_types.id"))

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("monthly_schedules.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "data",
            name="unique_user_day",
            deferrable=True,
            initially="DEFERRED",
        ),
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
    direct_targets = relationship("SwapDirectTarget", back_populates="swap_request")


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


class SwapWantedOption(Base):
    __tablename__ = "swap_wanted_options"

    id = Column(Integer, primary_key=True, index=True)

    swap_request_id = Column(Integer, ForeignKey("swap_requests.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    shift_type_id = Column(Integer, ForeignKey("shift_types.id"), nullable=False)

    # relationships (no back_populates needed yet; read-only helper table)
    swap_request = relationship("SwapRequest")
    shift_type = relationship("ShiftType")


class SwapDirectTarget(Base):
    """
    Destinatários explícitos de um pedido de troca direta.
    Apenas estes utilizadores podem aceitar o pedido quando existirem entradas.
    """
    __tablename__ = "swap_direct_targets"

    id = Column(Integer, primary_key=True, index=True)
    swap_request_id = Column(Integer, ForeignKey("swap_requests.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    swap_request = relationship("SwapRequest", back_populates="direct_targets")
    user = relationship("User")


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


class SwapHistory(Base):
    """Registo de uma troca aceite (para histórico e eventual limpeza mensal)."""
    __tablename__ = "swap_history"

    id = Column(Integer, primary_key=True, index=True)
    swap_request_id = Column(Integer, ForeignKey("swap_requests.id"), nullable=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    accepter_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    shift_id_offered = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    shift_id_received = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    accepted_at = Column(DateTime, nullable=False)
    cycle_id = Column(Integer, ForeignKey("cycle_proposals.id"), nullable=True)


class SwapNotification(Base):
    """Notificação: pedido que pode aceitar (can_accept) ou pedido já satisfeito por outro (request_fulfilled)."""
    __tablename__ = "swap_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    swap_request_id = Column(Integer, ForeignKey("swap_requests.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    read_at = Column(DateTime, nullable=True)
    notification_kind = Column(String, default="can_accept", nullable=False)  # can_accept | request_fulfilled
    rejected_by_name = Column(String, nullable=True)
    # Troca «outros dias»: um aviso por turno concreto do aceitante que satisfaz o pedido
    accepter_shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True, index=True)
    # Pacote (várias datas): JSON array de shift ids do aceitante, ordenados por data
    package_accepter_shift_ids = Column(Text, nullable=True)
    # Mensagem fixa (ex.: resumo após aceitar troca em pacote); notification_kind = swap_accepted_summary
    body_text = Column(Text, nullable=True)

    user = relationship("User", backref="swap_notifications")
    swap_request = relationship("SwapRequest", backref="notifications")
    accepter_shift = relationship("Shift", foreign_keys=[accepter_shift_id])


class SwapActionHistory(Base):
    """
    Histórico persistente de ações no contexto de trocas: aceitar ou recusar.
    É por utilizador (actor) e exibe o turno proposto pelo requester (código do requester).
    """
    __tablename__ = "swap_action_history"

    id = Column(Integer, primary_key=True, index=True)

    swap_request_id = Column(Integer, ForeignKey("swap_requests.id"), nullable=False, index=True)

    action_type = Column(String, nullable=False)  # ACCEPTED | REJECTED

    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    offered_shift_code = Column(String, nullable=False, index=True)
    offered_shift_date = Column(Date, nullable=False, index=True)
    # Turno que o destinatário cedeu (antes da troca), p.ex. DC no mesmo dia que o M oferecido.
    accepter_shift_code = Column(String, nullable=True, index=True)
    # Pacote multi-perna (JSON): [{"requester_code","requester_date","accepter_code","accepter_date"}, ...]
    package_legs_json = Column(Text, nullable=True)
    # True se o pedido era troca direta (havia SwapDirectTarget) no momento da ação.
    direct_swap = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, nullable=False, index=True)

    actor = relationship("User", foreign_keys=[actor_id])
    requester = relationship("User", foreign_keys=[requester_id])
    swap_request = relationship("SwapRequest")


class SwapActionDismissal(Base):
    """Utilizador ocultou uma linha do histórico de ações (só na sua vista)."""

    __tablename__ = "swap_action_dismissals"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    swap_action_history_id = Column(
        Integer, ForeignKey("swap_action_history.id", ondelete="CASCADE"), primary_key=True
    )
    dismissed_at = Column(DateTime, nullable=False)