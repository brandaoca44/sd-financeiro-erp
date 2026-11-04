"""Prévia mensal de CLT para 2026, com salário como única verba tributável."""

from decimal import Decimal, ROUND_HALF_UP

D = Decimal
INSS = tuple((D(limit), D(rate)) for limit, rate in (
    ("1621.00", ".075"), ("2902.84", ".09"), ("4354.27", ".12"), ("8475.55", ".14"),
))
IRRF = tuple((D(floor), D(rate), D(deduction)) for floor, rate, deduction in (
    ("4664.68", ".275", "908.73"), ("3751.05", ".225", "675.49"),
    ("2826.65", ".15", "394.16"), ("2428.80", ".075", "182.16"), ("0", "0", "0"),
))


def cents(value: Decimal) -> Decimal:
    return value.quantize(D(".01"), rounding=ROUND_HALF_UP)


def estimate_clt_2026(gross: Decimal) -> dict[str, Decimal]:
    previous = contribution = D(0)
    for limit, rate in INSS:
        contribution += max(D(0), min(gross, limit) - previous) * rate
        previous = limit
    inss = cents(contribution)
    base = max(D(0), gross - max(inss, D("607.20")))
    tax = next(cents(max(D(0), base * rate - deduction))
               for floor, rate, deduction in IRRF if base >= floor and (base > floor or floor == 0))
    reduction = D("312.89") if gross <= 5000 else max(D(0), D("978.62") - D(".133145") * gross)
    irrf = cents(max(D(0), tax - reduction))
    return {"gross": gross, "inss": inss, "irrf": irrf, "net": gross - inss - irrf}
