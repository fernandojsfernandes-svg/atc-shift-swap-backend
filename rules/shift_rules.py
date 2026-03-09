# Regras de incompatibilidade entre turnos
# (turno hoje, turno dia seguinte)

INCOMPATIBLE_NEXT_DAY = [
    ("T", "N"),
    ("Mt", "N"),
]


def is_next_day_incompatible(today_code: str, tomorrow_code: str) -> bool:
    return (today_code, tomorrow_code) in INCOMPATIBLE_NEXT_DAY