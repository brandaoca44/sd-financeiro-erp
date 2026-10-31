"""Valida CNPJ numérico e alfanumérico pelo módulo 11 publicado pela Receita."""

import re

_PLAIN = re.compile(r"[A-Za-z0-9]{12}[0-9]{2}", re.ASCII)
_MASKED = re.compile(r"[A-Za-z0-9]{2}\.[A-Za-z0-9]{3}\.[A-Za-z0-9]{3}/[A-Za-z0-9]{4}-[0-9]{2}", re.ASCII)


def normalize_cnpj(value: str) -> str:
    """Aceita somente formato limpo ou máscara completa; nunca descarta letras."""
    if not isinstance(value, str):
        raise ValueError("CNPJ inválido.")
    raw = value.strip()
    if _PLAIN.fullmatch(raw) is None and _MASKED.fullmatch(raw) is None:
        raise ValueError("CNPJ inválido.")
    normalized = raw.translate(str.maketrans("", "", "./-")).upper()
    if len(set(normalized)) == 1:
        raise ValueError("CNPJ inválido.")
    body = normalized[:12]
    for length in (12, 13):
        total = sum((ord(char) - 48) * (2 + ((length - index - 1) % 8)) for index, char in enumerate(body))
        remainder = total % 11
        body += str(0 if remainder < 2 else 11 - remainder)
    if body != normalized:
        raise ValueError("CNPJ inválido.")
    return normalized
