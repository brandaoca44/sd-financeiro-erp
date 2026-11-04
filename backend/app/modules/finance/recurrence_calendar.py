"""Calendário das despesas mensais."""

from calendar import monthrange
from datetime import date
from typing import Literal
from uuid import UUID, uuid5

ContractDueDay = Literal[5, 10, 15, 20, 25, 30]


def monthly_occurrence(rule_id: UUID, month: date, due_day: int) -> tuple[UUID, date]:
    """Retorna a chave estável da competência e o vencimento ajustado ao mês."""
    if not 1 <= due_day <= 31:
        raise ValueError("O dia de vencimento deve estar entre 1 e 31.")
    competence = month.replace(day=1)
    last_day = monthrange(competence.year, competence.month)[1]
    return uuid5(rule_id, competence.isoformat()), competence.replace(day=min(due_day, last_day))


def contract_occurrence(rule_id: UUID, month: date, due_day: ContractDueDay) -> tuple[UUID, date]:
    """Calcula a competência mensal a partir do dia contratado."""
    if due_day not in (5, 10, 15, 20, 25, 30):
        raise ValueError("Selecione um dia de vencimento: 05, 10, 15, 20, 25 ou 30.")
    return monthly_occurrence(rule_id, month, due_day)