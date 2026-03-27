import json

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, select, or_
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from collections import Counter, defaultdict

from database import get_db
from models import (
    SwapRequest,
    Shift,
    SwapStatus,
    User,
    ShiftType,
    SwapPreference,
    SwapWantedOption,
    SwapHistory,
    SwapNotification,
    SwapActionHistory,
    SwapActionDismissal,
    CycleProposal,
    CycleSwap,
    CycleConfirmation,
    SwapDirectTarget,
)
from services.notify_swap import notify_matching_users_same_day
from schemas.swap import (
    SwapCreate,
    SwapRead,
    SwapHistoryRead,
    MySwapRequestRead,
    DirectTargetBrief,
    WantedOptionBrief,
)
from schemas.swap_action import SwapActionHistoryRead, SwapPackageLegRead
from security import get_current_user
from rules.shift_rules import is_next_day_incompatible, exceeds_max_consecutive_days
from services.swap_engine import detect_swap_cycles
from services.multi_swap import validate_multi_swap_pairs
from services.proponent_create_validation import validate_proponent_swap_create

router = APIRouter(
    prefix="/swap-requests",
    tags=["Swap Requests"]
)

# Estilo «troca de serviço entre colegas» (cinzento escuro na UI) para turnos recebidos via troca.
_SWAP_COLOR_BUCKET = "gray_dark"
_SWAP_ORIGIN_STATUS = "troca_servico"

# Só BHT/TS mantêm vermelho/amarelo + cinzento na escala de quem recebe; o resto → cinzento escuro.
_SWAP_PRESERVE_ORIGIN_FOR_RECIPIENT = frozenset({"bht", "ts"})


def _history_package_json_from_pairs(pairs: list[tuple[Shift, Shift]] | None) -> str | None:
    """JSON para histórico quando aceite for pacote (≥2 pernas)."""
    if not pairs or len(pairs) < 2:
        return None
    legs = []
    for rs, as_ in sorted(pairs, key=lambda p: (p[0].data, p[0].id)):
        legs.append(
            {
                "requester_code": rs.codigo,
                "requester_date": str(rs.data),
                "accepter_code": as_.codigo,
                "accepter_date": str(as_.data),
            }
        )
    return json.dumps(legs, ensure_ascii=False)


def _parse_action_package_legs_row(r: SwapActionHistory) -> list[SwapPackageLegRead] | None:
    raw = getattr(r, "package_legs_json", None)
    if not raw:
        return None
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list) or len(arr) < 2:
            return None
        out: list[SwapPackageLegRead] = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            out.append(SwapPackageLegRead.model_validate(item))
        return out if len(out) >= 2 else None
    except Exception:
        return None


def _swap_pair_update_sql():
    """
    Troca só os donos dos dois registos de turno.

    O turno oferecido pelo pedinte mantém bucket/origin (ex.: BHT para o aceitante).
    O turno recebido pelo pedinte é estilizado depois em _mark_received_shift_as_colleague_swap.
    """
    return text(
        """
        UPDATE shifts
        SET user_id = CASE
            WHEN id = :accepter_shift_id THEN :requester_id
            WHEN id = :original_shift_id THEN :accepter_id
            ELSE user_id
        END
        WHERE id IN (:accepter_shift_id, :original_shift_id)
        """
    )


def _mark_received_shift_as_colleague_swap(db: Session, accepter_shift_id: int) -> None:
    """
    Turno que, após a troca, fica com o **outro** colega (troca de serviço): `troca_servico` +
    cinzento escuro, exceto se já era BHT ou TS (mantém vermelho/amarelo).

    Chamar para **ambos** os registos trocados: o que era do aceitante e passou para o pedinte,
    e o que era do pedinte e passou para o aceitante (ex.: o T que o José recebe do Sérgio).
    """
    sh = db.get(Shift, accepter_shift_id)
    if not sh:
        return
    os = (sh.origin_status or "").strip().lower()
    if os in _SWAP_PRESERVE_ORIGIN_FOR_RECIPIENT:
        return
    sh.origin_status = _SWAP_ORIGIN_STATUS
    sh.color_bucket = _SWAP_COLOR_BUCKET


def _swap_accept_summary_messages(
    requester_name: str,
    accepter_name: str,
    multileg_pairs: list[tuple[Shift, Shift]] | None,
    original_shift: Shift,
    accepter_shift: Shift,
) -> tuple[str, str]:
    """
    Texto para o pedinte e para o aceitante após aceitar (troca simples ou pacote).
    Usa os códigos dos turnos tal como estavam antes da troca (codigo não muda na BD).
    """

    def fmt_d(d) -> str:
        if hasattr(d, "strftime"):
            return d.strftime("%d/%m")
        return str(d)[:10]

    if multileg_pairs and len(multileg_pairs) > 0:
        legs = sorted(multileg_pairs, key=lambda p: (p[0].data, p[0].id))
        req_parts: list[str] = []
        acp_parts: list[str] = []
        for rs, as_ in legs:
            ds = fmt_d(rs.data)
            rc = (rs.codigo or "").strip()
            ac = (as_.codigo or "").strip()
            req_parts.append(f"Dia {ds} trocou o seu {rc} por {ac}")
            acp_parts.append(f"Dia {ds} trocou o seu {ac} por {rc}")
        req_msg = (
            f"{accepter_name} aceitou o pedido do pacote de troca. "
            + " e ".join(req_parts)
            + "."
        )
        acp_msg = (
            f"Aceitou o pedido do pacote de troca com {requester_name}. "
            + " e ".join(acp_parts)
            + "."
        )
        return req_msg, acp_msg

    ds = fmt_d(original_shift.data)
    oc = (original_shift.codigo or "").strip()
    ac = (accepter_shift.codigo or "").strip()
    req_msg = (
        f"{accepter_name} aceitou o pedido de troca. Dia {ds} trocou o seu {oc} por {ac}."
    )
    acp_msg = (
        f"Aceitou o pedido de troca com {requester_name}. Dia {ds} trocou o seu {ac} por {oc}."
    )
    return req_msg, acp_msg


def _notification_package_shift_ids(notif: SwapNotification) -> list[int] | None:
    raw = getattr(notif, "package_accepter_shift_ids", None)
    if not raw:
        return None
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list) or not arr:
            return None
        return [int(x) for x in arr]
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _build_multileg_pairs_from_package(
    db: Session,
    swap: SwapRequest,
    original_shift: Shift,
    package_accepter_ids: list[int],
    accepter_user_id: int,
) -> list[tuple[Shift, Shift]] | None:
    """
    Constrói (turno pedinte, turno aceitante) a partir dos turnos do aceitante no pacote.
    O pacote só inclui as datas efectivamente combinadas (não cobre todas as opções «ou»).
    """
    accepter_shifts = [db.get(Shift, sid) for sid in package_accepter_ids]
    if not all(accepter_shifts):
        return None
    for sh in accepter_shifts:
        if not sh or sh.user_id != accepter_user_id:
            return None
    accepter_shifts.sort(key=lambda s: s.data)
    offer_date = original_shift.data
    pairs: list[tuple[Shift, Shift]] = []
    for ashift in accepter_shifts:
        if not _accepter_shift_matches_wanted(db, swap.id, ashift):
            return None
        d = ashift.data
        if d == offer_date:
            rs = original_shift
        else:
            rs = (
                db.query(Shift)
                .filter(Shift.user_id == swap.requester_id, Shift.data == d)
                .first()
            )
            if not rs:
                return None
        pairs.append((rs, ashift))
    return pairs


def _accepter_shift_matches_wanted(db: Session, swap_id: int, accepter_shift: Shift) -> bool:
    rows = (
        db.query(SwapWantedOption, ShiftType.code)
        .join(ShiftType, SwapWantedOption.shift_type_id == ShiftType.id)
        .filter(
            SwapWantedOption.swap_request_id == swap_id,
            SwapWantedOption.date == accepter_shift.data,
        )
        .all()
    )
    if not rows:
        return False
    allowed_ids = {r[0].shift_type_id for r in rows}
    allowed_codes = {(r[1] or "").strip() for r in rows}
    if accepter_shift.shift_type_id and accepter_shift.shift_type_id in allowed_ids:
        return True
    return (accepter_shift.codigo or "").strip() in allowed_codes


def _shifts_after_swap(shifts: list[Shift], give_away_id: int, receive_shift: Shift, new_user_id: int):
    """
    Devolve lista em memória com os turnos após a troca:
    - remove o turno com id == give_away_id
    - adiciona o turno receive_shift com user_id = new_user_id
    """
    result: list[SimpleNamespace] = []
    for s in shifts:
        if s.id == give_away_id:
            continue
        result.append(SimpleNamespace(data=s.data, codigo=s.codigo, user_id=new_user_id))
    result.append(SimpleNamespace(data=receive_shift.data, codigo=receive_shift.codigo, user_id=new_user_id))
    result.sort(key=lambda s: s.data)
    return result


def _has_two_shifts_same_day(shifts_mem: list[SimpleNamespace]) -> bool:
    counter = Counter((s.user_id, s.data) for s in shifts_mem)
    return any(count > 1 for count in counter.values())


def _violates_next_day_rule(shifts_mem: list[SimpleNamespace]) -> bool:
    n = len(shifts_mem)
    for i in range(n - 1):
        today = shifts_mem[i]
        tomorrow = shifts_mem[i + 1]
        if (tomorrow.data - today.data).days == 1:
            if is_next_day_incompatible(today.codigo, tomorrow.codigo):
                return True
    return False


def _validate_cycle_execution(db: Session, shifts: list, users: list) -> None:
    """
    Validates that executing the cycle would not break operational rules.
    Raises HTTPException if invalid (same-day double shift; T or Mt followed by N next day; or >9 consecutive working days).
    """
    n = len(shifts)
    if n != len(users):
        raise HTTPException(status_code=400, detail="Invalid cycle data")

    # Load all current shifts for each user in the cycle
    user_shifts_map = {}
    for uid in users:
        user_shifts_map[uid] = db.query(Shift).filter(Shift.user_id == uid).all()

    # After cycle: user at index k gives shifts[k], receives shifts[(k+1) % n]
    for k in range(n):
        uid = users[k]
        give_away = shifts[k]
        receive = shifts[(k + 1) % n]
        resulting = [s for s in user_shifts_map[uid] if s.id != give_away.id] + [receive]

        # 1) No two shifts on same day
        by_date = {}
        for s in resulting:
            by_date.setdefault(s.data, []).append(s)
        for d, shs in by_date.items():
            if len(shs) > 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cycle would give user {uid} more than one shift on the same day"
                )

        # 2) Only T and Mt cannot have N the next day
        resulting_sorted = sorted(resulting, key=lambda s: s.data)
        for i in range(len(resulting_sorted) - 1):
            today_s = resulting_sorted[i]
            next_s = resulting_sorted[i + 1]
            if (next_s.data - today_s.data).days != 1:
                continue
            if is_next_day_incompatible(today_s.codigo, next_s.codigo):
                raise HTTPException(
                    status_code=400,
                    detail="Cycle would create forbidden sequence: only T and Mt cannot have N the next day"
                )

        # 3) Max 9 consecutive working days
        if exceeds_max_consecutive_days(resulting):
            raise HTTPException(
                status_code=400,
                detail="Cycle would exceed 9 consecutive working days for one or more users"
            )


# 🔹 CREATE SWAP (SEGURA)
@router.post("/", response_model=SwapRead)
def create_swap_request(
    swap: SwapCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only create a swap for your own shift")

    from datetime import date

    if shift.data < date.today():
        raise HTTPException(
            status_code=400,
            detail="Cannot create swap for past shifts"
        )

    # verificar se turno já está numa proposta de ciclo
    existing_cycle = db.query(CycleSwap).join(
        SwapRequest, CycleSwap.swap_id == SwapRequest.id
    ).join(
        CycleProposal, CycleSwap.cycle_id == CycleProposal.id
    ).filter(
        SwapRequest.shift_id == swap.shift_id,
        CycleProposal.status == "PROPOSED"
    ).first()

    if existing_cycle:
        raise HTTPException(
            status_code=400,
            detail="This shift is already part of a pending cycle proposal"
        )

    # Troca direta: não pode incluir-se a si próprio; cada destinatário tem de ter turno no dia;
    # a troca tem de cumprir as mesmas regras que no aceite (T/Mt→N, dias consecutivos, etc.).
    if swap.direct_target_ids:
        other_ids = [uid for uid in swap.direct_target_ids if uid != current_user.id]
        if not other_ids:
            raise HTTPException(
                status_code=400,
                detail="Não pode fazer um pedido de troca direta a si próprio. Escolha pelo menos um colega.",
            )
        for uid in other_ids:
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                raise HTTPException(
                    status_code=400,
                    detail="Um dos destinatários indicados não existe na base de dados.",
                )
            accepter_shift = db.query(Shift).filter(
                Shift.user_id == uid,
                Shift.data == shift.data,
            ).first()
            if not accepter_shift:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{user.nome} não tem turno na escala no dia {shift.data}. "
                        "Sem turno desse colega nesse dia não há troca direta possível."
                    ),
                )
            if not validate_multi_swap_pairs(
                db,
                current_user.id,
                uid,
                [(shift, accepter_shift)],
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"A troca direta com {user.nome} viola as regras em vigor "
                        "(ex.: T ou Mt seguidos de N no dia seguinte, ou mais de 9 dias consecutivos de trabalho)."
                    ),
                )

    if not swap.direct_target_ids:
        validate_proponent_swap_create(db, swap, shift, current_user.id)

    # Vários pedidos OPEN para o mesmo turno são permitidos (várias combinações em paralelo).
    # Quando um for aceite, accept_swap encerra os restantes para esse shift_id.

    new_swap = SwapRequest(
        shift_id=swap.shift_id,
        requester_id=current_user.id,
        status=SwapStatus.OPEN
    )

    db.add(new_swap)
    db.flush()  # need new_swap.id for preferences / direct targets

    if swap.acceptable_shift_types:
        for code in swap.acceptable_shift_types:
            shift_type = db.query(ShiftType).filter(ShiftType.code == code.strip()).first()
            if shift_type:
                db.add(SwapPreference(
                    swap_request_id=new_swap.id,
                    shift_type_id=shift_type.id
                ))

    # gravar opções de dias/tipos desejados, se existirem
    if swap.wanted_options:
        for opt in swap.wanted_options:
            for code in opt.shift_types:
                shift_type = db.query(ShiftType).filter(ShiftType.code == code.strip()).first()
                if not shift_type:
                    continue
                db.add(SwapWantedOption(
                    swap_request_id=new_swap.id,
                    date=opt.date,
                    shift_type_id=shift_type.id
                ))
        # Várias datas: as linhas «outras» são alternativas (OU); não exigimos turno em todas.
        # Quem notifica valida combinações reais (oferta + um dia extra onde o pedinte tenha escala).

    # alvos diretos (troca direta)
    if swap.direct_target_ids:
        now = datetime.utcnow()
        for uid in swap.direct_target_ids:
            if uid == current_user.id:
                continue
            user = db.query(User).filter(User.id == uid).first()
            if not user:
                raise HTTPException(
                    status_code=400,
                    detail="Destinatário de troca direta inválido.",
                )
            db.add(SwapDirectTarget(
                swap_request_id=new_swap.id,
                user_id=user.id,
            ))
            if getattr(user, "notifications_enabled", True):
                db.add(SwapNotification(
                    user_id=user.id,
                    swap_request_id=new_swap.id,
                    created_at=now,
                ))

    db.commit()
    db.refresh(new_swap)

    # Só notificar por matching quando NÃO for troca direta
    if not swap.direct_target_ids:
        try:
            notify_matching_users_same_day(db, new_swap)
            db.commit()
        except Exception:
            db.rollback()

    return new_swap


# 🔹 ACCEPT SWAP
@router.post("/{swap_id}/accept")
def accept_swap(
    swap_id: int,
    notification_id: int | None = Query(None),
    confirm_incompatibility: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    swap = db.query(SwapRequest).filter(SwapRequest.id == swap_id).first()

    if not swap:
        raise HTTPException(status_code=404, detail="Swap request not found")

    if swap.status != SwapStatus.OPEN:
        raise HTTPException(status_code=400, detail="Swap already processed")

    # Se houver destinatários diretos, apenas eles podem aceitar
    direct_target_ids = [r.user_id for r in db.query(SwapDirectTarget).filter(SwapDirectTarget.swap_request_id == swap.id).all()]
    if direct_target_ids and current_user.id not in direct_target_ids:
        raise HTTPException(
            status_code=403,
            detail="This swap request is directed to specific users and you are not one of them",
        )

    if swap.requester_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot accept your own swap"
        )

    original_shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()

    if not original_shift:
        raise HTTPException(status_code=404, detail="Original shift not found")

    # O turno oferecido tem de pertencer ainda ao pedinte (não bloquear por trocas antigas
    # no mesmo registo de turno — após várias trocas o mesmo shift_id pode ter histórico ACCEPTED).
    if original_shift.user_id != swap.requester_id:
        raise HTTPException(
            status_code=400,
            detail="Este pedido já não é válido: o turno já não pertence a quem o pediu.",
        )

    wanted_count = (
        db.query(SwapWantedOption.id)
        .filter(SwapWantedOption.swap_request_id == swap.id)
        .count()
    )

    multileg_pairs: list[tuple[Shift, Shift]] | None = None
    accepter_shift: Shift | None = None
    if notification_id is not None:
        notif = (
            db.query(SwapNotification)
            .filter(SwapNotification.id == notification_id)
            .first()
        )
        if (
            not notif
            or notif.user_id != current_user.id
            or notif.swap_request_id != swap.id
        ):
            raise HTTPException(status_code=404, detail="Notificação inválida.")
        pkg_ids = _notification_package_shift_ids(notif)
        if pkg_ids:
            if wanted_count == 0:
                raise HTTPException(status_code=400, detail="Pedido sem opções de troca.")
            multileg_pairs = _build_multileg_pairs_from_package(
                db, swap, original_shift, pkg_ids, current_user.id
            )
            if not multileg_pairs:
                raise HTTPException(
                    status_code=400,
                    detail="O pacote desta notificação já não é válido (verifique as suas escalas).",
                )
            for rs, as_ in multileg_pairs:
                if rs.user_id != swap.requester_id or as_.user_id != current_user.id:
                    raise HTTPException(
                        status_code=400,
                        detail="O pacote desta notificação já não é válido.",
                    )
            if not validate_multi_swap_pairs(
                db, swap.requester_id, current_user.id, multileg_pairs
            ):
                raise HTTPException(
                    status_code=400,
                    detail="O pacote viola regras de escalas (sequência T/Mt→N ou dias consecutivos).",
                )
            accepter_shift = next(
                as_ for rs, as_ in multileg_pairs if rs.id == original_shift.id
            )
        elif notif.accepter_shift_id:
            accepter_shift = db.get(Shift, notif.accepter_shift_id)
            if (
                not accepter_shift
                or accepter_shift.user_id != current_user.id
                or not _accepter_shift_matches_wanted(db, swap.id, accepter_shift)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="O turno indicado na notificação já não é válido para este pedido.",
                )
        elif wanted_count > 0:
            raise HTTPException(
                status_code=400,
                detail="Use a notificação atualizada que associa o seu turno concreto ao pedido.",
            )

    if accepter_shift is None:
        if wanted_count > 0:
            raise HTTPException(
                status_code=400,
                detail="Para este pedido deve aceitar a partir da notificação (com o seu turno indicado).",
            )
        accepter_shift = db.query(Shift).filter(
            Shift.user_id == current_user.id,
            Shift.data == original_shift.data,
        ).first()

    if not accepter_shift:
        raise HTTPException(
            status_code=400,
            detail="You do not have a shift on this date",
        )

    # No dia do turno oferecido, o aceitante ficará com original_shift.codigo
    incoming_on_offer_day = original_shift.codigo
    next_day = original_shift.data + timedelta(days=1)

    next_shift = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.data == next_day
    ).first()

    if next_shift:

        tomorrow_code = next_shift.codigo

        if is_next_day_incompatible(incoming_on_offer_day, tomorrow_code):

            if not confirm_incompatibility:
                raise HTTPException(
                    status_code=409,
                    detail="A troca não é permitida: tem T ou Mt no dia em que receberia o turno e tem N no dia seguinte (regra: T e Mt não podem ser seguidos de N)."
                )

    # Verificar preferências de turno
    preferences = db.query(SwapPreference).filter(
        SwapPreference.swap_request_id == swap.id
    ).all()

    if preferences:
        allowed_types = [p.shift_type_id for p in preferences]

        if accepter_shift.shift_type_id not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Your shift type is not accepted for this swap"
            )

    try:

        requester_id = swap.requester_id
        accepter_id = current_user.id

        if multileg_pairs:
            if not validate_multi_swap_pairs(
                db, requester_id, accepter_id, multileg_pairs
            ):
                raise HTTPException(
                    status_code=400,
                    detail="A troca em pacote já não é válida.",
                )
            for rs, as_ in multileg_pairs:
                db.execute(
                    _swap_pair_update_sql(),
                    {
                        "accepter_shift_id": as_.id,
                        "original_shift_id": rs.id,
                        "requester_id": requester_id,
                        "accepter_id": accepter_id,
                    },
                )
            db.flush()
            for rs, as_ in multileg_pairs:
                _mark_received_shift_as_colleague_swap(db, as_.id)
                _mark_received_shift_as_colleague_swap(db, rs.id)
            primary_received = accepter_shift
        else:
            # Shifts atuais de cada utilizador antes da troca
            requester_shifts = db.query(Shift).filter(Shift.user_id == requester_id).all()
            accepter_shifts = db.query(Shift).filter(Shift.user_id == accepter_id).all()

            # Listas em memória após a troca
            requester_after = _shifts_after_swap(
                requester_shifts,
                give_away_id=original_shift.id,
                receive_shift=accepter_shift,
                new_user_id=requester_id,
            )
            accepter_after = _shifts_after_swap(
                accepter_shifts,
                give_away_id=accepter_shift.id,
                receive_shift=original_shift,
                new_user_id=accepter_id,
            )

            # 1) Não pode haver 2 turnos no mesmo dia
            if _has_two_shifts_same_day(requester_after) or _has_two_shifts_same_day(accepter_after):
                raise HTTPException(
                    status_code=400,
                    detail="A troca não é permitida porque algum utilizador ficaria com dois turnos no mesmo dia."
                )

            # 2) Regra T/Mt -> N
            if _violates_next_day_rule(requester_after) or _violates_next_day_rule(accepter_after):
                raise HTTPException(
                    status_code=400,
                    detail="A troca não é permitida: criaria uma sequência T ou Mt seguidos de N no dia seguinte."
                )

            # 3) Regra 9 dias consecutivos
            if exceeds_max_consecutive_days(requester_after) or exceeds_max_consecutive_days(accepter_after):
                raise HTTPException(
                    status_code=400,
                    detail="A troca não é permitida: criaria mais de 9 dias consecutivos de trabalho para algum utilizador."
                )

            # Se chegou aqui, o estado 'depois da troca' é válido → agora sim gravamos na BD.
            # A constraint unique_user_day é DEFERRABLE, por isso só será verificada no commit.
            db.execute(
                _swap_pair_update_sql(),
                {
                    "accepter_shift_id": accepter_shift.id,
                    "original_shift_id": original_shift.id,
                    "requester_id": requester_id,
                    "accepter_id": accepter_id,
                },
            )
            db.flush()
            _mark_received_shift_as_colleague_swap(db, accepter_shift.id)
            _mark_received_shift_as_colleague_swap(db, original_shift.id)
            primary_received = accepter_shift

        swap.accepter_id = accepter_id
        swap.status = SwapStatus.ACCEPTED

        other_opens = db.query(SwapRequest).filter(
            SwapRequest.shift_id == original_shift.id,
            SwapRequest.id != swap.id,
            SwapRequest.status == SwapStatus.OPEN
        ).all()
        db.query(SwapRequest).filter(
            SwapRequest.shift_id == original_shift.id,
            SwapRequest.id != swap.id,
            SwapRequest.status == SwapStatus.OPEN
        ).update({"status": SwapStatus.REJECTED})
        now = datetime.utcnow()

        # Marcar notificações antigas (dos pedidos que ficaram rejeitados) como lidas,
        # para a UI deixar de mostrar "Aceitar/Recusar" em pedidos já fechados.
        if other_opens:
            other_ids = [o.id for o in other_opens]
            db.query(SwapNotification).filter(
                SwapNotification.swap_request_id.in_(other_ids)
            ).update({"read_at": now}, synchronize_session=False)

        # Marcar notificações antigas deste swap como lidas (para a UI não manter ações pendentes).
        db.query(SwapNotification).filter(
            SwapNotification.swap_request_id == swap.id
        ).update({"read_at": now}, synchronize_session=False)
        for other in other_opens:
            for t in db.query(SwapDirectTarget).filter(SwapDirectTarget.swap_request_id == other.id).all():
                if t.user_id == accepter_id:
                    continue
                target_user = db.query(User).filter(User.id == t.user_id).first()
                if target_user and getattr(target_user, "notifications_enabled", True):
                    db.add(SwapNotification(
                        user_id=t.user_id,
                        swap_request_id=swap.id,
                        created_at=now,
                        notification_kind="request_fulfilled",
                    ))

        db.add(SwapHistory(
            swap_request_id=swap.id,
            requester_id=requester_id,
            accepter_id=accepter_id,
            shift_id_offered=original_shift.id,
            shift_id_received=primary_received.id,
            accepted_at=datetime.utcnow(),
        ))

        # Registar ação do utilizador destinatário
        db.add(
            SwapActionHistory(
                swap_request_id=swap.id,
                action_type="ACCEPTED",
                actor_id=accepter_id,
                requester_id=requester_id,
                offered_shift_code=original_shift.codigo,
                offered_shift_date=original_shift.data,
                accepter_shift_code=(primary_received.codigo or "").strip() or None,
                created_at=datetime.utcnow(),
                package_legs_json=_history_package_json_from_pairs(multileg_pairs),
                direct_swap=bool(direct_target_ids),
            )
        )

        req_user = db.query(User).filter(User.id == requester_id).first()
        acp_user = db.query(User).filter(User.id == accepter_id).first()
        rn = (req_user.nome or "").strip() if req_user else ""
        an = (acp_user.nome or "").strip() if acp_user else ""
        if not rn:
            rn = "O pedinte"
        if not an:
            an = "O aceitante"
        sum_req, sum_acp = _swap_accept_summary_messages(
            rn, an, multileg_pairs, original_shift, accepter_shift
        )
        summary_at = datetime.utcnow()
        if req_user and getattr(req_user, "notifications_enabled", True):
            db.add(
                SwapNotification(
                    user_id=requester_id,
                    swap_request_id=swap.id,
                    created_at=summary_at,
                    notification_kind="swap_accepted_summary",
                    body_text=sum_req,
                )
            )
        if acp_user and getattr(acp_user, "notifications_enabled", True):
            db.add(
                SwapNotification(
                    user_id=accepter_id,
                    swap_request_id=swap.id,
                    created_at=summary_at,
                    notification_kind="swap_accepted_summary",
                    body_text=sum_acp,
                )
            )

        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print("Swap error:", e)
        raise HTTPException(status_code=500, detail="Swap transaction failed")

    return {"message": "Swap completed successfully"}


@router.post("/{swap_id}/reject")
def reject_swap(
    swap_id: int,
    notification_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    O destinatário indica que não aceita este pedido para si.

    - **Sem troca direta** (mesmo dia / outros dias para quem o sistema notifica vários colegas):
      o pedido **permanece OPEN**; outros podem aceitar. Só fecha com aceitação, cancelamento
      pelo proponente, ou recusas de *todos* os destinatários de troca direta (ver abaixo).

    - **Troca direta** (`SwapDirectTarget`): só os utilizadores indicados podem aceitar.
      Quando **todos** esses destinatários tiverem recusado, o pedido fecha (`REJECTED`).
      Caso típico: um único destinatário — uma recusa fecha o pedido.
    """
    swap = db.query(SwapRequest).filter(SwapRequest.id == swap_id).first()
    if not swap:
        raise HTTPException(status_code=404, detail="Swap request not found")

    if swap.status != SwapStatus.OPEN:
        raise HTTPException(status_code=400, detail="Swap already processed")

    if swap.requester_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot reject your own swap request")

    wanted_count = (
        db.query(SwapWantedOption.id)
        .filter(SwapWantedOption.swap_request_id == swap.id)
        .count()
    )

    direct_target_ids = [
        r.user_id
        for r in db.query(SwapDirectTarget).filter(SwapDirectTarget.swap_request_id == swap.id).all()
    ]
    if direct_target_ids and current_user.id not in direct_target_ids:
        raise HTTPException(
            status_code=403,
            detail="This swap request is directed to specific users and you are not one of them",
        )

    notif: SwapNotification | None = None
    if notification_id is not None:
        notif = (
            db.query(SwapNotification)
            .filter(SwapNotification.id == notification_id)
            .first()
        )
        if not notif or notif.user_id != current_user.id or notif.swap_request_id != swap.id:
            raise HTTPException(status_code=400, detail="Notificação inválida para este pedido.")
        pkg_ids = _notification_package_shift_ids(notif)
        if wanted_count > 0 and not (notif.accepter_shift_id or pkg_ids):
            raise HTTPException(
                status_code=400,
                detail="Para este tipo de pedido deve recusar a partir da notificação (turno concreto).",
            )
    elif wanted_count > 0:
        raise HTTPException(
            status_code=400,
            detail="Para este tipo de pedido deve recusar a partir da notificação (turno concreto).",
        )

    offered_shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()
    if not offered_shift:
        raise HTTPException(status_code=404, detail="Original shift not found")

    ac_shift_reject = (
        db.query(Shift)
        .filter(
            Shift.user_id == current_user.id,
            Shift.data == offered_shift.data,
        )
        .first()
    )
    ac_code_reject = (ac_shift_reject.codigo or "").strip() if ac_shift_reject else None

    now = datetime.utcnow()

    if notif is not None:
        notif.read_at = now
    else:
        db.query(SwapNotification).filter(
            SwapNotification.swap_request_id == swap.id,
            SwapNotification.user_id == current_user.id,
        ).update({"read_at": now})

    db.add(
        SwapActionHistory(
            swap_request_id=swap.id,
            action_type="REJECTED",
            actor_id=current_user.id,
            requester_id=swap.requester_id,
            offered_shift_code=offered_shift.codigo,
            offered_shift_date=offered_shift.data,
            accepter_shift_code=ac_code_reject,
            created_at=now,
            direct_swap=bool(direct_target_ids),
        )
    )
    db.flush()

    # Troca direta: só estes utilizadores podem aceitar — quando todos tiverem recusado, fecha o pedido.
    closes_direct = False
    if direct_target_ids:
        rejected_ids = {
            r.actor_id
            for r in db.query(SwapActionHistory)
            .filter(
                SwapActionHistory.swap_request_id == swap.id,
                SwapActionHistory.action_type == "REJECTED",
                SwapActionHistory.actor_id.in_(direct_target_ids),
            )
            .all()
        }
        if set(direct_target_ids) <= rejected_ids:
            closes_direct = True
            swap.status = SwapStatus.REJECTED
            db.query(SwapNotification).filter(
                SwapNotification.swap_request_id == swap.id,
                SwapNotification.user_id != swap.requester_id,
            ).update({"read_at": now})
            requester = db.query(User).filter(User.id == swap.requester_id).first()
            if requester and getattr(requester, "notifications_enabled", True):
                db.add(
                    SwapNotification(
                        user_id=swap.requester_id,
                        swap_request_id=swap.id,
                        created_at=now,
                        notification_kind="request_rejected",
                        rejected_by_name=(
                            current_user.nome if len(direct_target_ids) == 1 else None
                        ),
                    )
                )

    db.commit()
    if closes_direct:
        return {
            "message": (
                "Recusou a troca direta. Não há mais destinatários que possam aceitar — "
                "o pedido foi fechado. O proponente foi notificado."
            ),
        }
    return {
        "message": (
            "Indicou que não aceita este pedido. O pedido continua aberto para outros colegas "
            "(só o proponente pode cancelar o pedido)."
        ),
    }


@router.post("/actions/{action_id}/dismiss")
def dismiss_swap_action(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a linha do histórico de ações só para o utilizador atual."""
    row = db.query(SwapActionHistory).filter(SwapActionHistory.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Registo não encontrado")
    if current_user.id not in (row.actor_id, row.requester_id):
        raise HTTPException(status_code=403, detail="Sem permissão para apagar este registo")
    existing = (
        db.query(SwapActionDismissal)
        .filter(
            SwapActionDismissal.user_id == current_user.id,
            SwapActionDismissal.swap_action_history_id == action_id,
        )
        .first()
    )
    if existing:
        return {"message": "Já não consta no seu histórico."}
    db.add(
        SwapActionDismissal(
            user_id=current_user.id,
            swap_action_history_id=action_id,
            dismissed_at=datetime.utcnow(),
        )
    )
    db.commit()
    return {"message": "Removido do seu histórico."}


@router.get("/actions/me", response_model=list[SwapActionHistoryRead])
def list_my_swap_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Histórico das minhas ações como destinatário:
    - Aceito / Recusado em pedidos de troca.
    Mostra o código do turno oferecido pelo requester (swap.shift).
    """
    dismissed_ids = [
        x[0]
        for x in db.query(SwapActionDismissal.swap_action_history_id)
        .filter(SwapActionDismissal.user_id == current_user.id)
        .all()
    ]
    q = (
        db.query(SwapActionHistory)
        .options(
            joinedload(SwapActionHistory.requester),
            joinedload(SwapActionHistory.actor),
        )
        .filter(
            (SwapActionHistory.actor_id == current_user.id)
            | (SwapActionHistory.requester_id == current_user.id)
        )
    )
    if dismissed_ids:
        q = q.filter(SwapActionHistory.id.notin_(dismissed_ids))
    rows = q.order_by(SwapActionHistory.created_at.desc()).limit(200).all()

    unique_swap_ids = list({r.swap_request_id for r in rows})
    direct_swap_ids: set[int] = set()
    if unique_swap_ids:
        stmt = (
            select(SwapDirectTarget.swap_request_id)
            .where(SwapDirectTarget.swap_request_id.in_(unique_swap_ids))
            .distinct()
        )
        direct_swap_ids = set(db.scalars(stmt).all())

    return [
        SwapActionHistoryRead(
            id=r.id,
            swap_request_id=r.swap_request_id,
            action_type=r.action_type,
            actor_id=r.actor_id,
            requester_id=r.requester_id,
            offered_shift_code=r.offered_shift_code,
            offered_shift_date=r.offered_shift_date,
            accepter_shift_code=getattr(r, "accepter_shift_code", None),
            requester_name=r.requester.nome if r.requester else "",
            actor_name=r.actor.nome if r.actor else "",
            created_at=r.created_at,
            package_legs=_parse_action_package_legs_row(r),
            # Coluna gravada na ação (fiável) + fallback para histórico antigo
            direct_swap=bool(getattr(r, "direct_swap", False))
            or (r.swap_request_id in direct_swap_ids),
        )
        for r in rows
    ]


def _build_my_swap_request_reads(db: Session, swaps: list[SwapRequest]) -> list[MySwapRequestRead]:
    """Serializa pedidos do utilizador para a lista «Os meus pedidos»."""
    if not swaps:
        return []

    swap_ids = [s.id for s in swaps]
    wanted_rows = (
        db.query(SwapWantedOption)
        .filter(SwapWantedOption.swap_request_id.in_(swap_ids))
        .options(joinedload(SwapWantedOption.shift_type))
        .all()
    )
    wanted_map: dict[int, dict] = {}
    for w in wanted_rows:
        sid = w.swap_request_id
        if sid not in wanted_map:
            wanted_map[sid] = defaultdict(set)
        code = w.shift_type.code if w.shift_type else "?"
        wanted_map[sid][w.date].add(code)

    out: list[MySwapRequestRead] = []
    for s in swaps:
        shift = s.shift
        if not shift:
            continue
        direct_list = list(s.direct_targets) if s.direct_targets else []
        if direct_list:
            kind = "direct"
            targets = []
            for t in direct_list:
                if not t.user:
                    continue
                ash = (
                    db.query(Shift)
                    .filter(Shift.user_id == t.user_id, Shift.data == shift.data)
                    .first()
                )
                their = (ash.codigo or "").strip() if ash else ""
                targets.append(
                    DirectTargetBrief(
                        nome=t.user.nome or "",
                        employee_number=(t.user.employee_number or "").strip(),
                        their_shift_code=their or None,
                    )
                )
            acceptable = None
            wanted_opts = None
        elif s.id in wanted_map and wanted_map[s.id]:
            kind = "other_days"
            wanted_opts = [
                WantedOptionBrief(date=d, shift_types=sorted(codes))
                for d, codes in sorted(wanted_map[s.id].items())
            ]
            acceptable = None
            targets = None
        else:
            kind = "same_day"
            prefs = list(s.preferences) if s.preferences else []
            acceptable = [p.shift_type.code for p in prefs if p.shift_type] or None
            wanted_opts = None
            targets = None

        accepter_name = None
        if s.accepter_id and s.accepter:
            accepter_name = s.accepter.nome

        out.append(
            MySwapRequestRead(
                id=s.id,
                status=s.status,
                kind=kind,
                offered_shift_date=shift.data,
                offered_shift_code=shift.codigo or "",
                acceptable_shift_types=acceptable,
                wanted_options=wanted_opts,
                direct_targets=targets if kind == "direct" else None,
                accepter_name=accepter_name,
            )
        )
    return out


@router.get("/mine", response_model=list[MySwapRequestRead])
def list_my_swap_requests(
    limit: int = 100,
    include_recent_closed: bool = Query(
        False,
        description="Se true, inclui os últimos pedidos RECUSADOS ou ACEITES (não ficam só em /actions/me).",
    ),
    closed_limit: int = Query(15, ge=0, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pedidos criados pelo utilizador. Por defeito só OPEN (em aberto).

    Com `include_recent_closed=true`, acrescenta os últimos fechados para continuarem visíveis
    na mesma lista (estado RECUSADO / ACEITE). O detalhe «quem recusou/aceitou» continua também
    em `/swap-requests/actions/me`.
    """
    lim = min(max(1, limit), 200)
    open_swaps = (
        db.query(SwapRequest)
        .filter(
            SwapRequest.requester_id == current_user.id,
            SwapRequest.status == SwapStatus.OPEN,
        )
        .options(
            joinedload(SwapRequest.shift),
            joinedload(SwapRequest.accepter),
            joinedload(SwapRequest.direct_targets).joinedload(SwapDirectTarget.user),
            joinedload(SwapRequest.preferences).joinedload(SwapPreference.shift_type),
        )
        .order_by(SwapRequest.id.desc())
        .limit(lim)
        .all()
    )
    out = _build_my_swap_request_reads(db, open_swaps)

    if include_recent_closed and closed_limit > 0:
        cl = min(closed_limit, 50)
        closed_swaps = (
            db.query(SwapRequest)
            .filter(
                SwapRequest.requester_id == current_user.id,
                SwapRequest.status.in_([SwapStatus.REJECTED, SwapStatus.ACCEPTED]),
            )
            .options(
                joinedload(SwapRequest.shift),
                joinedload(SwapRequest.accepter),
                joinedload(SwapRequest.direct_targets).joinedload(SwapDirectTarget.user),
                joinedload(SwapRequest.preferences).joinedload(SwapPreference.shift_type),
            )
            .order_by(SwapRequest.id.desc())
            .limit(cl)
            .all()
        )
        out.extend(_build_my_swap_request_reads(db, closed_swaps))

    return out


@router.delete("/{swap_id}")
def cancel_swap_request(
    swap_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """O requester pode cancelar o seu próprio pedido de troca em aberto."""
    swap = db.query(SwapRequest).filter(SwapRequest.id == swap_id).first()
    if not swap:
        raise HTTPException(status_code=404, detail="Pedido de troca não encontrado")
    if swap.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="Só pode cancelar os seus próprios pedidos")
    if swap.status != SwapStatus.OPEN:
        raise HTTPException(status_code=400, detail="Só pode cancelar pedidos em aberto")
    now = datetime.utcnow()
    swap.status = SwapStatus.REJECTED
    # Retirar da inbox dos aceitantes os avisos «pode aceitar» (evita aceitar/recusar → "Swap already processed").
    db.query(SwapNotification).filter(
        SwapNotification.swap_request_id == swap.id,
        SwapNotification.user_id != swap.requester_id,
        SwapNotification.read_at.is_(None),
        or_(
            SwapNotification.notification_kind == "can_accept",
            SwapNotification.notification_kind.is_(None),
        ),
    ).update({"read_at": now}, synchronize_session=False)
    db.commit()
    return {"message": "Pedido de troca cancelado."}


@router.get("/open", response_model=list[SwapRead])
def list_open_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    swaps = db.query(SwapRequest).filter(
        SwapRequest.status == SwapStatus.OPEN,
        SwapRequest.requester_id != current_user.id
    ).all()

    return swaps


@router.get("/history", response_model=list[SwapHistoryRead])
def list_swap_history(
    limit: int = 100,
    before: date | None = None,
    db: Session = Depends(get_db),
):
    """Lista trocas aceites (histórico). Opcional: limit, before (só registos com accepted_at < before)."""
    q = db.query(SwapHistory).order_by(SwapHistory.accepted_at.desc())
    if before is not None:
        q = q.filter(SwapHistory.accepted_at < datetime.combine(before, time.min))
    return q.limit(limit).all()


@router.delete("/history")
def clear_swap_history(
    before: date,
    db: Session = Depends(get_db),
):
    """Remove registos de histórico com accepted_at anterior a `before` (ex.: fim do mês passado)."""
    deleted = db.query(SwapHistory).filter(
        SwapHistory.accepted_at < datetime.combine(before, time.min)
    ).delete()
    db.commit()
    return {"deleted": deleted, "before": str(before)}

@router.get("/matching", response_model=list[SwapRead])
def matching_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    # todos os turnos do utilizador atual
    my_shifts = db.query(Shift).filter(
        Shift.user_id == current_user.id
    ).all()

    my_shifts_by_date = {s.data: s for s in my_shifts}

    open_swaps = db.query(SwapRequest).filter(
        SwapRequest.status == SwapStatus.OPEN
    ).all()

    result = []

    for swap in open_swaps:

        if swap.requester_id == current_user.id:
            continue

        original_shift = db.query(Shift).filter(
            Shift.id == swap.shift_id
        ).first()

        if not original_shift:
            continue

        # 1) Se o pedido tiver wanted_options, verificar se algum turno meu encaixa
        wanted_opts = db.query(SwapWantedOption).filter(
            SwapWantedOption.swap_request_id == swap.id
        ).all()

        if wanted_opts:
            # mapa (date -> {shift_type_id,...}) para as opções deste swap
            wanted_by_date: dict[date, set[int]] = {}
            for opt in wanted_opts:
                wanted_by_date.setdefault(opt.date, set()).add(opt.shift_type_id)

            compatible = False

            for my_shift in my_shifts:
                if my_shift.shift_type_id is None:
                    continue
                allowed_types = wanted_by_date.get(my_shift.data)
                if not allowed_types:
                    continue
                if my_shift.shift_type_id in allowed_types:
                    compatible = True
                    break

            if compatible:
                result.append(swap)

            # já decidimos com base em wanted_options; não precisamos da lógica antiga
            continue

        # 2) Sem wanted_options → comportamento antigo (mesmo dia + SwapPreference)
        my_shift = my_shifts_by_date.get(original_shift.data)

        if not my_shift:
            continue

        preferences = db.query(SwapPreference).filter(
            SwapPreference.swap_request_id == swap.id
        ).all()

        # sem preferências → qualquer turno no mesmo dia
        if not preferences:
            result.append(swap)
            continue

        allowed_types = [p.shift_type_id for p in preferences]

        if my_shift.shift_type_id in allowed_types:
            result.append(swap)

    return result

@router.get("/suggestions")
def swap_suggestions(
    db: Session = Depends(get_db)
):

    swaps = db.query(SwapRequest).filter(
        SwapRequest.status == SwapStatus.OPEN
    ).all()

    # carregar todos os shifts apenas uma vez
    all_shifts = db.query(Shift).all()
    shifts = {s.id: s for s in all_shifts}

    suggestions = []

    for swap_a in swaps:

        shift_a = shifts.get(swap_a.shift_id)

        if not shift_a:
            continue

        for swap_b in swaps:

            if swap_b.id <= swap_a.id:
                continue

            if swap_a.requester_id == swap_b.requester_id:
                continue

            shift_b = shifts.get(swap_b.shift_id)

            if not shift_b:
                continue

            if shift_a.data != shift_b.data:
                continue

            if shift_a.codigo == shift_b.codigo:
                continue

            suggestions.append({
                "swap_a": swap_a.id,
                "swap_b": swap_b.id,
                "date": str(shift_a.data),
                "shift_a": shift_a.codigo,
                "shift_b": shift_b.codigo,
                "message": "Possible swap detected"
            })

    return suggestions
@router.get("/cycles")
def find_swap_cycles(
    db: Session = Depends(get_db)
):

    try:

        swaps = db.query(SwapRequest).options(
            joinedload(SwapRequest.shift)
        ).filter(
            SwapRequest.status == SwapStatus.OPEN
        ).all()

        cycles = detect_swap_cycles(swaps, db=db)

        result = []

        for cycle in cycles:

            result.append({
                "cycle": cycle,
                "message": "swap cycle possible"
            })

        return {"cycles": result}

    except Exception as e:
        return {"error": str(e)}

@router.get("/possible")
def possible_swaps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    allowed_codes = ["M", "T", "N", "MG", "Mt", "DC", "DS"]

    my_shifts = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.codigo.in_(allowed_codes)
    ).all()

    results = []

    for my_shift in my_shifts:

        other_shifts = db.query(Shift).filter(
            Shift.data == my_shift.data,
            Shift.user_id != current_user.id,
            Shift.codigo.in_(allowed_codes)
        ).all()

        for other in other_shifts:

            if other.codigo == my_shift.codigo:
                continue

            other_user = db.query(User).filter(
                User.id == other.user_id
            ).first()

            results.append({
                "date": my_shift.data,
                "my_shift": my_shift.codigo,
                "other_shift": other.codigo,
                "other_user_id": other.user_id,
                "TEST": "HELLO"
            })

    return results
@router.post("/execute-cycle")
def execute_cycle(cycle: list[int], db: Session = Depends(get_db)):

    swaps = db.query(SwapRequest).filter(SwapRequest.id.in_(cycle)).all()

    if len(swaps) < 2:
        raise HTTPException(status_code=400, detail="Invalid cycle")

    shifts = []
    users = []
    for swap in swaps:
        shift = db.query(Shift).filter(Shift.id == swap.shift_id).first()
        if not shift:
            raise HTTPException(status_code=404, detail=f"Shift for swap {swap.id} not found")
        shifts.append(shift)
        users.append(shift.user_id)

    _validate_cycle_execution(db, shifts, users)

    try:

        temp_user = -999

        # libertar primeiro turno
        shifts[0].user_id = temp_user
        db.flush()

        # mover restantes
        for i in range(1, len(shifts)):
            shifts[i].user_id = users[i-1]
            db.flush()

        # fechar ciclo
        shifts[0].user_id = users[-1]
        db.flush()

        for sh in shifts:
            os = (sh.origin_status or "").strip().lower()
            if os in _SWAP_PRESERVE_ORIGIN_FOR_RECIPIENT:
                continue
            sh.color_bucket = _SWAP_COLOR_BUCKET
            sh.origin_status = _SWAP_ORIGIN_STATUS
        db.flush()

        for swap in swaps:
            swap.status = SwapStatus.ACCEPTED

        n = len(swaps)
        for i in range(n):
            db.add(SwapHistory(
                swap_request_id=swaps[i].id,
                requester_id=swaps[i].requester_id,
                accepter_id=users[(i + 1) % n],
                shift_id_offered=shifts[i].id,
                shift_id_received=shifts[(i + 1) % n].id,
                accepted_at=datetime.utcnow(),
                cycle_id=None,
            ))

        db.commit()

    except Exception as e:
        db.rollback()
        print("Cycle error:", e)
        raise HTTPException(status_code=500, detail="Cycle execution failed")

    return {"message": "Swap cycle executed successfully"}

@router.post("/cycles/propose")
def propose_cycle(
    cycle: list[int],
    db: Session = Depends(get_db)
):

    # buscar swaps abertos
    swaps = db.query(SwapRequest).filter(
        SwapRequest.id.in_(cycle),
        SwapRequest.status == SwapStatus.OPEN
    ).all()

    if len(swaps) != len(cycle):
        raise HTTPException(
            status_code=400,
            detail="Some swaps are not available"
        )

    # criar proposta de ciclo
    proposal = CycleProposal(
        status="PROPOSED"
    )
    db.add(proposal)
    db.flush()  # gera proposal.id

    involved_users = set()

    # ligar swaps ao ciclo e recolher todos os utilizadores
    for swap in swaps:
        # criar ligação Swap <-> Cycle
        db.add(CycleSwap(
            cycle_id=proposal.id,
            swap_id=swap.id
        ))

        # adicionar requester
        involved_users.add(swap.requester_id)

        # adicionar accepter se existir
        if swap.accepter_id:
            involved_users.add(swap.accepter_id)

    # se houver utilizadores adicionais do ciclo que devem participar,
    # podes adicioná-los manualmente aqui:
    # involved_users.update([user_id_1, user_id_2, ...])

    # criar confirmações para cada utilizador do ciclo
    for user_id in involved_users:
        db.add(CycleConfirmation(
            cycle_id=proposal.id,
            user_id=user_id,
            confirmed=False
        ))

    # marcar swaps como PROPOSED
    for swap in swaps:
        swap.status = SwapStatus.PROPOSED

    db.commit()

    return {
        "cycle_id": proposal.id,
        "swaps": cycle,
        "users": list(involved_users),
        "status": "PROPOSED"
    }

@router.post("/cycles/{cycle_id}/confirm")
def confirm_cycle(
    cycle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    confirmation = db.query(CycleConfirmation).filter(
        CycleConfirmation.cycle_id == cycle_id,
        CycleConfirmation.user_id == current_user.id
    ).first()

    if not confirmation:
        raise HTTPException(
            status_code=404,
            detail="Confirmation not found for this user"
        )

    confirmation.confirmed = True
    db.flush()

    # verificar se todos confirmaram
    confirmations = db.query(CycleConfirmation).filter(
        CycleConfirmation.cycle_id == cycle_id
    ).all()

    all_confirmed = all(c.confirmed for c in confirmations)

    if all_confirmed:

        cycle_swaps = db.query(CycleSwap).filter(
            CycleSwap.cycle_id == cycle_id
        ).all()

        swap_ids = [cs.swap_id for cs in cycle_swaps]

        # executar ciclo
        execute_cycle(swap_ids, db)

        proposal = db.query(CycleProposal).filter(
            CycleProposal.id == cycle_id
        ).first()

        proposal.status = "EXECUTED"

    db.commit()

    return {
        "cycle_id": cycle_id,
        "user": current_user.id,
        "confirmed": True,
        "all_confirmed": all_confirmed
    }