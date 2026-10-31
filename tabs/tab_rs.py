import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tabs.tab_dynamics import MONTH_NAMES, fmt_rub, _common_months

RS_NAME = "русский свет"


def render(ctx):
    st.title("Русский Свет")
    base = ctx["base"]
    base_year = ctx["base_year"]
    curr_year = ctx["curr_year"]

    rs = base[
        base["Дистрибьютор"].astype(str).str.strip().str.casefold() == RS_NAME
    ].copy()
    if rs.empty:
        st.info("По выбранным фильтрам нет продаж дистрибьютора «Русский Свет».")
        return

    common = _common_months(rs, base_year, curr_year)
    if not common:
        st.info("Нет общих месяцев для сравнения выбранных лет.")
        return

    period = rs[rs["Год"].isin([base_year, curr_year]) & rs["Месяц"].isin(common)]
    all_period = base[base["Год"].isin([base_year, curr_year]) & base["Месяц"].isin(common)]

    sales_base = float(period.loc[period["Год"] == base_year, "Сумма_без_НДС"].sum())
    sales_curr = float(period.loc[period["Год"] == curr_year, "Сумма_без_НДС"].sum())
    total_curr = float(all_period.loc[all_period["Год"] == curr_year, "Сумма_без_НДС"].sum())
    yoy = (sales_curr / sales_base - 1) * 100 if sales_base else None
    share = sales_curr / total_curr * 100 if total_curr else None
    cities = sorted(period["Город"].dropna().astype(str).unique())

    # ---------- KPI ----------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Продажи {curr_year}, руб", fmt_rub(sales_curr),
              delta=f"{sales_curr - sales_base:+,.0f} vs {base_year}".replace(",", " "))
    c2.metric("YoY, %", f"{yoy:+.1f}%" if yoy is not None else "—")
    c3.metric(f"Доля в продажах ЦО {curr_year}",
              f"{share:.1f}%" if share is not None else "—")
    c4.metric("Филиалов", len(cities))

    months_label = ", ".join(MONTH_NAMES[m - 1] for m in common)
    st.caption(f"Сопоставимые месяцы: {months_label}.")

    # ---------- по филиалам ----------
    st.subheader(f"Продажи по филиалам: {base_year} vs {curr_year}")

    city_base = (period[period["Год"] == base_year]
                 .groupby("Город")["Сумма_без_НДС"].sum().rename(f"{base_year}"))
    city_curr = (period[period["Год"] == curr_year]
                 .groupby("Город")["Сумма_без_НДС"].sum().rename(f"{curr_year}"))
    city_cmp = pd.concat([city_base, city_curr], axis=1).fillna(0).reset_index()
    city_cmp["Доля, %"] = city_cmp[f"{curr_year}"].apply(
        lambda v: round(v / sales_curr * 100, 1) if sales_curr else 0.0)
    city_cmp["YoY, %"] = city_cmp.apply(
        lambda r: round((r[f"{curr_year}"] / r[f"{base_year}"] - 1) * 100, 1)
        if r[f"{base_year}"] else None, axis=1)
    city_cmp = city_cmp.sort_values(f"{curr_year}", ascending=False)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=city_cmp["Город"], y=city_cmp[f"{base_year}"],
                         name=str(base_year)))
    fig.add_trace(go.Bar(x=city_cmp["Город"], y=city_cmp[f"{curr_year}"],
                         name=str(curr_year)))
    fig.update_layout(barmode="group", yaxis_title="Сумма без НДС, руб")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(
        city_cmp.style.format({
            f"{base_year}": "{:,.0f}",
            f"{curr_year}": "{:,.0f}",
            "Доля, %": "{:.1f}%",
            "YoY, %": "{:+.1f}%",
        }, thousands=" ", na_rep="—"),
        width="stretch", hide_index=True,
    )

    # ---------- динамика по месяцам ----------
    st.subheader("Динамика по месяцам")

    monthly = (period.groupby(["Город", "Год", "Месяц"])["Сумма_без_НДС"]
               .sum().reset_index())

    cities_sorted = (period[period["Год"] == curr_year]
                     .groupby("Город")["Сумма_без_НДС"].sum()
                     .sort_values(ascending=False).index.tolist())
    # города без продаж отчётного года — в конец
    cities_sorted += [c for c in cities if c not in cities_sorted]

    charts_per_row = 2
    for row_start in range(0, len(cities_sorted), charts_per_row):
        cols = st.columns(charts_per_row)
        for col, city in zip(cols, cities_sorted[row_start:row_start + charts_per_row]):
            city_data = monthly[monthly["Город"] == city]
            fig_city = go.Figure()
            for year, dash in ((base_year, "dash"), (curr_year, "solid")):
                year_data = city_data[city_data["Год"] == year].sort_values("Месяц")
                if year_data.empty:
                    continue
                fig_city.add_trace(go.Scatter(
                    x=[MONTH_NAMES[int(m) - 1] for m in year_data["Месяц"]],
                    y=year_data["Сумма_без_НДС"],
                    mode="lines+markers",
                    name=str(year),
                    line=dict(dash=dash),
                ))
            fig_city.update_layout(
                title=city,
                yaxis_title="Сумма без НДС, руб",
                xaxis_title="",
                hovermode="x unified",
                legend_title="Год",
                height=320,
                margin=dict(t=50, b=30),
            )
            with col:
                st.plotly_chart(fig_city, width="stretch")

    # ---------- YoY по месяцам (все филиалы) ----------
    m_base = (period[period["Год"] == base_year]
              .groupby("Месяц")["Сумма_без_НДС"].sum().rename(f"{base_year}"))
    m_curr = (period[period["Год"] == curr_year]
              .groupby("Месяц")["Сумма_без_НДС"].sum().rename(f"{curr_year}"))
    yoy_tbl = pd.concat([m_base, m_curr], axis=1).fillna(0).reset_index()
    yoy_tbl["Месяц"] = yoy_tbl["Месяц"].map(lambda m: MONTH_NAMES[int(m) - 1])
    yoy_tbl["Δ, %"] = yoy_tbl.apply(
        lambda r: round((r[f"{curr_year}"] / r[f"{base_year}"] - 1) * 100, 1)
        if r[f"{base_year}"] else None, axis=1)
    st.dataframe(
        yoy_tbl.style.format({
            f"{base_year}": "{:,.0f}",
            f"{curr_year}": "{:,.0f}",
            "Δ, %": "{:+.1f}%",
        }, thousands=" ", na_rep="—"),
        width="stretch", hide_index=True,
    )

    # ---------- структура по группам продукции (ТОП-10) ----------
    st.subheader(f"Группы продукции по городам (ТОП-10): {base_year} vs {curr_year}")
    st.caption("ТОП-10 материалов города по сумме двух лет за сопоставимые месяцы.")

    mat_city = (period.groupby(["Город", "Материал", "Год"])["Сумма_без_НДС"]
                .sum().reset_index())

    for row_start in range(0, len(cities_sorted), 2):
        cols = st.columns(2)
        for col, city in zip(cols, cities_sorted[row_start:row_start + 2]):
            city_data = mat_city[mat_city["Город"] == city]
            pivot = city_data.pivot_table(index="Материал", columns="Год",
                                          values="Сумма_без_НДС", fill_value=0)
            for year in (base_year, curr_year):
                if year not in pivot.columns:
                    pivot[year] = 0.0
            pivot["_total"] = pivot[base_year] + pivot[curr_year]
            top10 = pivot.sort_values("_total", ascending=False).head(10)
            # горизонтальный бар рисуется снизу вверх — сортируем по возрастанию,
            # чтобы крупнейшие группы были сверху
            top10 = top10.sort_values(curr_year)
            fig_mat = go.Figure()
            fig_mat.add_trace(go.Bar(y=top10.index, x=top10[base_year],
                                     orientation="h", name=str(base_year)))
            fig_mat.add_trace(go.Bar(y=top10.index, x=top10[curr_year],
                                     orientation="h", name=str(curr_year)))
            fig_mat.update_layout(
                title=city,
                barmode="group",
                xaxis_title="Сумма без НДС, руб",
                yaxis_title="",
                legend_title="Год",
                height=420,
                margin=dict(t=50, b=30),
            )
            with col:
                st.plotly_chart(fig_mat, width="stretch")

    # ---------- месячный план по филиалам ----------
    st.subheader(f"Месячный план по филиалам — {curr_year}")
    st.caption("План редактируется вручную, хранится в памяти сессии "
               "и не записывается на диск.")

    months_curr = sorted(int(m) for m in
                         rs.loc[rs["Год"] == curr_year, "Месяц"].dropna().unique())
    labels = [MONTH_NAMES[m - 1] for m in months_curr]

    stored = st.session_state.get("rs_plans")
    if (stored is None or list(stored.index) != cities
            or list(stored.columns) != labels):
        plan_df = pd.DataFrame(0.0, index=cities, columns=labels)
        plan_df.index.name = "Филиал"
    else:
        plan_df = stored

    edited = st.data_editor(
        plan_df,
        width="stretch",
        key="rs_plans_editor",
        column_config={
            lbl: st.column_config.NumberColumn(
                lbl, min_value=0, step=1_000_000, format="%d")
            for lbl in labels
        },
    )
    if st.button("💾 Сохранить план РС", type="primary", key="rs_plans_save"):
        st.session_state["rs_plans"] = edited
        st.success("План сохранён в рамках текущей сессии.")
        st.rerun()

    # ---------- выполнение плана ----------
    if float(edited.to_numpy(dtype=float, na_value=0.0).sum()) > 0:
        st.subheader("Выполнение плана по филиалам")
        plan_cols = [MONTH_NAMES[m - 1] for m in common]
        plan_ytd = edited[plan_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
        fact_ytd = (period[period["Год"] == curr_year]
                    .groupby("Город")["Сумма_без_НДС"].sum())
        exec_tbl = pd.DataFrame({"Факт": fact_ytd, "План": plan_ytd}).fillna(0)
        exec_tbl["Выполнение, %"] = exec_tbl.apply(
            lambda r: round(r["Факт"] / r["План"] * 100, 1) if r["План"] else None,
            axis=1)
        exec_tbl = exec_tbl.sort_values("Факт", ascending=False).reset_index()
        exec_tbl = exec_tbl.rename(columns={"index": "Филиал", "Город": "Филиал"})
        st.caption("Факт и план — за сопоставимые месяцы отчётного года.")
        st.dataframe(
            exec_tbl.style.format({
                "Факт": "{:,.0f}",
                "План": "{:,.0f}",
                "Выполнение, %": "{:.1f}%",
            }, thousands=" ", na_rep="—"),
            width="stretch", hide_index=True,
        )
