import pandas as pd
from pathlib import Path

MONTHS_RU = {
    "Январь": 1, "Февраль": 2, "Март": 3, "Апрель": 4,
    "Май": 5, "Июнь": 6, "Июль": 7, "Август": 8,
    "Сентябрь": 9, "Октябрь": 10, "Ноябрь": 11, "Декабрь": 12,
}


def _parse_month(label):
    """'Январь 2025' -> (2025, 1, Timestamp('2025-01-01')) или None."""
    parts = str(label).strip().split()
    if len(parts) != 2:
        return None
    name, year = parts
    m = MONTHS_RU.get(name)
    if not m or not year.isdigit():
        return None
    return int(year), m, pd.Timestamp(year=int(year), month=m, day=1)


def load_sales(path: str | Path) -> pd.DataFrame:
    """Читает лист 'Table'.

    Структура (0-based индексы колонок):
        6  = G = Город
        7  = H = Дистрибьютор
        8  = I = Код_материала  (например, '001/5')
        9  = J = Материал       (например, 'Металлические каналы')
        10..27 = K:AB = месяцы 'Январь 2025' … 'Сентябрь 2026'
        28 = AC = 'Общий результат' — игнорируем
    """
    df = pd.read_excel(path, sheet_name="Table", header=15)

    df = df.rename(columns={
        df.columns[6]: "Город",
        df.columns[7]: "Дистрибьютор",
        df.columns[8]: "Код_материала",
        df.columns[9]: "Материал",
    })

    # Отсекаем строку-итог "Результат": у неё пустой дистрибьютор
    df = df[df["Город"].notna()]
    df = df[df["Дистрибьютор"].notna()]
    df = df[df["Дистрибьютор"].astype(str).str.strip() != ""]
    df = df[df["Дистрибьютор"].astype(str).str.strip().str.lower() != "результат"]
    df = df[df["Материал"].notna()]
    df = df[df["Материал"].astype(str).str.strip() != ""]

    month_cols = [c for c in df.columns if _parse_month(c)]
    if not month_cols:
        raise ValueError("Не найдены колонки месяцев формата 'Месяц Год'")

    id_cols = ["Город", "Дистрибьютор", "Код_материала", "Материал"]
    long = df.melt(
        id_vars=id_cols,
        value_vars=month_cols,
        var_name="Месяц_подпись",
        value_name="Сумма_без_НДС",
    )
    long["Сумма_без_НДС"] = pd.to_numeric(long["Сумма_без_НДС"], errors="coerce").fillna(0)

    parsed = long["Месяц_подпись"].map(_parse_month)
    long["Год"] = parsed.map(lambda x: x[0] if x else None)
    long["Месяц"] = parsed.map(lambda x: x[1] if x else None)
    long["Дата"] = parsed.map(lambda x: x[2] if x else pd.NaT)
    long = long.drop(columns=["Месяц_подпись"]).dropna(subset=["Дата"])
    long["Квартал"] = long["Дата"].dt.quarter
    return long.reset_index(drop=True)