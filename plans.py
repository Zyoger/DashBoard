import pandas as pd
from pathlib import Path

PLANS_PATH = Path("data/plans.csv")
COLUMNS = ["Год", "Квартал", "План_без_НДС"]


def parse_plans(source) -> pd.DataFrame:
    """Читает план из CSV (путь к файлу или байтовый буфер)
    и приводит его к формату COLUMNS."""
    df = pd.read_csv(source)
    for c in ["Год", "Квартал", "План_без_НДС"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # если старый файл был по дистрибьюторам/месяцам — конвертируем
    if "Месяц" in df.columns and "Квартал" not in df.columns:
        df["Квартал"] = ((df["Месяц"] - 1) // 3 + 1).astype("Int64")
        df = (df.groupby(["Год", "Квартал"], as_index=False)["План_без_НДС"].sum())
    if "Дистрибьютор" in df.columns:
        df = (df.groupby(["Год", "Квартал"], as_index=False)["План_без_НДС"].sum())
    return df[COLUMNS] if set(COLUMNS).issubset(df.columns) else df


def load_plans() -> pd.DataFrame:
    """Стартовый план из data/plans.csv (если файл есть в репозитории)."""
    if PLANS_PATH.exists():
        return parse_plans(PLANS_PATH)
    return pd.DataFrame(columns=COLUMNS)


def save_plans(df: pd.DataFrame) -> None:
    """Используется утилитой make_fake_plans.py для генерации стартового
    plans.csv. В самом приложении пользовательские данные на диск
    не сохраняются."""
    PLANS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(PLANS_PATH, index=False)
