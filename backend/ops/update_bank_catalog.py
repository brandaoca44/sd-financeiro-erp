"""Atualiza o catálogo público usado no seletor de instituições financeiras."""
import csv
import io
import json
from datetime import date
from pathlib import Path
from urllib.request import urlopen

SOURCE = "https://www.bcb.gov.br/content/estabilidadefinanceira/str1/ParticipantesSTR.csv"
DESTINATION = Path(__file__).resolve().parents[2] / "frontend/public/catalog/banks.json"


def build_catalog(data: bytes):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0][0] != "ISPB":
        raise ValueError("Formato inesperado do catálogo do Banco Central.")
    banks = []
    for row in rows[1:]:
        if len(row) < 6 or not row[0].strip():
            continue
        ispb, short_name, code = row[0].strip(), row[1].strip(), row[2].strip()
        if len(ispb) != 8 or not ispb.isdigit() or not short_name:
            raise ValueError("Instituição inválida no catálogo.")
        value = f"{code} - {short_name}" if code.isdigit() else short_name
        if len(value) > 80:
            raise ValueError("Nome da instituição excede o limite do cadastro.")
        banks.append({"ispb": ispb, "code": code if code.isdigit() else None,
                      "name": row[5].strip(), "value": value})
    if len(banks) < 100:
        raise ValueError("Catálogo incompleto.")
    return {"source": SOURCE, "license": "ODbL-1.0", "updated": date.today().isoformat(),
            "banks": sorted(banks, key=lambda bank: bank["value"])}


if __name__ == "__main__":
    with urlopen(SOURCE, timeout=20) as response:
        catalog = build_catalog(response.read())
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(DESTINATION)
    print(f"Catálogo atualizado com {len(catalog['banks'])} instituições.")
