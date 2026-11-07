"""Contratos internos com valores e datas sem conversão monetária por float."""

from datetime import date
from decimal import Decimal
import re
from typing import Annotated
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_serializer, model_validator

MAX_MONEY = Decimal("9999999999999999.99")


def money(value):
    if isinstance(value, str):
        if len(value) > 19 or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?", value):
            raise ValueError("Informe valor decimal positivo com até duas casas.")
        value = Decimal(value)
    if (not isinstance(value, Decimal) or not value.is_finite()
            or value.as_tuple().exponent < -2 or not Decimal("0") < value <= MAX_MONEY):
        raise ValueError("Valor monetário inválido.")
    return value


def calendar_date(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        value = date.fromisoformat(value)
    if type(value) is not date:
        raise ValueError("Informe uma data de calendário no formato AAAA-MM-DD.")
    return value


Money = Annotated[Decimal, BeforeValidator(money, json_schema_input_type=str)]
CalendarDate = Annotated[date, BeforeValidator(calendar_date)]


class PayableCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    amount: Money
    issue_date: CalendarDate
    due_date: CalendarDate

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.due_date < self.issue_date:
            raise ValueError("Vencimento não pode anteceder a emissão.")
        return self


class PayableUpdate(PayableCreate):
    expected_revision: int = Field(strict=True, ge=1)


class PayableCancel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expected_revision: int = Field(strict=True, ge=1)


class PayableReceipt(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int
    status: Literal["OPEN", "CANCELLED"]


class PayableResponse(PayableReceipt):
    organization_id: UUID
    company_id: UUID
    description: str
    amount: Decimal
    currency: Literal["BRL"]
    issue_date: date
    due_date: date
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_serializer("amount")
    def serialize_amount(self, value):
        return format(value, ".2f")


class PayablePage(BaseModel):
    items: list[PayableResponse]
    next_cursor: UUID | None


class PayablePayment(PayableCancel):
    financial_account_id: UUID | None = None
    amount: Money
    occurred_on: CalendarDate


class PayableReversal(PayableCancel):
    occurred_on: CalendarDate
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class MovementReceipt(BaseModel):
    payable_id: UUID
    movement_id: UUID
    revision: int
    kind: Literal["PAYMENT", "REVERSAL"]


class MovementResponse(BaseModel):
    financial_account_id: UUID | None = None
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    payable_id: UUID
    kind: Literal["PAYMENT", "REVERSAL"]
    amount: Decimal
    occurred_on: date
    reverses_id: UUID | None
    reversal_reason: str | None
    created_at: AwareDatetime

    @field_serializer("amount")
    def serialize_amount(self, value):
        return format(value, ".2f")


class MovementPage(BaseModel):
    items: list[MovementResponse]
    next_cursor: UUID | None


class PayablePosition(BaseModel):
    payable_id: UUID
    revision: int
    currency: Literal["BRL"] = "BRL"
    amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    settlement_status: Literal["OPEN", "PARTIALLY_PAID", "PAID", "CANCELLED"]

    @field_serializer("amount", "paid_amount", "outstanding_amount")
    def serialize_amount(self, value):
        return format(value, ".2f")


class CurrentPayables(BaseModel):
    active_title_count: int
    cancelled_title_count: int
    unpaid_title_count: int
    partial_title_count: int
    paid_title_count: int
    original_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    overdue_amount: Decimal
    due_today_amount: Decimal
    upcoming_amount: Decimal
    later_amount: Decimal

    @field_serializer("original_amount", "paid_amount", "outstanding_amount", "overdue_amount",
                      "due_today_amount", "upcoming_amount", "later_amount")
    def serialize_money(self, value):
        return format(value, ".2f")


class PeriodPayables(BaseModel):
    original_due_amount: Decimal
    outstanding_due_amount: Decimal
    overdue_due_amount: Decimal
    payments_amount: Decimal
    reversals_amount: Decimal
    net_paid_amount: Decimal

    @field_serializer("original_due_amount", "outstanding_due_amount", "overdue_due_amount",
                      "payments_amount", "reversals_amount", "net_paid_amount")
    def serialize_money(self, value):
        return format(value, ".2f")


class PayablesDay(BaseModel):
    day: date
    original_due_amount: Decimal
    outstanding_due_amount: Decimal
    payments_amount: Decimal
    reversals_amount: Decimal
    net_paid_amount: Decimal

    @field_serializer("original_due_amount", "outstanding_due_amount", "payments_amount", "reversals_amount", "net_paid_amount")
    def serialize_money(self, value):
        return format(value, ".2f")


class PayablesSummary(BaseModel):
    company_id: UUID
    currency: Literal["BRL"] = "BRL"
    balance_basis: Literal["CURRENT"] = "CURRENT"
    timezone: Literal["America/Sao_Paulo"] = "America/Sao_Paulo"
    as_of: date
    period_start: date
    period_end: date
    upcoming_days: int
    current: CurrentPayables
    period: PeriodPayables
    days: list[PayablesDay]
