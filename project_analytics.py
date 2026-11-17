"""Единые определения показателей проектных предложений."""
import pandas as pd
from calendar import monthrange
from datetime import date
import re

OFFER_ID = "ID предложения"
PROJECT_ID = "ID проекта"
OFFER_VALUE = "Стоимость для дистрибьютора, руб."
ORDER_VALUE = "Заказы, руб."


def distributor_group(value):
    """Группирует только распознанные общие названия; остальные сохраняет как есть."""
    if pd.isna(value) or not str(value).strip():
        return "(не указано)"
    name = str(value).strip()
    for pattern, group in ((r"^Русский\s+Свет(?:\s|$)", "Русский Свет"),
                           (r"^ЭТМ(?:\s|$)", "ЭТМ"),
                           (r"^Толедо(?:\s|$)", "Толедо"),
                           (r"^Электротехснаб(?:\s|$)", "Электротехснаб")):
        if re.search(pattern, name, flags=re.IGNORECASE):
            return group
    match = re.match(r'^(ООО\s+"[^"]+")(?:\s+ОП\b.*)?$', name, flags=re.IGNORECASE)
    return match.group(1) if match else name


def month_bounds(start_month, end_month):
    """Преобразует месяцы YYYY-MM в включительные календарные границы."""
    start = pd.Period(start_month, freq="M")
    end = pd.Period(end_month, freq="M")
    if end < start:
        raise ValueError("Конец периода не может предшествовать началу.")
    return date(start.year, start.month, 1), date(end.year, end.month, monthrange(end.year, end.month)[1])


def prepare_projects(frame):
    data = frame.copy()
    for source, target in (("Проект", PROJECT_ID), ("Объект / предложение", OFFER_ID)):
        data[target] = data[source].astype("string").str.extract(r"^\s*(\d+)\s*-", expand=False)
    return data


def latest_year_rows(source, filtered):
    """Год выбирается по всем загруженным данным, независимо от фильтров."""
    dates = source["Дата создания"].dropna()
    if dates.empty:
        return None, filtered.iloc[0:0].copy()
    year = int(dates.dt.year.max())
    return year, filtered.loc[filtered["Дата создания"].dt.year == year].copy()


def validate_offers(frame):
    missing = int(frame[OFFER_ID].isna().sum())
    duplicates = int(frame[OFFER_ID].notna().sum() - frame[OFFER_ID].dropna().nunique())
    if missing or duplicates:
        raise ValueError(f"Идентификаторы предложений: пустых — {missing}, повторных строк — {duplicates}. Проверьте выгрузки; автоматическое объединение не выполняется.")


def metrics(frame):
    count = frame[OFFER_ID].nunique()
    offers = frame[OFFER_VALUE].sum()
    orders = frame[ORDER_VALUE].sum()
    converted = frame.loc[frame[ORDER_VALUE] > 0, OFFER_ID].nunique()
    full = frame.loc[frame["Стадия"] == "Полный заказ", OFFER_ID].nunique()
    return {
        "Количество предложений": count,
        "Сумма предложений, руб.": offers,
        "Сумма заказов, руб.": orders,
        "Конверсия в заказ, %": converted / count * 100 if count else None,
        "Реализация потенциала, %": orders / offers * 100 if offers else None,
        "Количество проектов": frame[PROJECT_ID].nunique(),
        "Средняя сумма предложения, руб.": offers / count if count else None,
        "Доля стадии «Полный заказ», %": full / count * 100 if count else None,
    }


def monthly_metrics(frame):
    """Месячные и общие показатели пересчитываются из исходных строк."""
    result = []
    for month in range(1, 13):
        part = frame[frame["Дата создания"].dt.month == month]
        result.append({"Месяц": month, **metrics(part)})
    return pd.DataFrame(result)


def compare_periods(frame, base, current):
    periods = []
    for start, end in (base, current):
        part = frame[frame["Дата создания"].dt.date.between(start, end)]
        periods.append(part)
    return periods


def distributor_comparison(periods):
    """Сохраняет все фактические наименования и пустую категорию."""
    tables = []
    for frame, suffix in zip(periods, ("прошлый", "текущий")):
        grouped = frame.assign(Дистрибьютор=frame["Дистрибьютор"].fillna("(не указано)"))
        grouped = grouped.groupby("Дистрибьютор", dropna=False).agg(
            Количество=(OFFER_ID, "nunique"),
            Предложения=(OFFER_VALUE, "sum"),
            Заказы=(ORDER_VALUE, "sum"),
        )
        tables.append(grouped.add_suffix(f" — {suffix}"))
    return tables[0].join(tables[1], how="outer").fillna(0).sort_index()


def monthly_comparison(periods, base, current):
    """Таблица месяцев и итог с повторным расчётом отношений по всем строкам."""
    frames = []
    for part, (start, end), suffix in zip(periods, (base, current), ("прошлый", "текущий")):
        monthly = monthly_metrics(part).set_index("Месяц")
        monthly.loc[~monthly.index.to_series().between(start.month, end.month), :] = float("nan")
        frames.append(monthly.add_suffix(f" — {suffix}"))
    table = frames[0].join(frames[1])
    for name in ("Количество предложений", "Сумма предложений, руб.", "Сумма заказов, руб."):
        prior, recent = table[f"{name} — прошлый"], table[f"{name} — текущий"]
        table[f"{name}: динамика, %"] = (recent.div(prior.where(prior != 0)) - 1) * 100
    total = {}
    for part, suffix in zip(periods, ("прошлый", "текущий")):
        total.update({f"{name} — {suffix}": value for name, value in metrics(part).items()})
    for name in ("Количество предложений", "Сумма предложений, руб.", "Сумма заказов, руб."):
        before, after = total[f"{name} — прошлый"], total[f"{name} — текущий"]
        total[f"{name}: динамика, %"] = (after / before - 1) * 100 if before else None
    table.index = table.index.map(str)
    table.loc["Итого"] = pd.Series(total)
    return table
