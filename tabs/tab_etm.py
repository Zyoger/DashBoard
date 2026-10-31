import re
from pathlib import Path
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ETM_PATH = Path("data/etm.xlsx")

# Годы анализа: базовый (факт прошлого года) и отчётный (план + факт).
BASE_YEAR = 2025
CURR_YEAR = 2026

DIM_NAMES = ["ПОК", "РК", "ДП", "Макрорегион ДКС", "ОП", "37 кл"]
DIMENSION_NAMES = ("Специализация", "Товарная категория")

MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

_MONTH_NUM = {name.casefold(): i + 1 for i, name in enumerate(MONTHS)}
_MONTH_ABBR = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


def _find_header_row(raw: pd.DataFrame, max_rows: int = 10) -> int:
    """Строка заголовков — та, где первая колонка равна «ПОК»."""
    for row_idx in range(min(max_rows, raw.shape[0])):
        if str(raw.iat[row_idx, 0]).strip().casefold() == "пок":
            return row_idx
    raise ValueError("Не найдена строка заголовков (колонка «ПОК»).")


def _month_columns(header: pd.Series, year: int, kind: str) -> dict[int, int]:
    """Находит колонки месяцев по тексту заголовков.

    kind="fact": заголовки вида «Январь 2026» (полное название + год).
    kind="plan": заголовки вида «ГО план янв26» (сокращение + две цифры года).
    Квартальные («1 кв.2026») и итоговые («ГО план 2026») колонки
    этим шаблонам не соответствуют и пропускаются.

    Возвращает {номер_месяца: индекс_колонки}.
    """
    result: dict[int, int] = {}
    for idx, value in header.items():
        if not isinstance(value, str):
            continue
        text = value.strip().casefold()
        if kind == "plan":
            match = re.fullmatch(
                r"го\s+план\s+([а-яё]{3})\s*" + str(year)[-2:], text
            )
            if match and match.group(1) in _MONTH_ABBR:
                result[_MONTH_ABBR[match.group(1)]] = idx
        else:
            match = re.fullmatch(r"([а-яё]+)\s+" + str(year), text)
            if match and match.group(1) in _MONTH_NUM:
                result[_MONTH_NUM[match.group(1)]] = idx
    return result

NORTH_CITIES = ("Ярославль", "Тверь", "Владимир", "Кострома", "Иваново")


def _city_zone(op_name) -> str:
    value = str(op_name).strip().casefold()
    return "Север" if any(city.casefold() in value for city in NORTH_CITIES) else "Юг"


@st.cache_data(show_spinner="Читаю выгрузку ЭТМ…")
def _read_etm(file_bytes: bytes, sheet_name: str) -> tuple[pd.DataFrame, list[int]]:
    """Читает лист выгрузки ЭТМ.

    Колонки находятся по тексту заголовков, а не по фиксированным позициям,
    поэтому добавление новых месяцев (например, ноября и декабря факта)
    и сдвиги колонок в выгрузке не ломают парсер.

    Возвращает (данные, отсортированный список месяцев с фактом отчётного года).
    """
    raw = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=None)

    header_row = _find_header_row(raw)
    header = raw.iloc[header_row]

    # Колонки измерений — по именам заголовков.
    dim_cols: dict[str, int] = {}
    dimension_col = None
    for idx, value in header.items():
        name = str(value).strip()
        if name in DIM_NAMES and name not in dim_cols:
            dim_cols[name] = idx
        if name in DIMENSION_NAMES and dimension_col is None:
            dimension_col = idx
    missing = [name for name in DIM_NAMES if name not in dim_cols]
    if missing:
        raise ValueError(
            f"Лист «{sheet_name}»: не найдены колонки измерений: {missing}"
        )
    if dimension_col is None:
        raise ValueError(
            f"Лист «{sheet_name}»: не найдена колонка разреза "
            f"(«Специализация» или «Товарная категория»)"
        )
    dimension_name = str(header.iloc[dimension_col]).strip()

    # Колонки месяцев — по шаблонам заголовков.
    fact_base = _month_columns(header, BASE_YEAR, "fact")
    plan_curr = _month_columns(header, CURR_YEAR, "plan")
    fact_curr = _month_columns(header, CURR_YEAR, "fact")
    if not fact_base:
        raise ValueError(
            f"Лист «{sheet_name}»: не найдены колонки факта {BASE_YEAR} "
            f"(«Январь {BASE_YEAR}» и т.д.)"
        )
    if not plan_curr:
        raise ValueError(
            f"Лист «{sheet_name}»: не найдены колонки плана {CURR_YEAR} "
            f"(«ГО план янв{str(CURR_YEAR)[-2:]}» и т.д.)"
        )
    if not fact_curr:
        raise ValueError(
            f"Лист «{sheet_name}»: не найдены колонки факта {CURR_YEAR} "
            f"(«Январь {CURR_YEAR}» и т.д.)"
        )

    body = raw.iloc[header_row + 1:].reset_index(drop=True)
    data = pd.DataFrame({name: body.iloc[:, idx] for name, idx in dim_cols.items()})
    data[dimension_name] = body.iloc[:, dimension_col]
    data["География"] = data["ОП"].map(_city_zone)

    for month, idx in fact_base.items():
        data[f"Факт_{month}_{BASE_YEAR}"] = pd.to_numeric(body.iloc[:, idx], errors="coerce").fillna(0)
    for month, idx in plan_curr.items():
        data[f"План_{month}_{CURR_YEAR}"] = pd.to_numeric(body.iloc[:, idx], errors="coerce").fillna(0)
    for month, idx in fact_curr.items():
        data[f"Факт_{month}_{CURR_YEAR}"] = pd.to_numeric(body.iloc[:, idx], errors="coerce").fillna(0)

    # Исключаем строки итогов, чтобы не задваивать суммы при группировках.
    text_cols = DIM_NAMES + [dimension_name]
    summary_mask = data[text_cols].astype(str).apply(
        lambda col: col.str.contains(r"итог|всего", case=False, na=False)
    ).any(axis=1)
    data = data.loc[~summary_mask].copy()
    data = data[data[dimension_name].notna()]
    data[dimension_name] = data[dimension_name].astype(str).str.strip()
    data = data[data[dimension_name] != ""]

    # Для разреза «Товарная категория» полностью исключаем эти группы:
    # они не попадут ни в фильтр категорий, ни в расчёты и сводные показатели.
    if dimension_name == "Товарная категория":
        excluded_categories = ("13К", "13О", "1Yh")
        category_codes = data[dimension_name].str.extract(r"^\s*([^\s\-–—]+)", expand=False).str.casefold()
        excluded_codes = {code.casefold() for code in excluded_categories}
        data = data.loc[~category_codes.isin(excluded_codes)].copy()

    for field in text_cols:
        data[field] = data[field].fillna("(пусто)").astype(str).str.strip()

    # В поле «ОП» могут находиться как офисы продаж (например, «Владимир ОП1»),
    # так и выставочно-торговые центры (например, «Владимир ВТЦ»).
    data["Тип подразделения"] = data["ОП"].str.contains(r"ВТЦ", case=False, na=False).map(
        {True: "ВТЦ", False: "ОП"}
    )
    return data.reset_index(drop=True), sorted(fact_curr)


def _fmt(value) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _display_df(frame: pd.DataFrame) -> pd.DataFrame:
    """Подготовка таблицы для интерфейса: целые числа и пробелы между разрядами."""
    result = frame.copy()
    for column in result.columns:
        if pd.api.types.is_numeric_dtype(result[column]):
            is_percent = "%" in str(column)
            def format_number(value):
                if pd.isna(value):
                    return "—"
                formatted = f"{float(value):,.0f}".replace(",", " ")
                return f"{formatted}%" if is_percent else formatted
            result[column] = result[column].map(format_number)
    return result


def _pct(numerator, denominator):
    return numerator / denominator * 100 if denominator else None


def _status(execution, yoy):
    if execution is not None and execution < 80:
        return "Критично"
    if execution is not None and execution < 100:
        return "Внимание"
    if yoy is not None and yoy < 0:
        return "Есть снижение"
    if execution is not None and execution >= 100:
        return "План выполнен"
    return "Нет данных"


def _aggregate(frame, group_fields, actual_cols, plan_cols, fact25_cols):
    grouped = frame.groupby(group_fields, dropna=False)[actual_cols + plan_cols + fact25_cols].sum().reset_index()
    grouped["Факт 2026"] = grouped[actual_cols].sum(axis=1)
    grouped["План 2026"] = grouped[plan_cols].sum(axis=1)
    grouped["Факт 2025"] = grouped[fact25_cols].sum(axis=1)
    grouped["Выполнение, %"] = grouped.apply(
        lambda row: _pct(row["Факт 2026"], row["План 2026"]), axis=1
    )
    grouped["Отклонение от плана"] = grouped["Факт 2026"] - grouped["План 2026"]
    grouped["Изменение к 2025, %"] = grouped.apply(
        lambda row: _pct(row["Факт 2026"] - row["Факт 2025"], row["Факт 2025"]), axis=1
    )
    return grouped


def _excel_report(summary, by_op, by_dimension, monthly, source_rows):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Обзор", index=False)
        by_op.to_excel(writer, sheet_name="По ОП", index=False)
        by_dimension.to_excel(writer, sheet_name="Категории и специализации", index=False)
        monthly.to_excel(writer, sheet_name="По месяцам", index=False)
        source_rows.to_excel(writer, sheet_name="Исходные строки", index=False)
    output.seek(0)
    return output.getvalue()


def render(ctx):
    st.title("ЭТМ — аналитика продаж")
    st.caption(
        "Обзор выполнения плана, динамики и структуры. Источники: «%ВП ГО DKC по спец» и «%ВП ГО DKC по ТГ». "
        "Загрузка файла и все фильтры находятся в общей боковой панели приложения."
    )

    etm_context = ctx.get("etm")
    if not etm_context:
        error = ctx.get("etm_error")
        if error:
            st.error(f"Не удалось подготовить данные ЭТМ: {error}")
        else:
            st.info("Загрузите Excel-файл ЭТМ и выберите фильтры в боковой панели.")
        return

    kind = etm_context["kind"]
    dimension = etm_context["dimension"]
    filtered = etm_context["filtered"].copy()
    period_end = etm_context["period_end"]

    if filtered.empty:
        st.warning("По выбранным фильтрам нет данных. Измените параметры фильтрации.")
        return

    available_months = etm_context["fact_months"]
    months = [month for month in available_months if month <= period_end]
    actual_cols = [f"Факт_{month}_{CURR_YEAR}" for month in months]
    plan_cols = [f"План_{month}_{CURR_YEAR}" for month in months]
    fact25_cols = [f"Факт_{month}_{BASE_YEAR}" for month in months]

    fact26 = float(filtered[actual_cols].sum().sum())
    plan26 = float(filtered[plan_cols].sum().sum())
    fact25 = float(filtered[fact25_cols].sum().sum())
    execution = _pct(fact26, plan26)
    yoy = _pct(fact26 - fact25, fact25)
    gap = fact26 - plan26

    st.caption(f"Период анализа: январь — {MONTHS[period_end - 1].lower()} 2026 года; сравнение YoY — с теми же месяцами 2025 года.")

    overview_tab, dynamics_tab, structure_tab, detail_tab = st.tabs(
        ["📊 Обзор", "📈 Динамика", "🧩 Структура", "📋 Детализация"]
    )

    # Данные для всех разделов
    by_op = _aggregate(filtered, ["География", "ОП"], actual_cols, plan_cols, fact25_cols)
    by_op["Статус"] = by_op.apply(
        lambda row: _status(row["Выполнение, %"], row["Изменение к 2025, %"]), axis=1
    )
    by_op = by_op.sort_values(["Выполнение, %", "Факт 2026"], ascending=[True, False], na_position="last")

    by_dimension = _aggregate(filtered, [dimension], actual_cols, plan_cols, fact25_cols)
    by_dimension["Доля в продажах, %"] = by_dimension["Факт 2026"].apply(
        lambda value: _pct(value, fact26)
    )
    by_dimension["Статус"] = by_dimension.apply(
        lambda row: _status(row["Выполнение, %"], row["Изменение к 2025, %"]), axis=1
    )
    by_dimension = by_dimension.sort_values("Факт 2026", ascending=False)

    by_geo = _aggregate(filtered, ["География"], actual_cols, plan_cols, fact25_cols)

    monthly_rows = []
    for month in months:
        a26 = float(filtered[f"Факт_{month}_{CURR_YEAR}"].sum())
        p26 = float(filtered[f"План_{month}_{CURR_YEAR}"].sum())
        a25 = float(filtered[f"Факт_{month}_{BASE_YEAR}"].sum())
        monthly_rows.append({
            "Месяц": MONTHS[month - 1],
            "Факт 2025": a25,
            "Факт 2026": a26,
            "План 2026": p26,
            "Выполнение, %": _pct(a26, p26),
            "Отклонение от плана": a26 - p26,
        })
    monthly = pd.DataFrame(monthly_rows)
    monthly["Накопительный факт 2025"] = monthly["Факт 2025"].cumsum()
    monthly["Накопительный факт 2026"] = monthly["Факт 2026"].cumsum()
    monthly["Накопительный план 2026"] = monthly["План 2026"].cumsum()

    with overview_tab:
        st.subheader("Ключевые показатели")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Факт 2026", _fmt(fact26), delta=f"{yoy:+.1f}% к 2025" if yoy is not None else "нет базы для YoY")
        k2.metric("План 2026", _fmt(plan26))
        k3.metric("Выполнение плана", f"{execution:.1f}%" if execution is not None else "—")
        k4.metric("Отклонение от плана", _fmt(gap), delta="выше плана" if gap >= 0 else "ниже плана", delta_color="normal" if gap >= 0 else "inverse")
        k5.metric("Факт 2025", _fmt(fact25))

        st.subheader("Сравнение Севера и Юга")
        if not by_geo.empty:
            geo_show = by_geo[["География", "Факт 2026", "План 2026", "Выполнение, %", "Факт 2025", "Изменение к 2025, %"]].copy()
            geo_show["Выполнение, %"] = geo_show["Выполнение, %"].round(1)
            geo_show["Изменение к 2025, %"] = geo_show["Изменение к 2025, %"].round(1)
            left, right = st.columns([1.15, 1])
            with left:
                st.dataframe(_display_df(geo_show), use_container_width=True, hide_index=True)
            with right:
                geo_fig = px.bar(
                    geo_show, x="География", y="Выполнение, %", color="География",
                    text="Выполнение, %", title="Выполнение плана по географии",
                )
                geo_fig.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="100%")
                geo_fig.update_layout(showlegend=False, yaxis_title="Выполнение плана, %", xaxis_title="")
                st.plotly_chart(geo_fig, use_container_width=True)
        else:
            st.info("Для сравнения выберите Север и Юг в фильтре «География».")

        best_op = by_op[by_op["Выполнение, %"].notna()].sort_values("Выполнение, %", ascending=False)
        weak_op = by_op[by_op["Выполнение, %"].notna()].sort_values("Выполнение, %", ascending=True)
        best_name = f"{best_op.iloc[0]['ОП']} · {best_op.iloc[0]['Выполнение, %']:.1f}%" if not best_op.empty else "—"
        weak_name = f"{weak_op.iloc[0]['ОП']} · {weak_op.iloc[0]['Выполнение, %']:.1f}%" if not weak_op.empty else "—"
        extra1, extra2 = st.columns(2)
        extra1.metric("Лучший ОП по выполнению", best_name)
        extra2.metric("ОП с наибольшим отставанием", weak_name)

        st.subheader("Рейтинг ОП — зоны внимания вверху")
        op_show = by_op[["География", "ОП", "Факт 2026", "План 2026", "Выполнение, %", "Изменение к 2025, %", "Отклонение от плана", "Статус"]].copy()
        for col in ["Выполнение, %", "Изменение к 2025, %"]:
            op_show[col] = op_show[col].round(1)
        st.dataframe(_display_df(op_show.head(30)), use_container_width=True, hide_index=True)

        st.subheader("Автоматические сигналы")
        critical = by_op[by_op["Статус"] == "Критично"].head(5)
        attention = by_op[by_op["Статус"].isin(["Внимание", "Есть снижение"])].head(5)
        if critical.empty and attention.empty:
            st.success("По выбранным фильтрам нет ОП с выполнением плана ниже 100% и отрицательной динамикой.")
        else:
            for _, row in critical.iterrows():
                st.error(
                    f"{row['ОП']} ({row['География']}): выполнение плана "
                    f"{row['Выполнение, %']:.1f}% — критическая зона."
                    if pd.notna(row["Выполнение, %"]) else f"{row['ОП']}: критическая зона, проверьте плановые данные."
                )
            for _, row in attention.iterrows():
                exec_text = f"{row['Выполнение, %']:.1f}%" if pd.notna(row["Выполнение, %"]) else "нет данных по плану"
                yoy_text = f"{row['Изменение к 2025, %']:+.1f}%" if pd.notna(row["Изменение к 2025, %"]) else "нет базы для сравнения"
                st.warning(f"{row['ОП']} ({row['География']}): выполнение {exec_text}; динамика к 2025 году {yoy_text}.")

    with dynamics_tab:
        st.subheader("Факт 2025 и 2026 по месяцам")
        trend_fig = go.Figure()
        trend_fig.add_trace(go.Scatter(x=monthly["Месяц"], y=monthly["Факт 2025"], mode="lines+markers", name="Факт 2025"))
        trend_fig.add_trace(go.Scatter(x=monthly["Месяц"], y=monthly["Факт 2026"], mode="lines+markers", name="Факт 2026"))
        trend_fig.update_layout(hovermode="x unified", yaxis_title="Значение из выгрузки", xaxis_title="Месяц")
        st.plotly_chart(trend_fig, use_container_width=True)

        st.subheader("Накопительный итог с начала года")
        cumulative_fig = go.Figure()
        cumulative_fig.add_trace(go.Scatter(x=monthly["Месяц"], y=monthly["Накопительный факт 2025"], mode="lines+markers", name="Факт 2025 YTD"))
        cumulative_fig.add_trace(go.Scatter(x=monthly["Месяц"], y=monthly["Накопительный факт 2026"], mode="lines+markers", name="Факт 2026 YTD"))
        cumulative_fig.add_trace(go.Scatter(x=monthly["Месяц"], y=monthly["Накопительный план 2026"], mode="lines+markers", name="План 2026 YTD", line=dict(dash="dash")))
        cumulative_fig.update_layout(hovermode="x unified", yaxis_title="Накопительное значение", xaxis_title="Месяц")
        st.plotly_chart(cumulative_fig, use_container_width=True)

        st.subheader("Факт и план 2026 по месяцам")
        plan_fig = go.Figure()
        plan_fig.add_trace(go.Bar(x=monthly["Месяц"], y=monthly["Факт 2026"], name="Факт 2026"))
        plan_fig.add_trace(go.Bar(x=monthly["Месяц"], y=monthly["План 2026"], name="План 2026"))
        plan_fig.update_layout(barmode="group", yaxis_title="Значение из выгрузки", xaxis_title="Месяц")
        st.plotly_chart(plan_fig, use_container_width=True)
        st.dataframe(_display_df(monthly), use_container_width=True, hide_index=True)

    with structure_tab:
        st.subheader(f"ТОП-10 {dimension.lower()} по факту 2026")
        top10 = by_dimension.head(10).sort_values("Факт 2026", ascending=True)
        top_fig = px.bar(top10, x="Факт 2026", y=dimension, orientation="h", text="Факт 2026")
        top_fig.update_layout(yaxis_title="", xaxis_title="Значение из выгрузки", height=520)
        st.plotly_chart(top_fig, use_container_width=True)

        st.subheader("Направления с наибольшим снижением к 2025 году")
        declines = by_dimension[by_dimension["Изменение к 2025, %"].notna()].sort_values("Изменение к 2025, %").head(10)
        if declines.empty:
            st.info("Нет направлений с базой для сравнения.")
        else:
            decline_show = declines[[dimension, "Факт 2025", "Факт 2026", "Изменение к 2025, %", "Выполнение, %", "Статус"]].copy()
            decline_show["Изменение к 2025, %"] = decline_show["Изменение к 2025, %"].round(1)
            decline_show["Выполнение, %"] = decline_show["Выполнение, %"].round(1)
            st.dataframe(_display_df(decline_show), use_container_width=True, hide_index=True)

        st.subheader("Полная структура")
        structure_show = by_dimension[[dimension, "Факт 2026", "Доля в продажах, %", "План 2026", "Выполнение, %", "Изменение к 2025, %", "Статус"]].copy()
        for col in ["Доля в продажах, %", "Выполнение, %", "Изменение к 2025, %"]:
            structure_show[col] = structure_show[col].round(1)
        st.dataframe(_display_df(structure_show), use_container_width=True, hide_index=True)

    with detail_tab:
        st.subheader("Детализация по ОП")
        st.dataframe(_display_df(by_op), use_container_width=True, hide_index=True)
        st.subheader(f"Детализация по {dimension.lower()}")
        st.dataframe(_display_df(by_dimension), use_container_width=True, hide_index=True)

        summary = pd.DataFrame([
            {"Показатель": "Факт 2026", "Значение": fact26},
            {"Показатель": "План 2026", "Значение": plan26},
            {"Показатель": "Выполнение плана, %", "Значение": execution},
            {"Показатель": "Факт 2025", "Значение": fact25},
            {"Показатель": "Изменение к 2025, %", "Значение": yoy},
            {"Показатель": "Отклонение от плана", "Значение": gap},
        ])
        report = _excel_report(summary, by_op, by_dimension, monthly, filtered)
        st.download_button(
            "📥 Скачать отчёт Excel",
            data=report,
            file_name=f"ETM_аналитика_{kind}_{period_end:02d}_2026.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.caption(
        "Единицы измерения не подписаны как рубли: в тестовой выгрузке их бизнес-смысл не подтверждён. "
        "Прогноз до конца года не рассчитывается, чтобы не выдавать простой пересчёт темпа за достоверный прогноз."
    )
