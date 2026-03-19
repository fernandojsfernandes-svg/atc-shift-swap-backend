# Regra: apenas os turnos T e Mt não podem ter N no dia seguinte.
# Nenhuma outra sequência de turnos consecutivos é proibida por esta regra.
INCOMPATIBLE_NEXT_DAY = [
    ("T", "N"),   # T hoje → N amanhã: proibido
    ("Mt", "N"), # Mt hoje → N amanhã: proibido
]

def _normalize_shift_code(code: str | None) -> str:
    """
    Normaliza códigos vindos da BD/PDF (evita falsos positivos por espaços).
    Nota: não alteramos case porque existem códigos distintos como "MT" vs "Mt".
    Ex.: "Mt ", " Mt" -> "Mt".
    """
    c = (code or "").strip()
    if not c:
        return ""
    return c

def is_next_day_incompatible(today_code: str, tomorrow_code: str) -> bool:
    """True se (hoje=today_code, amanhã=tomorrow_code) violar a regra (apenas T→N e Mt→N)."""
    t = _normalize_shift_code(today_code)
    n = _normalize_shift_code(tomorrow_code)
    return (t, n) in INCOMPATIBLE_NEXT_DAY


# códigos que contam como trabalho
WORK_SHIFT_CODES = {
    "M",
    "T",
    "N",
    "MG",
    "Mt"
}

def exceeds_max_consecutive_days(shifts):

    shifts = sorted(shifts, key=lambda s: s.data)

    # Contar apenas dias consecutivos no calendário.
    # Se existirem lacunas (dias sem registo), não podemos continuar a contar como "consecutivos".
    consecutive = 0
    prev_date = None

    for shift in shifts:
        codigo = _normalize_shift_code(getattr(shift, "codigo", None))
        if codigo in WORK_SHIFT_CODES:
            if prev_date is None or (shift.data - prev_date).days != 1:
                consecutive = 1
            else:
                consecutive += 1
        else:
            consecutive = 0

        prev_date = shift.data

        if consecutive > 9:
            return True

    return False