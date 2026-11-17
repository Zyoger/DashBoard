"""Русский Свет: обзор, динамика, офисы и месячный план."""
from hashlib import sha1
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from tabs.tab_dynamics import MONTH_NAMES, fmt_rub, _common_months
from tabs.tab_etm import _display_df, _pct, _status, _city_zone
from rs_plans import COLUMNS, parse_quarterly_plans, quarterly_to_monthly

RS_NAME = "русский свет"
COLORS = ("#94A3B8", "#4F46E5", "#B45309")
PREV, FACT, PLAN = "Факт базового года", "Факт отчётного года", "План"
VALUE = "Сумма_без_НДС"
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "outputs/01a1e535-rs-plans/rs_quarterly_plan_template.xlsx"


def reset_sidebar_filters():
    for key in list(st.session_state):
        if key.startswith("rs_sidebar_"):
            st.session_state.pop(key, None)


def _reset_geography_dependents():
    # География задаёт новую область: прежние дочерние ограничения не должны
    # скрывать вновь добавленные города и материалы.
    for key in ("rs_sidebar_cities", "rs_sidebar_materials"):
        st.session_state.pop(key, None)
        st.session_state.pop(f"{key}_options", None)


def _filter_multiselect(label, options, key, follow_options=False, on_change=None):
    options = list(options)
    options_key = f"{key}_options"
    if key not in st.session_state or (
        follow_options and st.session_state[key] == st.session_state.get(options_key)
    ):
        st.session_state[key] = options
    else:
        st.session_state[key] = [value for value in st.session_state[key] if value in options]
    if follow_options:
        st.session_state[options_key] = options
    return st.multiselect(label, options, key=key, on_change=on_change)


def sidebar_filters(sales, expanded=False):
    """Независимые фильтры РС, построенные на полной исходной выгрузке."""
    source = sales.loc[sales["Дистрибьютор"].astype(str).str.strip().str.casefold() == RS_NAME]
    result = {"base": source, "base_year": None, "curr_year": None, "rs_months": []}
    with st.expander("🟦 Фильтры Русского Света", expanded=expanded, key="main_filter_rs", on_change="rerun"):
        if source.empty:
            st.info("В файле продаж нет строк дистрибьютора «Русский Свет».")
            return result
        zones = source["Город"].map(_city_zone)
        geography = _filter_multiselect("География РС", sorted(zones.unique()), "rs_sidebar_geography",
                                        on_change=_reset_geography_dependents)
        scoped = source.loc[zones.isin(geography)]
        cities = _filter_multiselect("Город / офис РС", sorted(scoped["Город"].dropna().unique()), "rs_sidebar_cities", follow_options=True)
        materials = _filter_multiselect("Материал РС", sorted(scoped["Материал"].dropna().unique()), "rs_sidebar_materials", follow_options=True)
        years = sorted(int(year) for year in source["Год"].dropna().unique())
        if not years:
            return result
        for key, default in (("rs_sidebar_base_year", years[max(0, len(years)-2)]),
                             ("rs_sidebar_curr_year", years[-1])):
            if st.session_state.get(key) not in years:
                st.session_state[key] = default
        base_year = st.selectbox("Базовый год РС", years, key="rs_sidebar_base_year")
        curr_year = st.selectbox("Отчётный год РС", years, key="rs_sidebar_curr_year")
        if base_year == curr_year:
            st.caption("Для сравнения год к году выберите разные годы.")
        available = _common_months(source, base_year, curr_year)
        months = []
        if available:
            if st.session_state.get("rs_sidebar_start") not in available:
                st.session_state["rs_sidebar_start"] = available[0]
            start = st.selectbox("Период РС с", available, key="rs_sidebar_start",
                                 format_func=lambda month: MONTH_NAMES[month-1])
            end_options = [month for month in available if month >= start]
            if st.session_state.get("rs_sidebar_end") not in end_options:
                st.session_state["rs_sidebar_end"] = end_options[-1]
            end = st.selectbox("Период РС по", end_options, key="rs_sidebar_end",
                               format_func=lambda month: MONTH_NAMES[month-1])
            months = [month for month in available if start <= month <= end]
        st.button("Сбросить фильтры РС", key="rs_sidebar_reset", on_click=reset_sidebar_filters)
        return {"base": scoped.loc[scoped["Город"].isin(cities) & scoped["Материал"].isin(materials)].copy(),
                "base_year": base_year, "curr_year": curr_year, "rs_months": months}


def _store_quarterly_plans(frame, cities):
    names = {str(city).strip().casefold(): city for city in cities}
    unknown = [name for name in frame["Филиал"].unique() if name.casefold() not in names]
    if unknown:
        raise ValueError("Филиалы не найдены в выгрузке продаж: " + ", ".join(unknown))
    frame = frame.copy()
    frame["Филиал"] = frame["Филиал"].map(lambda name: names[name.casefold()])
    monthly = quarterly_to_monthly(frame)
    st.session_state.setdefault("rs_plans_by_year", {}).update(monthly)
    st.session_state["rs_plan_revision"] = st.session_state.get("rs_plan_revision", 0) + 1


def load_quarterly_upload(uploaded, cities):
    if uploaded is not None:
        signature = (sha1(uploaded.getvalue()).hexdigest(), tuple(cities))
        if st.session_state.get("rs_plan_last_upload") == signature:
            return
        st.session_state["rs_plan_last_upload"] = signature
    else:
        st.session_state.pop("rs_plan_last_upload", None)
    st.session_state.pop("rs_plan_upload_error", None)
    st.session_state.pop("rs_plan_upload_success", None)
    if uploaded is None:
        return
    try:
        frame = parse_quarterly_plans(uploaded.getvalue())
        _store_quarterly_plans(frame, cities)
        years = ", ".join(str(y) for y in sorted(frame["Год"].unique()))
        st.session_state["rs_plan_upload_success"] = f"Загружено строк: {len(frame)}. Заменены планы за годы: {years}."
    except Exception as exc:
        st.session_state["rs_plan_upload_error"] = f"План не загружен: {exc}"


def _quarterly_editor(plan):
    return pd.DataFrame({f"{q} квартал": plan.reindex(columns=MONTH_NAMES[(q-1)*3:q*3], fill_value=0).sum(axis=1).round(2)
                         for q in range(1, 5)}, index=plan.index)


def _on_plan_upload(cities):
    load_quarterly_upload(st.session_state.get("rs_quarterly_upload"), cities)


def _summary(frame, field, base_year, curr_year):
    result = pd.concat([frame.loc[frame["Год"] == y].groupby(field)[VALUE].sum().rename(label)
                        for y, label in ((base_year, PREV), (curr_year, FACT))], axis=1).fillna(0)
    result["Изменение продаж"] = result[FACT] - result[PREV]
    result["YoY, %"] = result["Изменение продаж"].div(result[PREV].where(result[PREV] != 0)).mul(100)
    return result


def _table(frame, base_year, curr_year):
    base_label = f"Факт {base_year}" + (" (база)" if base_year == curr_year else "")
    st.dataframe(_display_df(frame.rename(columns={PREV: base_label, FACT: f"Факт {curr_year}"})),
                 width="stretch", hide_index=True, alt="Сводные показатели Русского Света")


def _series_chart(frame, base_year, curr_year, cumulative=False, bars=False):
    fig = go.Figure()
    for field, name, color, dash in ((PREV, f"Факт {base_year}", COLORS[0], "dash"),
                                    (FACT, f"Факт {curr_year}", COLORS[1], "solid"),
                                    (PLAN, f"План {curr_year}", COLORS[2], "dot")):
        if bars and field == PREV:
            continue
        values = frame[field].cumsum() if cumulative else frame[field]
        if bars:
            trace = go.Bar(x=frame.index, y=values, name=name, marker_color=color)
        else:
            trace = go.Scatter(x=frame.index, y=values, name=name, mode="lines+markers",
                               line=dict(color=color, dash=dash), marker_color=color)
        fig.add_trace(trace)
    fig.update_layout(barmode="group", hovermode="x unified", yaxis_title="Сумма без НДС, руб.",
                      xaxis_title="Месяц", height=420)
    return fig


def _contribution(frame, label, base_total, base_year, curr_year, key):
    data = frame[[PREV, FACT, "Изменение продаж"]].sort_values("Изменение продаж").copy()
    data["Вклад в общий YoY, п.п."] = data["Изменение продаж"].div(base_total if base_total else float("nan")).mul(100)
    fig = go.Figure(go.Bar(x=data["Изменение продаж"], y=data.index, orientation="h",
                           marker_color=["#2ca02c" if v >= 0 else "#d62728" for v in data["Изменение продаж"]]))
    fig.add_vline(x=0, line_color="gray")
    fig.update_layout(xaxis_title=f"Факт {curr_year} − факт {base_year}, руб.", yaxis_title="",
                      height=max(360, len(data) * 28 + 100))
    st.plotly_chart(fig, width="stretch", key=key, alt=f"Вклад {label} в изменение продаж")
    _table(data.reset_index(), base_year, curr_year)


def _prepare(ctx):
    base_year, curr_year, base = ctx["base_year"], ctx["curr_year"], ctx["base"]
    if base.empty or base_year is None or curr_year is None:
        return None
    rs = base.loc[base["Дистрибьютор"].astype(str).str.strip().str.casefold() == RS_NAME].copy()
    if rs.empty:
        return None
    months = ctx.get("rs_months", _common_months(rs, base_year, curr_year))
    if not months:
        return None
    period = rs.loc[rs["Год"].isin([base_year, curr_year]) & rs["Месяц"].isin(months)]
    if period.empty:
        return None
    offices = _summary(period, "Город", base_year, curr_year)
    materials = _summary(period, "Материал", base_year, curr_year)
    # План редактируется по всем филиалам файла, независимо от текущих фильтров.
    source = ctx.get("sales", base)
    full_rs = source.loc[source["Дистрибьютор"].astype(str).str.strip().str.casefold() == RS_NAME]
    cities = sorted(full_rs["Город"].dropna().unique())
    if "rs_plans_by_year" not in st.session_state:
        legacy = st.session_state.get("rs_plans")
        st.session_state["rs_plans_by_year"] = {curr_year: legacy} if legacy is not None else {}
    stored = st.session_state["rs_plans_by_year"].get(curr_year, pd.DataFrame())
    plan = stored.reindex(index=sorted(set(cities) | set(stored.index)),
                          columns=MONTH_NAMES, fill_value=0)
    plan = plan.apply(pd.to_numeric, errors="coerce").fillna(0).clip(lower=0)
    plan.index.name = "Филиал"
    selected_plan = plan.reindex(index=offices.index, columns=[MONTH_NAMES[m - 1] for m in months], fill_value=0)
    offices[PLAN] = selected_plan.sum(axis=1)
    offices["Выполнение, %"] = offices[FACT].div(offices[PLAN].where(offices[PLAN] != 0)).mul(100)
    offices["Отклонение от плана"] = offices[FACT] - offices[PLAN]
    offices["Статус"] = [_status(e, y) for e, y in zip(offices["Выполнение, %"], offices["YoY, %"])]
    monthly = _summary(period, "Месяц", base_year, curr_year).reindex(months, fill_value=0)
    monthly.index = [MONTH_NAMES[m - 1] for m in months]
    monthly.index.name = "Месяц"
    monthly[PLAN] = selected_plan.sum(axis=0)
    monthly["Выполнение, %"] = monthly[FACT].div(monthly[PLAN].where(monthly[PLAN] != 0)).mul(100)
    monthly["Отклонение от плана"] = monthly[FACT] - monthly[PLAN]
    matrix = period.loc[period["Год"] == curr_year].pivot_table(index="Город", columns="Месяц", values=VALUE, aggfunc="sum", fill_value=0)
    matrix = matrix.reindex(index=offices.index, columns=months, fill_value=0)
    matrix.columns = selected_plan.columns
    heatmap = matrix.div(selected_plan.where(selected_plan != 0)).mul(100)
    return period, months, offices, materials, monthly, plan, selected_plan, heatmap


def render(ctx):
    st.title("Русский Свет")
    prepared = _prepare(ctx)
    if prepared is None:
        st.info("По выбранным фильтрам нет продаж дистрибьютора «Русский Свет».")
        return
    period, months, offices, materials, monthly, plan, selected_plan, heatmap = prepared
    base_year, curr_year = ctx["base_year"], ctx["curr_year"]
#   st.caption("Офисы представлены городами из выгрузки. Сопоставимые месяцы: " + ", ".join(MONTH_NAMES[m - 1] for m in months))
#   st.caption("Квартальный план загружается на вкладке «План». У каждого квартала своя сумма, которая делится на его три месяца. Фильтр материалов изменяет факт, но не план филиала.")
    overview_tab, dynamics_tab, offices_tab, plan_tab = st.tabs(["📊 Обзор", "📈 Динамика", "🏙 По Офисам", "🎯 План"])
    actual, previous, target = monthly[FACT].sum(), monthly[PREV].sum(), monthly[PLAN].sum()
    execution, yoy = _pct(actual, target), _pct(actual - previous, previous)
    ranking = offices.sort_values(["Выполнение, %", FACT], ascending=[True, False], na_position="last")
    with overview_tab:
        st.subheader("Ключевые показатели")
        cols = st.columns(5)
        cols[0].metric(f"Факт {curr_year}", fmt_rub(actual), delta=f"{yoy:+.1f}% к {base_year}" if yoy is not None else "нет базы для YoY")
        cols[1].metric(f"План {curr_year}", fmt_rub(target))
        cols[2].metric("Выполнение плана", f"{execution:.1f}%" if execution is not None else "—")
        cols[3].metric("Отклонение от плана", fmt_rub(actual - target))
        cols[4].metric(f"Факт {base_year}", fmt_rub(previous))
        st.subheader(f"Вклад в изменение продаж: {base_year} → {curr_year}")
        st.caption("Изменение — разница факта двух лет. Вклад в общий YoY — эта разница, делённая на общий факт базового года, в процентных пунктах.")
        left, right = st.columns(2)
        with left:
            st.markdown("### По офисам")
            _contribution(offices, "Город", previous, base_year, curr_year, "rs_contribution_offices")
        with right:
            st.markdown("### По материалам")
            _contribution(materials, "Материал", previous, base_year, curr_year, "rs_contribution_materials")
        st.subheader("Динамика по месяцам")
        st.plotly_chart(_series_chart(monthly, base_year, curr_year), width="stretch", key="rs_overview_monthly", alt="Факт двух лет и месячный план Русского Света")
        st.subheader("Сравнение офисов")
        left, right = st.columns(2)
        with left:
            _table(ranking.reset_index(), base_year, curr_year)
        with right:
            fig = go.Figure(go.Bar(x=offices.index, y=offices["Выполнение, %"], marker_color=COLORS[1]))
            fig.add_hline(y=100, line_dash="dash", annotation_text="План 100%")
            fig.update_layout(yaxis_title="Выполнение плана, %", xaxis_title="Офис")
            st.plotly_chart(fig, width="stretch", key="rs_office_comparison", alt="Выполнение плана по офисам")
        valid = offices.dropna(subset=["Выполнение, %"]).sort_values("Выполнение, %")
        left, right = st.columns(2)
        for col, title, position in ((left, "Лучший офис по выполнению", -1), (right, "Офис с наибольшим отставанием", 0)):
            value = f"{valid.index[position]} · {valid.iloc[position]['Выполнение, %']:.1f}%" if not valid.empty else "—"
            col.metric(title, value)
        st.subheader("Рейтинг офисов — зоны внимания вверху")
        _table(ranking.reset_index(), base_year, curr_year)
    with dynamics_tab:
        for title, key, cumulative, bars in (
            (f"Факт {base_year} и {curr_year} и план {curr_year} по месяцам", "trend", False, False),
            ("Накопительный итог за выбранный период", "cumulative", True, False),
            (f"Факт и план {curr_year} по месяцам", "plan", False, True),
        ):
            st.subheader(title)
            st.plotly_chart(_series_chart(monthly, base_year, curr_year, cumulative, bars), width="stretch", key=f"rs_{key}", alt=title)
        _table(monthly.reset_index(), base_year, curr_year)
        st.subheader("Выполнение плана по месяцам, %")
        fig = go.Figure(go.Bar(x=monthly.index, y=monthly["Выполнение, %"], marker_color=COLORS[1], text=monthly["Выполнение, %"], texttemplate="%{text:.1f}%"))
        fig.add_hline(y=100, line_dash="dash", annotation_text="План 100%")
        fig.update_layout(yaxis_title="Выполнение плана, %", xaxis_title="Месяц")
        st.plotly_chart(fig, width="stretch", key="rs_execution", alt="Выполнение плана Русского Света по месяцам")
        st.subheader("Выполнение плана: офис × месяц")
        fig = go.Figure(go.Heatmap(z=heatmap.to_numpy(dtype=float, na_value=float("nan")), x=heatmap.columns.tolist(), y=heatmap.index.tolist(), zmin=0, zmax=200, zmid=100,
                                  colorscale=[[0, "#d73027"], [.5, "#ffffbf"], [1, "#1a9850"]], colorbar=dict(title="Выполнение, %"), texttemplate="%{z:.1f}%", hoverongaps=False,
                                  hovertemplate="%{y}<br>%{x}<br>Выполнение: %{z:.1f}%<extra></extra>"))
        fig.update_layout(height=max(320, 32 * len(heatmap) + 140), xaxis_title="Месяц", yaxis_title="Офис", yaxis_autorange="reversed", plot_bgcolor="#eeeeee")
        st.plotly_chart(fig, width="stretch", key="rs_heatmap", alt="Месячное выполнение плана по офисам Русского Света")
        st.caption("При нулевом плане процент не рассчитывается. Цветовая шкала: 0–200%; значения выше 200% показаны насыщенным зелёным.")
    with offices_tab:
        st.caption("План задан по офисам; план по материалам не распределён.")
        for city in offices.sort_values(FACT, ascending=False).index:
            st.subheader(city)
            city_period = period.loc[period["Город"] == city]
            city_monthly = _summary(city_period, "Месяц", base_year, curr_year).reindex(months, fill_value=0)
            city_monthly.index = [MONTH_NAMES[m - 1] for m in months]
            city_monthly[PLAN] = selected_plan.loc[city]
            left, right = st.columns(2)
            with left:
                st.markdown(f"### Динамика по месяцам: {base_year} vs {curr_year}")
                st.plotly_chart(_series_chart(city_monthly, base_year, curr_year), width="stretch", key=f"rs_office_monthly_{city}", alt=f"Динамика факта и плана: {city}")
            with right:
                st.markdown(f"### Материалы по офису (ТОП-10): {base_year} vs {curr_year}")
                st.caption("ТОП-10 по сумме факта двух лет за сопоставимые месяцы.")
                top = _summary(city_period, "Материал", base_year, curr_year)
                top = top.assign(_total=top[PREV] + top[FACT]).nlargest(10, "_total").sort_values(FACT)
                fig = go.Figure()
                for field, year, color in ((PREV, base_year, COLORS[0]), (FACT, curr_year, COLORS[1])):
                    fig.add_trace(go.Bar(x=top[field], y=top.index, orientation="h", name=str(year), marker_color=color))
                fig.update_layout(barmode="group", height=420, xaxis_title="Сумма без НДС, руб.", yaxis_title="")
                st.plotly_chart(fig, width="stretch", key=f"rs_office_top_{city}", alt=f"ТОП-10 материалов: {city}")
    with plan_tab:
        st.subheader(f"Квартальный план по филиалам — {curr_year}")
        st.caption("Первые два месяца получают по 1/3 квартального плана с округлением до копеек; третий — остаток. Например, 100 руб. = 33,33 + 33,33 + 33,34 руб.")
        if TEMPLATE_PATH.exists():
            st.download_button("Скачать Excel-шаблон квартальных планов", data=TEMPLATE_PATH.read_bytes(),
                               file_name="rs_quarterly_plan_template.xlsx", key="rs_plan_template",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("Файл заменяет планы указанных годов целиком. Неуказанные филиалы и кварталы этих годов получают нулевой план. Названия филиалов должны совпадать с городами в выгрузке продаж.")
        source = ctx.get("sales", ctx["base"])
        cities = sorted(source.loc[
            source["Дистрибьютор"].astype(str).str.strip().str.casefold() == RS_NAME,
            "Город",
        ].dropna().unique())
        st.file_uploader("Загрузить квартальный план (.xlsx)", type=["xlsx"],
                         key="rs_quarterly_upload", on_change=_on_plan_upload, args=(cities,))
        if st.session_state.get("rs_plan_upload_error"):
            st.error(st.session_state["rs_plan_upload_error"])
        if st.session_state.get("rs_plan_upload_success"):
            st.success(st.session_state["rs_plan_upload_success"])
        quarterly = _quarterly_editor(plan)
        editor_id = sha1(repr((curr_year, list(plan.index), st.session_state.get("rs_plan_revision", 0))).encode()).hexdigest()[:12]
        edited = st.data_editor(quarterly, width="stretch", key=f"rs_plans_editor_{editor_id}",
                                column_config={lbl: st.column_config.NumberColumn(lbl, min_value=0, step=1_000_000, format="%.2f") for lbl in quarterly.columns})
        if st.button("💾 Сохранить план РС", type="primary", key="rs_plans_save"):
            records = [[city, curr_year, q, edited.loc[city, f"{q} квартал"]]
                       for city in edited.index for q in range(1, 5)]
            try:
                _store_quarterly_plans(pd.DataFrame(records, columns=COLUMNS), edited.index)
                st.session_state.pop("rs_plan_upload_success", None)
                st.session_state.pop("rs_plan_upload_error", None)
                st.rerun()
            except ValueError as exc:
                st.error(f"План не сохранён: {exc}")
        st.subheader("Расчётное распределение по месяцам")
        st.dataframe(plan, width="stretch", alt="Месячный план, рассчитанный из квартального")
        st.caption("Планы хранятся только в памяти сессии. Для сравнения с фактом используются сопоставимые месяцы выбранных лет.")
        st.subheader("Выполнение плана по филиалам")
        _table(ranking.reset_index(), base_year, curr_year)
