import pandas as pd
from pathlib import Path
from numeric_validation import numeric_values

PLANS_PATH = Path("data/plans.csv")
COLUMNS = ["Год", "Квартал", "План_без_НДС"]


def parse_plans(source) -> pd.DataFrame:
    """Читает план из CSV (путь к файлу или байтовый буфер)
    и приводит его к формату COLUMNS."""
    df = pd.read_csv(source)
    required = {"Год", "План_без_НДС"}
    if "Квартал" not in df.columns and "Месяц" not in df.columns:
        required.add("Квартал")
    missing = required - set(df.columns)
    if missing:
        raise ValueError("В плане отсутствуют обязательные столбцы: " + ", ".join(sorted(missing)))
    period = "Квартал" if "Квартал" in df.columns else "Месяц"
    for c in ["Год", period, "План_без_НДС"]:
        df[c] = numeric_values(df[c], c)
        if df[c].isna().any():
            raise ValueError(f"Столбец «{c}»: обязательное значение не заполнено.")
    for c, low, high in [("Год", 1900, 9999), (period, 1, 4 if period == "Квартал" else 12)]:
        if ((df[c] % 1 != 0) | ~df[c].between(low, high)).any():
            raise ValueError(f"Столбец «{c}»: ожидается целое число от {low} до {high}.")
    # если старый файл был по дистрибьюторам/месяцам — конвертируем
    if "Месяц" in df.columns and "Квартал" not in df.columns:
        df["Квартал"] = ((df["Месяц"] - 1) // 3 + 1).astype("Int64")
        df = (df.groupby(["Год", "Квартал"], as_index=False)["План_без_НДС"].sum())
    if "Дистрибьютор" in df.columns:
        df = (df.groupby(["Год", "Квартал"], as_index=False)["План_без_НДС"].sum())
    return df[COLUMNS]


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
