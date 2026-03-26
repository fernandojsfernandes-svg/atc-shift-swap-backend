""" valores por omissão e validação para edição manual de turnos (cor / origem). """

from __future__ import annotations

# Buckets usados no frontend (backgroundColor) e no import PDF
VALID_COLOR_BUCKETS = frozenset(
    {"red", "pink", "gray_light", "gray_dark", "lime", "yellow"},
)

# Valores de origin_status já usados no projeto (models / PDF)
VALID_ORIGIN_STATUS = frozenset(
    {
        "rota",
        "troca_nav",
        "troca_servico",
        "bht",
        "ts",
        "mudanca_funcoes",
        "outros",
    },
)


def resolve_manual_shift_fields(
    codigo: str,
    color_bucket: str | None,
    origin_status: str | None,
) -> tuple[str | None, str | None]:
    """
    Se color_bucket ou origin_status forem None, aplicam-se regras simples por omissão.
    """
    code = (codigo or "").strip()
    cb = color_bucket.strip() if color_bucket else None
    os_ = origin_status.strip() if origin_status else None

    if cb is None:
        if code in ("DC", "DS"):
            cb = "gray_dark"
        else:
            cb = "gray_light"

    if os_ is None:
        os_ = "rota"

    return cb, os_
