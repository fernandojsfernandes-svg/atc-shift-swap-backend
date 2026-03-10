# incompatibilidades entre turnos de dias consecutivos
INCOMPATIBLE_NEXT_DAY = [
    ("T", "N"),
    ("Mt", "N"),
]

def is_next_day_incompatible(today_code: str, tomorrow_code: str) -> bool:
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