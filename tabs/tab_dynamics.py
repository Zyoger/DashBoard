import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from io import BytesIO

MONTH_NAMES = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
               "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]


def fmt_rub(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def _common_months(df, y1, y2):
    m1 = set(df.loc[df["Год"] == y1, "Месяц"].dropna().astype(int))
    m2 = set(df.loc[df["Год"] == y2, "Месяц"].dropna().astype(int))
    if m1 and m2:
        return sorted(m1 & m2)
    return sorted(m1 | m2)


def _plan_total(plans, year_):
    if plans.empty:
        return 0.0
    p = plans[plans["Год"] == year_]
    return float(p["План_без_НДС"].fillna(0).sum())


def _plan_by_quarter(plans, year_):
    if plans.empty:
        return None
    p = (plans[plans["Год"] == year_]
         .groupby("Квартал", as_index=False)["План_без_НДС"].sum()
         .rename(columns={"План_без_НДС": "План"}))
    return p if not p.empty else None


def _render_overview(ctx):
    base = ctx["base"]
    plans = ctx["plans"]
    base_year = ctx["base_year"]
    curr_year = ctx["curr_year"]

    # ---------- сопоставимые месяцы ----------
    common_months = _common_months(base, base_year, curr_year)
    base_df = base[(base["Год"] == base_year) & (base["Месяц"].isin(common_months))]
    curr_df = base[(base["Год"] == curr_year) & (base["Месяц"].isin(common_months))]

    sales_base = float(base_df["Сумма_без_НДС"].sum())
    sales_curr = float(curr_df["Сумма_без_НДС"].sum())
    plan_base = _plan_total(plans, base_year)
    plan_curr = _plan_total(plans, curr_year)

    yoy_pct = (sales_curr / sales_base * 100 - 100) if sales_base else None
    exec_curr = (sales_curr / plan_curr * 100) if plan_curr else None

    st.caption(
        f"Сравнение: {base_year} vs {curr_year} · "
        f"сопоставимые месяцы: {', '.join(map(str, common_months)) if common_months else '—'}"
    )

    # ---------- KPI ----------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Продажи {curr_year}, руб", fmt_rub(sales_curr),
              delta=f"{sales_curr - sales_base:+,.0f} vs {base_year}".replace(",", " "))
    c2.metric(f"Продажи {base_year}, руб", fmt_rub(sales_base))
    c3.metric("YoY, %", f"{yoy_pct:+.1f}%" if yoy_pct is not None else "—",
              delta=(f"{sales_curr - sales_base:+,.0f} руб".replace(",", " ")
                     if sales_base else None))
    c4.metric(f"Выполнение плана {curr_year}",
              f"{exec_curr:.1f}%" if exec_curr is not None else "—",
              delta=(f"план {fmt_rub(plan_curr)}" if plan_curr else None))

    # ---------- план vs факт по кварталам ----------
    st.subheader(f"План vs факт по кварталам — {curr_year}")

    fact_q = (curr_df.groupby("Квартал", as_index=False)["Сумма_без_НДС"].sum()
              .rename(columns={"Сумма_без_НДС": "Факт"}))
    plan_q = _plan_by_quarter(plans, curr_year)

    if plan_q is not None:
        q_tbl = fact_q.merge(plan_q, on="Квартал", how="outer").fillna(0).sort_values("Квартал")
    else:
        q_tbl = fact_q.copy()
        q_tbl["План"] = 0

    q_tbl["Выполнение, %"] = q_tbl.apply(
        lambda r: round(r["Факт"] / r["План"] * 100, 1) if r["План"] else None, axis=1)
    q_tbl["Отклонение, руб"] = q_tbl["Факт"] - q_tbl["План"]

    colQ1, colQ2 = st.columns(2)
    with colQ1:
        figq = go.Figure()
        figq.add_trace(go.Bar(x=[f"Q{int(q)}" for q in q_tbl["Квартал"]],
                              y=q_tbl["Факт"], name="Факт"))
        figq.add_trace(go.Bar(x=[f"Q{int(q)}" for q in q_tbl["Квартал"]],
                              y=q_tbl["План"], name="План"))
        figq.update_layout(barmode="group", yaxis_title="Сумма без НДС, руб")
        st.plotly_chart(figq, width="stretch")
    with colQ2:
        q_display = q_tbl.copy()
        q_display["Квартал"] = q_display["Квартал"].apply(lambda q: f"Q{int(q)}")
        st.dataframe(
            q_display.style
            .format({
                "Факт": "{:,.0f}",
                "План": "{:,.0f}",
                "Выполнение, %": "{:.1f}%",
                "Отклонение, руб": "{:+,.0f}",
            }, thousands=" ", na_rep="—"),
            width="stretch", hide_index=True,
        )

    # ---------- динамика по месяцам ----------
    st.subheader(f"Динамика по месяцам: {base_year} vs {curr_year}")

    def monthly(df, year_):
        g = (df[df["Год"] == year_]
             .groupby("Месяц", as_index=False)["Сумма_без_НДС"].sum()
             .rename(columns={"Сумма_без_НДС": "Сумма"}))
        g["Год"] = year_
        return g

    m_base = monthly(base, base_year)
    m_curr = monthly(base, curr_year)

    fig = go.Figure()
    if not m_base.empty:
        fig.add_trace(go.Scatter(x=[MONTH_NAMES[int(m) - 1] for m in m_base["Месяц"]],
                                 y=m_base["Сумма"], mode="lines+markers",
                                 name=str(base_year)))
    if not m_curr.empty:
        fig.add_trace(go.Scatter(x=[MONTH_NAMES[int(m) - 1] for m in m_curr["Месяц"]],
                                 y=m_curr["Сумма"], mode="lines+markers",
                                 name=str(curr_year)))
    fig.update_layout(xaxis_title="Месяц", yaxis_title="Сумма без НДС, руб",
                      hovermode="x unified", legend_title="Год")
    st.plotly_chart(fig, width="stretch")

    # ---------- YoY по месяцам ----------
    st.subheader("YoY по месяцам")

    yoy_tbl = (
        m_base[["Месяц", "Сумма"]].rename(columns={"Сумма": f"{base_year}"})
        .merge(m_curr[["Месяц", "Сумма"]].rename(columns={"Сумма": f"{curr_year}"}),
               on="Месяц", how="outer")
        .sort_values("Месяц")
    )
    yoy_tbl["Месяц"] = yoy_tbl["Месяц"].map(lambda m: MONTH_NAMES[int(m) - 1])
    yoy_tbl["Δ абс., руб"] = yoy_tbl[f"{curr_year}"] - yoy_tbl[f"{base_year}"]
    yoy_tbl["Δ, %"] = yoy_tbl.apply(
        lambda r: round((r[f"{curr_year}"] / r[f"{base_year}"] - 1) * 100, 1)
        if r[f"{base_year}"] else None, axis=1)

    colA, colB = st.columns(2)
    with colA:
        st.dataframe(
            yoy_tbl.style
            .format({
                f"{base_year}": "{:,.0f}",
                f"{curr_year}": "{:,.0f}",
                "Δ абс., руб": "{:+,.0f}",
                "Δ, %": "{:+.1f}%",
            }, thousands=" ", na_rep="—"),
            width="stretch", hide_index=True,
        )
    with colB:
        yoy_plot = yoy_tbl.dropna(subset=["Δ, %"])
        if not yoy_plot.empty:
            colors = ["#2ca02c" if v >= 0 else "#d62728" for v in yoy_plot["Δ, %"]]
            fig2 = go.Figure(go.Bar(x=yoy_plot["Месяц"], y=yoy_plot["Δ, %"],
                                    marker_color=colors,
                                    text=[f"{v:+.1f}%" for v in yoy_plot["Δ, %"]],
                                    textposition="outside"))
            fig2.update_layout(yaxis_title="YoY, %", xaxis_title="Месяц")
            st.plotly_chart(fig2, width="stretch")

    # ---------- продажи по городам ----------
    st.subheader(f"Продажи по городам: {base_year} vs {curr_year}")

    city_base = (base[base["Год"] == base_year]
                 .groupby("Город", as_index=False)["Сумма_без_НДС"].sum()
                 .rename(columns={"Сумма_без_НДС": f"{base_year}"}))
    city_curr = (base[base["Год"] == curr_year]
                 .groupby("Город", as_index=False)["Сумма_без_НДС"].sum()
                 .rename(columns={"Сумма_без_НДС": f"{curr_year}"}))
    city_cmp = city_base.merge(city_curr, on="Город", how="outer").fillna(0)
    city_cmp["YoY, %"] = city_cmp.apply(
        lambda r: round((r[f"{curr_year}"] / r[f"{base_year}"] - 1) * 100, 1)
        if r[f"{base_year}"] else None, axis=1)
    city_cmp = city_cmp.sort_values(f"{curr_year}", ascending=False)

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=city_cmp["Город"], y=city_cmp[f"{base_year}"],
                          name=str(base_year)))
    fig3.add_trace(go.Bar(x=city_cmp["Город"], y=city_cmp[f"{curr_year}"],
                          name=str(curr_year)))
    fig3.update_layout(barmode="group", yaxis_title="Сумма без НДС, руб")
    st.plotly_chart(fig3, width="stretch")
    st.dataframe(
        city_cmp.style
        .format({
            f"{base_year}": "{:,.0f}",
            f"{curr_year}": "{:,.0f}",
            "YoY, %": "{:+.1f}%",
        }, thousands=" ", na_rep="—"),
        width="stretch", hide_index=True,
    )

    # ---------- структура по материалам ----------
    st.subheader(f"Структура по материалам: {base_year} vs {curr_year}")

    mat_base = (base[base["Год"] == base_year]
                .groupby("Материал", as_index=False)["Сумма_без_НДС"].sum()
                .rename(columns={"Сумма_без_НДС": f"{base_year}"}))
    mat_curr = (base[base["Год"] == curr_year]
                .groupby("Материал", as_index=False)["Сумма_без_НДС"].sum()
                .rename(columns={"Сумма_без_НДС": f"{curr_year}"}))
    mat_cmp = mat_base.merge(mat_curr, on="Материал", how="outer").fillna(0)
    mat_cmp["YoY, %"] = mat_cmp.apply(
        lambda r: round((r[f"{curr_year}"] / r[f"{base_year}"] - 1) * 100, 1)
        if r[f"{base_year}"] else None, axis=1)

    # сортировка: от большего к меньшему по отчётному году
    mat_cmp = mat_cmp.sort_values(f"{curr_year}", ascending=False).reset_index(drop=True)

    colMat1, colMat2 = st.columns(2)
    with colMat1:
        # горизонтальный бар: чтобы сверху были бОльшие значения,
        # разворачиваем порядок категорий (Plotly рисует снизу вверх)
        mat_plot = mat_cmp.iloc[::-1]
        fig4 = go.Figure()
        fig4.add_trace(go.Bar(
            y=mat_plot["Материал"], x=mat_plot[f"{base_year}"],
            orientation="h", name=str(base_year),
        ))
        fig4.add_trace(go.Bar(
            y=mat_plot["Материал"], x=mat_plot[f"{curr_year}"],
            orientation="h", name=str(curr_year),
        ))
        fig4.update_layout(
            barmode="group",
            xaxis_title="Сумма без НДС, руб",
            yaxis_title="",
            height=600,
        )
        st.plotly_chart(fig4, width="stretch")
    with colMat2:
        st.dataframe(
            mat_cmp.style
            .format({
                f"{base_year}": "{:,.0f}",
                f"{curr_year}": "{:,.0f}",
                "YoY, %": "{:+.1f}%",
            }, thousands=" ", na_rep="—"),
            width="stretch", hide_index=True, height=600,
        )

    # ---------- редактор общего плана по кварталам ----------
    with st.expander("✏️ Общий план по кварталам — редактирование"):
        st.caption("Формат: Год | Квартал | План без НДС. План общий, "
                   "не привязан к дистрибьюторам. "
                   "Хранится в памяти сессии и не записывается на диск.")

        years_all = sorted(int(y) for y in ctx["sales"]["Год"].dropna().unique())

        edited = st.data_editor(
            plans,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "Год": st.column_config.SelectboxColumn(
                    "Год", options=years_all, required=True),
                "Квартал": st.column_config.SelectboxColumn(
                    "Квартал", options=[1, 2, 3, 4], required=True),
                "План_без_НДС": st.column_config.NumberColumn(
                    "План_без_НДС", min_value=0, step=1_000_000, format="%d"),
            },
            key="plans_editor",
        )

        col_a, col_b = st.columns([1, 1])
        if col_a.button("💾 Сохранить план", type="primary"):
            st.session_state["plans_df"] = edited
            st.success("План сохранён в рамках текущей сессии.")
            st.rerun()
        if col_b.button("↩️ Вернуть план по умолчанию"):
            st.session_state.pop("plans_df", None)
            st.rerun()


def _render_summary(ctx):
    """Иерархическая сводная: Дистрибьютор → Город, год + последний месяц."""
    base = ctx["base"]
    base_year = ctx["base_year"]
    curr_year = ctx["curr_year"]

    common_months = _common_months(base, base_year, curr_year)
    if not common_months:
        st.info("Нет общих месяцев для сравнения выбранных лет.")
        return

    period = base[
        base["Год"].isin([base_year, curr_year])
        & base["Месяц"].isin(common_months)
    ].copy()

    if period.empty:
        st.info("По выбранным фильтрам нет данных за сопоставимые месяцы.")
        return

    last_month = max(common_months)
    last_month_label = MONTH_NAMES[last_month - 1]

    # ---------- агрегация: год ----------
    grouped_year = (
        period.groupby(["Дистрибьютор", "Город", "Год"], dropna=False)["Сумма_без_НДС"]
        .sum()
        .unstack("Год", fill_value=0)
    )
    for year in (base_year, curr_year):
        if year not in grouped_year.columns:
            grouped_year[year] = 0.0
    grouped_year = grouped_year[[base_year, curr_year]].rename(columns={
        base_year: f"Отгрузки {base_year}",
        curr_year: f"Отгрузки {curr_year}",
    }).reset_index()

    # ---------- агрегация: последний месяц ----------
    period_last = period[period["Месяц"] == last_month].copy()
    grouped_month = (
        period_last.groupby(["Дистрибьютор", "Город", "Год"], dropna=False)["Сумма_без_НДС"]
        .sum()
        .unstack("Год", fill_value=0)
    )
    for year in (base_year, curr_year):
        if year not in grouped_month.columns:
            grouped_month[year] = 0.0
    grouped_month = grouped_month[[base_year, curr_year]].rename(columns={
        base_year: f"Отгрузки {last_month_label} {base_year}",
        curr_year: f"Отгрузки {last_month_label} {curr_year}",
    }).reset_index()

    grouped = grouped_year.merge(
        grouped_month, on=["Дистрибьютор", "Город"], how="outer"
    ).fillna(0)

    # имена колонок
    col_base = f"Отгрузки {base_year}"
    col_curr = f"Отгрузки {curr_year}"
    col_m_base = f"Отгрузки {last_month_label} {base_year}"
    col_m_curr = f"Отгрузки {last_month_label} {curr_year}"

    grouped["Изменение, руб."] = grouped[col_curr] - grouped[col_base]
    grouped["Динамика, %"] = grouped.apply(
        lambda r: (
            (r[col_curr] / r[col_base] - 1) * 100
            if r[col_base] else (100.0 if r[col_curr] > 0 else 0.0)
        ),
        axis=1,
    )
    grouped["Изменение мес., руб."] = grouped[col_m_curr] - grouped[col_m_base]
    grouped["Динамика мес., %"] = grouped.apply(
        lambda r: (
            (r[col_m_curr] / r[col_m_base] - 1) * 100
            if r[col_m_base] else (100.0 if r[col_m_curr] > 0 else 0.0)
        ),
        axis=1,
    )

    # ---------- сборка иерархии: дистрибьютор → город ----------
    rows = []
    total_base = float(grouped[col_base].sum())
    total_curr = float(grouped[col_curr].sum())
    total_m_base = float(grouped[col_m_base].sum())
    total_m_curr = float(grouped[col_m_curr].sum())

    dist_order = (
        grouped.groupby("Дистрибьютор", dropna=False)[col_curr]
        .sum()
        .sort_values(ascending=False)
        .index
    )

    for dist in dist_order:
        dist_rows = grouped[grouped["Дистрибьютор"] == dist]
        d_base = float(dist_rows[col_base].sum())
        d_curr = float(dist_rows[col_curr].sum())
        d_m_base = float(dist_rows[col_m_base].sum())
        d_m_curr = float(dist_rows[col_m_curr].sum())
        d_change = d_curr - d_base
        d_dyn = (d_curr / d_base - 1) * 100 if d_base else (100.0 if d_curr > 0 else 0.0)
        d_m_change = d_m_curr - d_m_base
        d_m_dyn = (d_m_curr / d_m_base - 1) * 100 if d_m_base else (100.0 if d_m_curr > 0 else 0.0)

        rows.append({
            "Уровень": 0,
            "Наименование": str(dist),
            col_base: d_base,
            col_curr: d_curr,
            f"Доля {base_year}, %": (d_base / total_base * 100) if total_base else 0.0,
            f"Доля {curr_year}, %": (d_curr / total_curr * 100) if total_curr else 0.0,
            "Изменение, руб.": d_change,
            "Динамика, %": d_dyn,
            col_m_base: d_m_base,
            col_m_curr: d_m_curr,
            f"Доля {last_month_label} {base_year}, %": (d_m_base / total_m_base * 100) if total_m_base else 0.0,
            f"Доля {last_month_label} {curr_year}, %": (d_m_curr / total_m_curr * 100) if total_m_curr else 0.0,
            "Изменение мес., руб.": d_m_change,
            "Динамика мес., %": d_m_dyn,
        })

        city_rows = dist_rows.sort_values(col_curr, ascending=False)
        for _, r in city_rows.iterrows():
            rows.append({
                "Уровень": 1,
                "Наименование": str(r["Город"]),
                col_base: float(r[col_base]),
                col_curr: float(r[col_curr]),
                f"Доля {base_year}, %": (r[col_base] / total_base * 100) if total_base else 0.0,
                f"Доля {curr_year}, %": (r[col_curr] / total_curr * 100) if total_curr else 0.0,
                "Изменение, руб.": float(r["Изменение, руб."]),
                "Динамика, %": float(r["Динамика, %"]),
                col_m_base: float(r[col_m_base]),
                col_m_curr: float(r[col_m_curr]),
                f"Доля {last_month_label} {base_year}, %": (r[col_m_base] / total_m_base * 100) if total_m_base else 0.0,
                f"Доля {last_month_label} {curr_year}, %": (r[col_m_curr] / total_m_curr * 100) if total_m_curr else 0.0,
                "Изменение мес., руб.": float(r["Изменение мес., руб."]),
                "Динамика мес., %": float(r["Динамика мес., %"]),
            })

    total_change = total_curr - total_base
    total_dyn = (total_curr / total_base - 1) * 100 if total_base else (100.0 if total_curr > 0 else 0.0)
    total_m_change = total_m_curr - total_m_base
    total_m_dyn = (total_m_curr / total_m_base - 1) * 100 if total_m_base else (100.0 if total_m_curr > 0 else 0.0)

    rows.append({
        "Уровень": 0,
        "Наименование": "ИТОГО",
        col_base: total_base,
        col_curr: total_curr,
        f"Доля {base_year}, %": 100.0 if total_base else 0.0,
        f"Доля {curr_year}, %": 100.0 if total_curr else 0.0,
        "Изменение, руб.": total_change,
        "Динамика, %": total_dyn,
        col_m_base: total_m_base,
        col_m_curr: total_m_curr,
        f"Доля {last_month_label} {base_year}, %": 100.0 if total_m_base else 0.0,
        f"Доля {last_month_label} {curr_year}, %": 100.0 if total_m_curr else 0.0,
        "Изменение мес., руб.": total_m_change,
        "Динамика мес., %": total_m_dyn,
    })

    summary = pd.DataFrame(rows)

    months_label = ", ".join(MONTH_NAMES[m - 1] for m in common_months)
    st.caption(
        f"Иерархия: Дистрибьютор → Город. Год: {base_year} vs {curr_year} · "
        f"сопоставимые месяцы: {months_label}. "
        f"Последний месяц сравнения: {last_month_label}. "
        "Доля рассчитана от общего объёма отгрузок в каждом периоде."
    )

    # ---------- отображение: отступы для городов ----------
    summary_display = summary.drop(columns=["Уровень"]).copy()
    summary_display["Наименование"] = [
        ("    └ " + str(name)) if lvl == 1 else str(name)
        for name, lvl in zip(summary["Наименование"], summary["Уровень"])
    ]

    # ---------- стилизация ----------
    COLOR_TEXT = "#1a1a1a"
    COLOR_TEXT_MUTED = "#444444"
    COLOR_BG_DIST = "#e8eef5"
    COLOR_BG_TOTAL = "#d4dde8"
    COLOR_BG_ROW = "#ffffff"
    COLOR_UP = "#1b7f3b"
    COLOR_DOWN = "#c0392b"

    COLOR_MONTH_HEADER = "#2e6b8f"
    COLOR_MONTH_CELL = "#eaf4f8"
    COLOR_MONTH_MUTED = "#3f6b7d"

    month_cols = {
        col_m_base, col_m_curr,
        f"Доля {last_month_label} {base_year}, %",
        f"Доля {last_month_label} {curr_year}, %",
        "Изменение мес., руб.", "Динамика мес., %",
    }

    def _style_row(row):
        idx = row.name
        level = summary.iloc[idx]["Уровень"]
        name = summary.iloc[idx]["Наименование"]

        row_styles = []
        for col in row.index:
            is_month = col in month_cols
            if name == "ИТОГО":
                bg = COLOR_BG_TOTAL
                fg = COLOR_TEXT
                weight = "700"
                extra = "border-top: 2px solid #1f4e79;"
            elif level == 0:
                bg = COLOR_BG_DIST
                fg = COLOR_TEXT
                weight = "600"
                extra = ""
            else:
                bg = COLOR_BG_ROW
                fg = COLOR_TEXT_MUTED
                weight = "400"
                extra = ""

            if is_month:
                bg = COLOR_MONTH_CELL if name != "ИТОГО" else COLOR_BG_TOTAL
                fg = COLOR_MONTH_MUTED if level == 1 else COLOR_TEXT

            row_styles.append(
                f"background-color: {bg}; color: {fg}; font-weight: {weight}; {extra}"
            )
        return row_styles

    def _color_dynamic(value):
        if pd.isna(value):
            return ""
        if value > 0:
            return f"color: {COLOR_UP}; font-weight: 600;"
        if value < 0:
            return f"color: {COLOR_DOWN}; font-weight: 600;"
        return ""

    month_cols_list = [col_m_base, col_m_curr,
                       f"Доля {last_month_label} {base_year}, %",
                       f"Доля {last_month_label} {curr_year}, %",
                       "Изменение мес., руб.", "Динамика мес., %"]

    styled = (
        summary_display
        .style
        .hide(axis="index")
        .apply(_style_row, axis=1)
        .map(_color_dynamic, subset=["Динамика, %"])
        .map(_color_dynamic, subset=["Динамика мес., %"])
        .format({
            col_base: "{:,.0f}",
            col_curr: "{:,.0f}",
            f"Доля {base_year}, %": "{:.0f}%",
            f"Доля {curr_year}, %": "{:.0f}%",
            "Изменение, руб.": "{:+,.0f}",
            "Динамика, %": "{:+.0f}%",
            col_m_base: "{:,.0f}",
            col_m_curr: "{:,.0f}",
            f"Доля {last_month_label} {base_year}, %": "{:.0f}%",
            f"Доля {last_month_label} {curr_year}, %": "{:.0f}%",
            "Изменение мес., руб.": "{:+,.0f}",
            "Динамика мес., %": "{:+.0f}%",
        }, thousands=" ", na_rep="—")
        .set_table_styles([
            {"selector": "thead th",
             "props": [("background-color", "#1f4e79"),
                       ("color", "#ffffff"),
                       ("font-weight", "600"),
                       ("text-align", "right"),
                       ("padding", "8px"),
                       ("border-bottom", "2px solid #143a5c")]},
            {"selector": "thead th:first-child",
             "props": [("text-align", "left")]},
            *[
                {"selector": f"thead th:nth-child({i + 1})",
                 "props": [("background-color", COLOR_MONTH_HEADER)]}
                for i, col in enumerate(summary_display.columns)
                if col in month_cols_list
            ],
            {"selector": "tbody td",
             "props": [("padding", "6px 10px"),
                       ("border-bottom", "1px solid #e0e0e0"),
                       ("font-size", "13px")]},
            {"selector": "tbody td:not(:first-child)",
             "props": [("text-align", "right")]},
            {"selector": "tbody td:first-child",
             "props": [("text-align", "left")]},
            {"selector": "table",
             "props": [("width", "100%"),
                       ("border-collapse", "collapse"),
                       ("font-family", "Arial, sans-serif")]},
        ])
    )

    st.markdown(
        f'<div style="color:{COLOR_TEXT};">{styled.to_html(escape=False)}</div>',
        unsafe_allow_html=True,
    )

    # ---------- экспорт в Excel ----------
    excel_buffer = BytesIO()
    export = summary.drop(columns=["Уровень"]).copy()
    export["Наименование"] = [
        ("    " + str(name)) if lvl == 1 else str(name)
        for name, lvl in zip(summary["Наименование"], summary["Уровень"])
    ]
    export.to_excel(excel_buffer, index=False, engine="openpyxl")
    st.download_button(
        "⬇️ Скачать сводную таблицу (Excel)",
        data=excel_buffer.getvalue(),
        file_name=f"Сводная_иерархия_{base_year}_{curr_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_dynamics_pivot",
    )


def render(ctx):
    st.title("Динамика продаж")
    overview_tab, summary_tab = st.tabs(["Обзор", "Сводная таблица"])
    with overview_tab:
        _render_overview(ctx)
    with summary_tab:
        st.subheader("Сводная таблица отгрузок")
        if ctx["base"].empty:
            st.info("По выбранным фильтрам продаж нет данных.")
        else:
            _render_summary(ctx)