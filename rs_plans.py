"""Квартальные планы Русского Света и их равномерное месячное распределение."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO

import pandas as pd

from tabs.tab_dynamics import MONTH_NAMES

SHEET_NAME = "Планы РС"
COLUMNS = ["Филиал", "Год", "Квартал", "План_без_НДС"]
WIDE_COLUMNS = ["Филиал", "Год"] + [f"{q} квартал" for q in range(1, 5)]


def validate_quarterly_plans(frame):
    if set(WIDE_COLUMNS).issubset(frame.columns):
        frame = frame[WIDE_COLUMNS].dropna(how="all").copy()
        quarters = WIDE_COLUMNS[2:]
        frame[quarters] = frame[quarters].fillna(0)
        frame = frame.melt(id_vars=["Филиал", "Год"], value_vars=quarters,
                           var_name="Квартал", value_name="План_без_НДС")
        frame["Квартал"] = frame["Квартал"].str[0].astype(int)
    missing = set(COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError("Нужны столбцы: " + ", ".join(WIDE_COLUMNS) + ". Скачайте шаблон на вкладке «План».")
    frame = frame[COLUMNS].dropna(how="all").copy()
    if frame.empty:
        raise ValueError("Заполните хотя бы одну строку квартального плана.")
    records = []
    for index, row in frame.iterrows():
        label = f"Строка {index + 2}"
        if pd.isna(row["Филиал"]) or not str(row["Филиал"]).strip():
            raise ValueError(f"{label}: укажите филиал (город из выгрузки продаж).")
        try:
            year = Decimal(str(row["Год"]).strip())
            quarter = Decimal(str(row["Квартал"]).strip())
            text = str(row["План_без_НДС"]).replace(" ", "").replace("\u00a0", "").replace(",", ".")
            amount = Decimal(text)
            if not year.is_finite() or year != int(year) or not 1900 <= year <= 9999:
                raise ValueError("год должен быть целым числом от 1900 до 9999")
            if not quarter.is_finite() or quarter != int(quarter) or not 1 <= quarter <= 4:
                raise ValueError("квартал должен быть целым числом от 1 до 4")
            if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
                raise ValueError("план должен быть неотрицательным числом с точностью до копеек")
        except (InvalidOperation, ValueError, OverflowError) as exc:
            raise ValueError(f"{label}: проверьте год, квартал и сумму плана. {exc}") from exc
        records.append([str(row["Филиал"]).strip(), int(year), int(quarter), float(amount)])
    result = pd.DataFrame(records, columns=COLUMNS)
    keys = result.assign(Филиал=result["Филиал"].str.casefold())
    if keys.duplicated(["Филиал", "Год", "Квартал"]).any():
        raise ValueError("Филиал, год и квартал должны быть уникальны: найдены повторяющиеся строки.")
    return result


def parse_quarterly_plans(payload):
    frame = pd.read_excel(BytesIO(payload), sheet_name=SHEET_NAME, engine="openpyxl")
    return validate_quarterly_plans(frame)


def quarterly_to_monthly(frame):
    """Первые два месяца округляем до копеек; третий получает остаток квартала."""
    frame = validate_quarterly_plans(frame)
    result = {}
    for year, group in frame.groupby("Год"):
        monthly = pd.DataFrame(0.0, index=sorted(group["Филиал"].unique()), columns=MONTH_NAMES)
        monthly.index.name = "Филиал"
        for _, row in group.iterrows():
            total = Decimal(str(row["План_без_НДС"]))
            part = (total / 3).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            values = [part, part, total - part * 2]
            start = (int(row["Квартал"]) - 1) * 3
            for offset, value in enumerate(values):
                monthly.loc[row["Филиал"], MONTH_NAMES[start + offset]] = float(value)
        result[int(year)] = monthly
    return result
