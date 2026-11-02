"""Аналитика проектного взаимодействия по выгрузке 1С/CRM."""
from __future__ import annotations

from io import BytesIO
import re

import pandas as pd
import streamlit as st

SHEET_NAME = "Предложение"
COLUMN_MAP = {
    "Проектный запрос.Ид. - Наименование": "Проектный запрос",
    "Проект": "Проект",
    "Проект.Подотрасль": "Подотрасль",
    "Ид. и Наименование": "Объект / предложение",
    "Дистрибьютор": "Дистрибьютор",
    "Конечный клиент": "Конечный клиент",
    "Стадия": "Стадия",
    "Ответственный": "Ответственный",
    "Создал": "Создал",
    "Дата создания": "Дата создания",
    "Скидка клиенту": "Скидка клиенту, %",
    "Скидка дистрибьютору": "Скидка дистрибьютору, %",
    "Стоимость для клиента (без НДС)": "Стоимость для клиента, руб.",
    "Стоимость для дистрибьютора (без НДС), руб.": "Стоимость для дистрибьютора, руб.",
    "Заказы (по колонке Предложение).Сумма без НДС": "Заказы, руб.",
}
NUMERIC_COLUMNS = [
    "Скидка клиенту, %", "Скидка дистрибьютору, %",
    "Стоимость для клиента, руб.", "Стоимость для дистрибьютора, руб.",
    "Заказы, руб.",
]
REQUIRED_COLUMNS = list(COLUMN_MAP)


@st.cache_data(show_spinner=False)
def parse_project_file(payload: bytes) -> pd.DataFrame:
    """Читает лист «Предложение» и приводит поля к типам, нужным аналитике."""
    try:
        raw = pd.read_excel(BytesIO(payload), sheet_name=SHEET_NAME, engine="openpyxl")
    except ValueError as exc:
        raise ValueError(f"В книге не найден лист «{SHEET_NAME}».") from exc
    missing = [column for column in REQUIRED_COLUMNS if column not in raw.columns]
    if missing:
        raise ValueError("В файле отсутствуют обязательные столбцы: " + ", ".join(missing))

    df = raw[REQUIRED_COLUMNS].rename(columns=COLUMN_MAP).copy()
    text_columns = [
        "Проектный запрос", "Проект", "Подотрасль", "Объект / предложение",
        "Дистрибьютор", "Конечный клиент", "Стадия", "Ответственный", "Создал",
    ]
    for column in text_columns:
        df[column] = df[column].astype("string").str.strip()
        df[column] = df[column].replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    df["Дата создания"] = pd.to_datetime(df["Дата создания"], errors="coerce")

    # Город берём только из явного фрагмента «г. ...» в поле дистрибьютора.
    # Если его нет, оставляем отдельную категорию, не пытаясь угадать город.
    def extract_city(value):
        if pd.isna(value):
            return "Не указан"
        match = re.search(r"г\.\s*([^,]+)", str(value), flags=re.IGNORECASE)
        if not match:
            return "Не указан"
        city = match.group(1).strip()
        # В некоторых строках после названия города присутствует пометка филиала «Осн.».
        return re.sub(r"\s+Осн\.?$", "", city, flags=re.IGNORECASE).strip()

    df["Город"] = df["Дистрибьютор"].map(extract_city)
    df["Месяц"] = df["Дата создания"].dt.to_period("M").dt.to_timestamp()
    return df


def _multi_filter(label: str, series: pd.Series, key: str):
    options = sorted(series.dropna().astype(str).unique().tolist())
    return st.multiselect(label, options, default=options, key=key)


def _money(value: float) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def _percent(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def render(ctx: dict | None = None):
    """Отображает дашборд проектного взаимодействия."""
    ctx = ctx or {}
    df = ctx.get("project_df")
    if df is None or df.empty:
        st.title("🤝 Проектное взаимодействие")
        st.info("Загрузите выгрузку проектного взаимодействия (.xlsx) в боковой панели.")
        return

    st.title("🤝 Проектное взаимодействие")
    st.caption("Аналитика по листу «Предложение». Фильтры находятся в общей боковой панели. Денежные суммы рассчитаны по строкам исходной выгрузки.")

    filtered = ctx.get("project_filtered_df")
    if filtered is None:
        filtered = df.copy()
    else:
        filtered = filtered.copy()

    if filtered.empty:
        st.warning("По выбранным фильтрам записей нет. Измените параметры фильтрации.")
        return

    projects_count = filtered["Проект"].nunique()
    records_count = len(filtered)
    proposal_sum = filtered["Стоимость для клиента, руб."].sum()
    orders_sum = filtered["Заказы, руб."].sum()
    conversion = orders_sum / proposal_sum * 100 if proposal_sum else 0
    full_orders = filtered.loc[filtered["Стадия"] == "Полный заказ", "Проект"].nunique()

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Уникальных проектов", f"{projects_count:,}".replace(",", " "))
    k2.metric("Записей / предложений", f"{records_count:,}".replace(",", " "))
    k3.metric("Стоимость предложений", _money(proposal_sum))
    k4.metric("Сумма заказов", _money(orders_sum))
    k5.metric("Заказы / предложения", _percent(conversion))
    st.caption(f"Проекты со стадией «Полный заказ» в отфильтрованных строках: {full_orders:,}".replace(",", " "))
    missing_requests = int(filtered["Проектный запрос"].isna().sum())
    st.caption(
        f"Пустое поле «Проектный запрос»: {missing_requests:,} строк. "
        "Пустые значения сохранены как есть — соседние значения не подставляются."
        .replace(",", " ")
    )

    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Проектное взаимодействие по стадиям")
        stage_summary = (filtered.groupby("Стадия", dropna=False)
                         .agg(Записей=("Проект", "size"), Проектов=("Проект", "nunique"),
                              Предложения=("Стоимость для клиента, руб.", "sum"),
                              Заказы=("Заказы, руб.", "sum"))
                         .sort_values("Записей", ascending=False))
        st.bar_chart(stage_summary[["Записей"]])
        st.dataframe(stage_summary.style.format({"Предложения": "{:,.0f}", "Заказы": "{:,.0f}"}), use_container_width=True)
    with right:
        st.subheader("ТОП-10 дистрибьюторов по стоимости предложений")
        dist_summary = (filtered.groupby("Дистрибьютор", dropna=False)
                        .agg(Проектов=("Проект", "nunique"), Записей=("Проект", "size"),
                             Предложения=("Стоимость для клиента, руб.", "sum"),
                             Заказы=("Заказы, руб.", "sum"))
                        .sort_values("Предложения", ascending=False))
        st.bar_chart(dist_summary.head(10)[["Предложения"]])
        st.dataframe(dist_summary.head(10).style.format({"Предложения": "{:,.0f}", "Заказы": "{:,.0f}"}), use_container_width=True)

    st.subheader("Сводная таблица: дистрибьютор → город")
    distributor_city = (filtered.groupby(["Дистрибьютор", "Город"], dropna=False)
                        .agg(Проектов=("Проект", "nunique"), Записей=("Проект", "size"),
                             Стоимость_предложений=("Стоимость для клиента, руб.", "sum"),
                             Стоимость_дистрибьютора=("Стоимость для дистрибьютора, руб.", "sum"),
                             Заказы=("Заказы, руб.", "sum"))
                        .reset_index()
                        .sort_values("Стоимость_предложений", ascending=False))
    st.dataframe(distributor_city.style.format({
        "Стоимость_предложений": "{:,.0f}", "Стоимость_дистрибьютора": "{:,.0f}", "Заказы": "{:,.0f}"
    }), use_container_width=True, hide_index=True)

    st.subheader("Динамика по месяцам")
    monthly = (filtered.dropna(subset=["Месяц"]).groupby("Месяц")
               .agg(Проектов=("Проект", "nunique"), Записей=("Проект", "size"),
                    Предложения=("Стоимость для клиента, руб.", "sum"),
                    Заказы=("Заказы, руб.", "sum")))
    if not monthly.empty:
        m1, m2 = st.columns(2)
        with m1:
            st.caption("Стоимость предложений, руб.")
            st.line_chart(monthly[["Предложения"]])
        with m2:
            st.caption("Сумма заказов, руб.")
            st.line_chart(monthly[["Заказы"]])

    st.subheader("Детализация проектных записей")
    detail_columns = [
        "Проектный запрос", "Проект", "Подотрасль", "Объект / предложение",
        "Дистрибьютор", "Город", "Конечный клиент", "Стадия", "Ответственный",
        "Создал", "Дата создания", "Скидка клиенту, %", "Скидка дистрибьютору, %",
        "Стоимость для клиента, руб.", "Стоимость для дистрибьютора, руб.", "Заказы, руб.",
    ]
    st.dataframe(filtered[detail_columns].sort_values("Дата создания", ascending=False),
                 use_container_width=True, hide_index=True)

    export = BytesIO()
    with pd.ExcelWriter(export, engine="openpyxl") as writer:
        filtered[detail_columns].to_excel(writer, index=False, sheet_name="Проекты")
        distributor_city.to_excel(writer, index=False, sheet_name="Дистрибьютор-город")
        stage_summary.reset_index().to_excel(writer, index=False, sheet_name="Стадии")
    st.download_button(
        "⬇️ Скачать отфильтрованные данные Excel",
        data=export.getvalue(),
        file_name="project_analysis_filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="project_export_xlsx",
    )
