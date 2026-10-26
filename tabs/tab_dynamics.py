import streamlit as st
import plotly.graph_objects as go

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


def render(ctx):
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
    exec_base = (sales_base / plan_base * 100) if plan_base else None

    st.title("Динамика продаж")
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
        st.dataframe(
            q_tbl.rename(columns={"Квартал": "Квартал"}),
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
        st.dataframe(yoy_tbl, width="stretch", hide_index=True)
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
    st.dataframe(city_cmp, width="stretch", hide_index=True)

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
        st.dataframe(mat_cmp, width="stretch", hide_index=True, height=600)

    # ---------- редактор общего плана по кварталам ----------
    with st.expander("✏️ Общий план по кварталам — редактирование"):
        st.caption("Формат: Год | Квартал | План без НДС. План общий, "
                   "не привязан к дистрибьюторам.")

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

        from plans import save_plans
        col_a, col_b = st.columns([1, 1])
        if col_a.button("💾 Сохранить план", type="primary"):
            save_plans(edited)
            st.success("План сохранён в data/plans.csv")
            st.rerun()
        if col_b.button("🔄 Перечитать plans.csv"):
            st.rerun()