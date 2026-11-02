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
