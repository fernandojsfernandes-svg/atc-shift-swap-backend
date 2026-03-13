# Regra: apenas os turnos T e Mt não podem ter N no dia seguinte.
# Nenhuma outra sequência de turnos consecutivos é proibida por esta regra.
INCOMPATIBLE_NEXT_DAY = [
    ("T", "N"),   # T hoje → N amanhã: proibido
    ("Mt", "N"), # Mt hoje → N amanhã: proibido
]

def is_next_day_incompatible(today_code: str, tomorrow_code: str) -> bool:
    """True se (hoje=today_code, amanhã=tomorrow_code) violar a regra (apenas T→N e Mt→N)."""
    return (today_code, tomorrow_code) in INCOMPATIBLE_NEXT_DAY


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

    consecutive = 0

    for shift in shifts:

        if shift.codigo in WORK_SHIFT_CODES:
            consecutive += 1
        else:
            consecutive = 0

        if consecutive > 9:
            return True

    return False