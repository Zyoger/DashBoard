"""Аналитика проектного взаимодействия по выгрузке 1С/CRM."""
from __future__ import annotations

from io import BytesIO
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from numeric_validation import numeric_values
from project_analytics import prepare_projects, metrics, compare_periods, distributor_comparison, latest_year_rows

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
        df[column] = numeric_values(df[column], column).fillna(0)
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
    return prepare_projects(df)


def _multi_filter(label: str, series: pd.Series, key: str):
    options = sorted(series.dropna().astype(str).unique().tolist())
    return st.multiselect(label, options, default=options, key=key)


def _money(value: float) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def _percent(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def render(ctx: dict | None = None):
    overview, dynamics, distributors = st.tabs(["Обзор", "Динамика", "Дистрибьюторы"])
    with overview:
        _render_comparison_summary(ctx or {})
        _render_overview(ctx)
    with dynamics:
        _render_dynamics(ctx or {})
    with distributors:
        _render_dimension(ctx or {}, ["Дистрибьютор", "Город"], "Дистрибьюторы и филиалы")


def _period_frames(ctx):
    df = ctx.get("project_comparison_df")
    filters = ctx.get("project_filters", {})
    base, current = filters.get("compare_base", ()), filters.get("compare_current", ())
    if df is None or len(base) != 2 or len(current) != 2:
        return None
    return compare_periods(df, base, current)


def _render_comparison_summary(ctx):
    source = ctx.get("project_df")
    if source is None or source.empty:
        return
    filtered = ctx.get("project_filtered_df")
    year, current_rows = latest_year_rows(source, source if filtered is None else filtered)
    if year is None or current_rows.empty:
        return
    current = metrics(current_rows)
    st.subheader(f"Показатели за {year} год")
    cols = st.columns(4)
    for i, (name, value) in enumerate(current.items()):
        text = "н/д" if value is None else f"{value:,.1f}".replace(",", " ")
        cols[i % 4].metric(name, text)
    missing = int(current_rows["ID проекта"].isna().sum())
    if missing:
        st.warning(f"Строк без идентификатора проекта: {missing}. Они включены в суммы и число предложений, но не в число проектов.")
    st.caption("Заказы показаны по дате создания предложения; это не дата оформления заказа.")


def _render_dimension(ctx, fields, title):
    st.subheader(title)
    periods = _period_frames(ctx)
    if periods is None:
        st.info("Загрузите проектные выгрузки и выберите интервалы сравнения.")
        return
    tables = []
    for label, frame in zip(("Прошлый период", "Текущий период"), periods):
        records = []
        for keys, group in frame.groupby(fields, dropna=False, sort=False):
            keys = keys if isinstance(keys, tuple) else (keys,)
            records.append({**dict(zip(fields, keys)), **metrics(group)})
        table = pd.DataFrame(records, columns=fields + list(metrics(frame)))
        tables.append(table.rename(columns={col: f"{col} ({label})" for col in table.columns if col not in fields}))
    result = tables[0].merge(tables[1], on=fields, how="outer")
    if result.empty:
        st.info("По выбранным фильтрам данных нет.")
        return
    st.dataframe(result, hide_index=True, width="stretch")
    st.caption("Данные соответствуют выбранным периодам сравнения.")
    order_column = "Сумма заказов, руб. (Текущий период)"
    top = result.sort_values(order_column, ascending=False).head(15).copy()
    top["Разрез"] = top[fields].fillna("(не указано)").astype(str).agg(" / ".join, axis=1)
    st.bar_chart(top.set_index("Разрез")[["Сумма заказов, руб. (Прошлый период)", order_column]], horizontal=True)
    output = BytesIO()
    result.to_excel(output, index=False, sheet_name="Сравнение", engine="openpyxl")
    st.download_button("Скачать таблицу Excel", output.getvalue(), file_name="project_comparison.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"project_export_{fields[0]}")


def _render_dynamics(ctx):
    df = ctx.get("project_comparison_df")
    filters = ctx.get("project_filters", {})
    base, current = filters.get("compare_base", ()), filters.get("compare_current", ())
    if df is None or len(base) != 2 or len(current) != 2:
        st.info("Загрузите проектные выгрузки и выберите два полных интервала в фильтрах.")
        return
    periods = compare_periods(df, base, current)
    data = distributor_comparison(periods)
    if data.empty:
        st.info("По выбранным фильтрам и периодам предложений нет.")
        return
    st.caption(f"Периоды по дате создания предложений: {base[0]:%d.%m.%Y}–{base[1]:%d.%m.%Y} и {current[0]:%d.%m.%Y}–{current[1]:%d.%m.%Y}.")
    if (base[0].month, base[0].day, base[1].month, base[1].day) != (current[0].month, current[0].day, current[1].month, current[1].day):
        st.warning("Выбранные календарные интервалы различаются; сравнение может быть несопоставимым.")
    labels = [f"{p[0]:%d.%m.%Y}–{p[1]:%d.%m.%Y}" for p in (base, current)]
    height = 600
    count_chart = go.Figure()
    for suffix, label, color in zip(("прошлый", "текущий"), labels, ("#94A3B8", "#4F46E5")):
        count_chart.add_bar(x=data.index, y=data[f"Количество — {suffix}"], name=label, marker_color=color, hovertemplate="%{x}<br>Предложений: %{y:,.0f}<extra>%{fullData.name}</extra>")
    count_chart.update_layout(title="Количество предложений по дистрибьюторам", barmode="group", xaxis_title="Дистрибьютор", yaxis_title="Количество предложений", height=height, margin=dict(l=10, r=20, t=60, b=40))
    count_chart.update_xaxes(automargin=True, tickangle=-45)
    st.plotly_chart(count_chart, width="stretch", key="project_dynamics_count")

    money_chart = go.Figure()
    for metric, suffix, label, color in (("Предложения", "прошлый", labels[0], "#94A3B8"), ("Предложения", "текущий", labels[1], "#4F46E5"), ("Заказы", "прошлый", labels[0], "#CBD5E1"), ("Заказы", "текущий", labels[1], "#B45309")):
        money_chart.add_bar(x=data.index, y=data[f"{metric} — {suffix}"], name=f"{metric}: {label}", marker_color=color, hovertemplate="%{x}<br>%{y:,.2f} ₽<extra>%{fullData.name}</extra>")
    money_chart.update_layout(title="Суммы предложений и заказов по дистрибьюторам", barmode="group", xaxis_title="Дистрибьютор", yaxis_title="Сумма без НДС, ₽", height=height, margin=dict(l=10, r=20, t=60, b=40))
    money_chart.update_xaxes(automargin=True, tickangle=-45)
    st.plotly_chart(money_chart, width="stretch", key="project_dynamics_amount")
    st.caption("Предложения — стоимость для дистрибьютора без НДС. Заказы отнесены к дате создания предложения, а не к дате заказа.")
    if any(part.empty for part in periods):
        st.warning("В одном из выбранных интервалов нет записей. Проверьте выгрузки и фильтры.")


def _render_overview(ctx: dict | None = None):
    """Отображает дашборд проектного взаимодействия."""
    ctx = ctx or {}
    df = ctx.get("project_df")
    if df is None or df.empty:
        st.title("🤝 Проектное взаимодействие")
        st.info("Загрузите выгрузку проектного взаимодействия (.xlsx) в боковой панели.")
        return

    filtered = ctx.get("project_filtered_df")
    if filtered is None:
        filtered = df.copy()
    else:
        filtered = filtered.copy()

    year, filtered = latest_year_rows(df, filtered)
    if year is None:
        st.warning("В загруженных данных нет корректных дат создания.")
        return
    if filtered.empty:
        st.warning("По выбранным фильтрам записей нет. Измените параметры фильтрации.")
        return

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
