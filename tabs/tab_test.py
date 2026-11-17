"""Каталог примеров визуализаций на демонстрационных данных."""
from datetime import date
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import altair as alt
import pydeck as pdk

EXAMPLE_GROUPS = {
    "Сравнение и динамика": ["Линейный", "Площадной", "Столбчатый", "Столбчатый горизонтальный", "Столбчатый с накоплением", "Водопад", "Диаграмма Парето", "Свечной"],
    "Структура и доли": ["Круговой", "Кольцевая диаграмма", "Древовидная карта", "Солнечные лучи", "100% накопительная диаграмма", "Полярная столбчатая диаграмма"],
    "Распределение и взаимосвязи": ["Точечный", "Пузырьковый", "Гистограмма", "Ящик с усами", "Скрипка", "Тепловая карта", "Лепестковый", "Параллельные координаты"],
    "Этапы, потоки и показатели": ["Воронка", "Индикатор", "Схема потоков", "Диаграмма Ганта", "Диаграмма связей", "Mermaid", "Graphviz"],
    "Карты и 3D": ["Карта", "PyDeck", "3D-поверхность"],
    "Примеры библиотек": ["Altair", "Vega-Lite", "ECharts"],
}


def render():
    st.title("Тест")
    st.caption("Все примеры используют демонстрационные данные и не изменяют загруженные файлы.")
    gallery, tables, indicators, filters, badges, kpi_cards, details = st.tabs([
        "Каталог визуализаций", "Таблицы", "Показатели", "Фильтры",
        "Бейджи статуса", "Карточки KPI", "Раскрывающиеся блоки",
    ])
    with gallery:
        _render_gallery()
    with tables:
        _render_tables()
    with indicators:
        _render_indicators()
    with filters:
        _render_filters()
    with badges:
        _render_badges()
    with kpi_cards:
        _render_kpi_cards()
    with details:
        _render_details()


def _render_gallery():
    group = st.selectbox("Группа визуализаций", list(EXAMPLE_GROUPS), key="test_example_group")
    _render_example(EXAMPLE_GROUPS[group], f"test_example_{list(EXAMPLE_GROUPS).index(group)}")


def _sample_data():
    return pd.DataFrame({"Город": ["Тверь", "Ярославль", "Тула", "Калуга"],
                         "Группа": ["А", "Б", "А", "Б"],
                         "План": [120, 150, 100, 110], "Факт": [132, 138, 115, 105]})


def _render_badges():
    st.subheader("Статусы с пояснениями")
    columns = st.columns(4)
    columns[0].badge("Выполнено", color="green", icon=":material/check_circle:", help="План выполнен или превышен.")
    columns[1].badge("Внимание", color="orange", icon=":material/warning:", help="Показатель близок к плану, но ещё не достиг его.")
    columns[2].badge("Отставание", color="red", icon=":material/error:", help="Показатель ниже выбранного порога.")
    columns[3].badge("Нет данных", color="gray", icon=":material/help:", help="Недостаточно данных для оценки.")
    st.caption("Цвета и пороги показаны только как пример оформления.")


def _render_kpi_cards():
    st.subheader("Карточки с подсказками и динамикой")
    a, b, c = st.columns(3)
    a.metric("Продажи", "132 млн ₽", delta="+12 млн ₽", border=True, chart_data=[90, 100, 115, 120, 132], chart_type="line", help="Сумма продаж за выбранный период.")
    b.metric("Выполнение плана", "110%", delta="+10 п.п.", border=True, chart_data=[85, 92, 96, 104, 110], chart_type="bar", help="Факт, делённый на план, умноженный на 100%.")
    c.metric("Расходы", "85 млн ₽", delta="−15 млн ₽", delta_color="inverse", border=True, chart_data=[110, 105, 100, 92, 85], chart_type="area", help="Пример показателя, для которого снижение расходов окрашивается как улучшение.")


def _render_details():
    st.subheader("Подробности по запросу")
    st.caption("Основные сведения остаются видимыми; детали раскрываются по нажатию.")
    st.metric("Факт по всем городам", "490", help="Сумма условных значений в таблице ниже.")
    with st.expander("Показать расчёт"):
        st.write("Факт складывается из значений по четырём городам. План используется для сравнения.")
        st.dataframe(_sample_data(), hide_index=True, width="stretch", alt="Пример детализации по городам")
    with st.expander("Показать методику"):
        st.markdown("**Выполнение плана** = факт / план × 100%. При нулевом плане показатель не рассчитывается.")


def _render_tables():
    data = _sample_data().assign(**{"Выполнение, %": [110.0, 92.0, 115.0, 95.5],
                                    "Динамика": [[90, 100, 115, 132], [120, 125, 131, 138],
                                                 [75, 85, 95, 115], [80, 98, 100, 105]]})
    st.subheader("Интерактивная таблица")
    st.caption("Сортируйте столбцы и выбирайте строки.")
    selection = st.dataframe(data, hide_index=True, width="stretch", key="test_table_select",
                             on_select="rerun", selection_mode="multi-row",
                             column_config={"Город": st.column_config.TextColumn(pinned=True),
                                            "Выполнение, %": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=120),
                                            "Динамика": st.column_config.LineChartColumn()},
                             alt="Таблица с выбором строк, прогрессом и мини-графиками")
    st.caption(f"Выбрано строк: {len(selection.selection.rows)}")

    st.subheader("Таблица с цветовым выделением")
    comparison = _sample_data().assign(Отклонение=lambda df: df["Факт"] - df["План"])
    styled = comparison.style.map(lambda value: "color: #15803d" if value > 0 else ("color: #b91c1c" if value < 0 else ""), subset=["Отклонение"])
    st.dataframe(styled, hide_index=True, width="stretch", alt="Таблица с цветовым выделением отклонений")

    st.subheader("Сводная таблица")
    summary = _sample_data().groupby("Группа", as_index=False)[["План", "Факт"]].sum()
    st.dataframe(summary, hide_index=True, width="stretch", alt="Сводные значения по группам")

    st.subheader("Редактируемая таблица")
    st.caption("Измените значения в таблице; результат и скачиваемый CSV обновятся.")
    edited = st.data_editor(_sample_data(), hide_index=True, key="test_table_editor", width="stretch",
                            column_config={"План": st.column_config.NumberColumn(min_value=0, step=1),
                                           "Факт": st.column_config.NumberColumn(min_value=0, step=1)},
                            disabled=["Город", "Группа"], alt="Пример редактируемой таблицы")
    st.metric("Итого факт", f"{edited['Факт'].sum():,.0f}".replace(",", " "))
    st.download_button("Скачать таблицу CSV", edited.to_csv(index=False).encode("utf-8-sig"),
                       file_name="test_table.csv", mime="text/csv", key="test_table_download")


def _render_indicators():
    st.subheader("Показатели и сравнение")
    data = _sample_data()
    plan, fact = data["План"].sum(), data["Факт"].sum()
    a, b, c = st.columns(3)
    a.metric("План", f"{plan}")
    b.metric("Факт", f"{fact}", delta=f"{fact - plan:+d} к плану")
    c.metric("Выполнение", f"{fact / plan * 100:.1f}%")
    st.progress(min(fact / plan, 1.0), text=f"Выполнение плана: {fact / plan * 100:.1f}%")

    st.subheader("Цвет и направление изменения")
    a, b, c = st.columns(3)
    a.metric("Рост продаж", "132", delta="+12", border=True, help="Рост показателя выделен зелёным.")
    b.metric("Снижение расходов", "85", delta="−15", delta_color="inverse", border=True,
             help="Для расходов снижение может быть положительным результатом.")
    c.metric("Без оценки", "105", delta="+5", delta_color="off", border=True)

    st.subheader("Мини-графики в показателях")
    a, b, c = st.columns(3)
    a.metric("Линия", "132", delta="+12", chart_data=[90, 100, 115, 120, 132], chart_type="line", border=True)
    b.metric("Столбцы", "138", delta="+8", chart_data=[110, 120, 115, 130, 138], chart_type="bar", border=True)
    c.metric("Область", "115", delta="+5", chart_data=[70, 80, 95, 110, 115], chart_type="area", border=True)

    st.subheader("Сообщения о состоянии")
    st.success("План выполнен")
    st.warning("Показатель требует внимания")
    st.error("План не выполнен")
    st.info("Нет данных для сравнения")


def _render_filters():
    st.subheader("Фильтрация таблицы")
    data = _sample_data()
    groups = st.multiselect("Группа", sorted(data["Группа"].unique()), default=sorted(data["Группа"].unique()), key="test_filter_groups")
    minimum = st.slider("Минимальный факт", 0, 150, 0, key="test_filter_minimum")
    selected = data[data["Группа"].isin(groups) & data["Факт"].ge(minimum)]
    st.caption(f"Найдено строк: {len(selected)}")
    st.dataframe(selected, hide_index=True, width="stretch", alt="Отфильтрованные демонстрационные данные")

    st.subheader("Дополнительные способы выбора")
    query = st.text_input("Поиск города", key="test_filter_search", placeholder="Например, Тверь")
    city = st.selectbox("Один город", ["Все"] + data["Город"].tolist(), key="test_filter_city")
    fact_range = st.slider("Диапазон факта", 0, 150, (0, 150), key="test_filter_range")
    only_above = st.checkbox("Только выполнение плана", key="test_filter_above_plan")
    result = data[data["Город"].str.contains(query, case=False, regex=False)
                  & data["Факт"].between(*fact_range)]
    if city != "Все":
        result = result[result["Город"] == city]
    if only_above:
        result = result[result["Факт"] >= result["План"]]
    st.dataframe(result, hide_index=True, width="stretch", alt="Данные после дополнительных фильтров")

    st.subheader("Другие элементы выбора")
    st.radio("Режим сравнения", ["Месяц", "Квартал", "Год"], horizontal=True, key="test_filter_radio")
    st.select_slider("Период по кварталам", ["I", "II", "III", "IV"], value=("I", "IV"), key="test_filter_quarters")
    st.date_input("Интервал дат", value=(date(2026, 1, 1), date(2026, 10, 31)), key="test_filter_dates")
    st.toggle("Показывать план", value=True, key="test_filter_toggle")
    st.caption("Эти элементы показывают варианты ввода и не влияют на таблицы выше.")


def _render_example(choices, key):
    choice = st.selectbox("Выберите пример", choices, key=key)
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн"]
    frame = pd.DataFrame({"Месяц": months, "Продажи": [22, 30, 26, 38, 35, 47], "План": [25, 28, 32, 34, 39, 43]})
    categories = pd.DataFrame({"Категория": ["А", "Б", "В", "Г"], "Значение": [42, 28, 18, 12], "План": [35, 30, 22, 15]})
    if choice == "Линейный":
        st.line_chart(frame, x="Месяц", y=["Продажи", "План"], alt="Пример линейного графика")
    elif choice == "Площадной":
        st.area_chart(frame, x="Месяц", y=["Продажи", "План"], alt="Пример площадного графика")
    elif choice in ("Столбчатый", "Столбчатый горизонтальный", "Столбчатый с накоплением"):
        st.bar_chart(categories, x="Категория", y=["Значение", "План"], horizontal=choice == "Столбчатый горизонтальный", stack=choice == "Столбчатый с накоплением", alt=choice)
    elif choice == "Точечный":
        st.scatter_chart(categories, x="План", y="Значение", color="Категория", alt="Пример точечного графика")
    elif choice == "Карта":
        st.caption("Для подложки карты браузеру может потребоваться подключение к интернету.")
        st.map(pd.DataFrame({"lat": [55.75, 56.86, 57.63], "lon": [37.62, 35.92, 39.89]}), zoom=5, alt="Пример карты")
    elif choice == "Altair":
        chart = alt.Chart(categories).mark_bar().encode(x="Категория:N", y="Значение:Q", color="Категория:N", tooltip=["Категория", "Значение"])
        st.altair_chart(chart, width="stretch", alt="Пример Altair")
    elif choice == "Vega-Lite":
        st.vega_lite_chart(categories, {"mark": "bar", "encoding": {"x": {"field": "Категория", "type": "nominal"}, "y": {"field": "Значение", "type": "quantitative"}}}, width="stretch", alt="Пример Vega-Lite")
    elif choice == "ECharts":
        st.echarts_chart({"xAxis": {"type": "category", "data": months}, "yAxis": {"type": "value"}, "series": [{"type": "line", "data": frame["Продажи"].tolist()}]}, height=400, alt="Пример ECharts")
    elif choice == "PyDeck":
        st.caption("Для подложки карты браузеру может потребоваться подключение к интернету.")
        points = pd.DataFrame({"lat": [55.75, 56.86, 57.63], "lon": [37.62, 35.92, 39.89]})
        deck = pdk.Deck(layers=[pdk.Layer("ScatterplotLayer", points, get_position="[lon, lat]", get_radius=12000, get_fill_color=[79, 70, 229, 180])], initial_view_state=pdk.ViewState(latitude=56.5, longitude=37.5, zoom=5))
        st.pydeck_chart(deck, alt="Пример карты PyDeck")
    elif choice == "Mermaid":
        st.mermaid_chart("graph LR\n  A[Запрос] --> B[Предложение]\n  B --> C[Заказ]", alt="Пример схемы Mermaid")
    elif choice == "Graphviz":
        st.graphviz_chart('digraph { "Запрос" -> "Предложение" -> "Заказ" }', width="stretch", alt="Пример схемы Graphviz")
    else:
        if choice == "Пузырьковый":
            fig = px.scatter(categories, x="План", y="Значение", size="Значение", color="Категория", hover_name="Категория")
        elif choice in ("Круговой", "Кольцевая диаграмма"):
            fig = px.pie(categories, names="Категория", values="Значение", hole=0.5 if choice == "Кольцевая диаграмма" else 0)
        elif choice in ("Гистограмма", "Ящик с усами", "Скрипка"):
            values = pd.DataFrame({"Группа": ["А"] * 6 + ["Б"] * 6, "Значение": [12, 17, 18, 20, 22, 30, 16, 21, 23, 24, 29, 35]})
            fig = {"Гистограмма": px.histogram, "Ящик с усами": px.box, "Скрипка": px.violin}[choice](values, x="Группа", y="Значение", color="Группа")
        elif choice == "Тепловая карта":
            fig = px.imshow([[4, 8, 5], [7, 3, 9], [2, 6, 8]], x=["Янв", "Фев", "Мар"], y=["А", "Б", "В"], text_auto=True)
        elif choice in ("Древовидная карта", "Солнечные лучи"):
            hierarchy = pd.DataFrame({"Направление": ["Север", "Север", "Юг", "Юг"], "Категория": ["А", "Б", "А", "В"], "Значение": [30, 20, 25, 15]})
            fig = (px.treemap if choice == "Древовидная карта" else px.sunburst)(hierarchy, path=["Направление", "Категория"], values="Значение")
        elif choice == "Воронка":
            fig = px.funnel(y=["Запросы", "Предложения", "Переговоры", "Заказы"], x=[100, 75, 45, 25])
        elif choice == "Водопад":
            fig = go.Figure(go.Waterfall(x=["Начало", "Рост", "Снижение", "Итого"], y=[100, 35, -20, 0], measure=["absolute", "relative", "relative", "total"]))
        elif choice == "Лепестковый":
            fig = go.Figure(go.Scatterpolar(r=[4, 3, 5, 4, 4], theta=["Цена", "Срок", "Качество", "Сервис", "Цена"], fill="toself"))
        elif choice == "Индикатор":
            fig = go.Figure(go.Indicator(mode="gauge+number", value=78, gauge={"axis": {"range": [0, 100]}}, title={"text": "Выполнение, %"}))
        elif choice == "Свечной":
            fig = go.Figure(go.Candlestick(x=months, open=[10, 12, 11, 15, 14, 17], high=[14, 15, 16, 18, 19, 20], low=[9, 10, 10, 13, 13, 15], close=[12, 11, 15, 14, 17, 19]))
        elif choice == "3D-поверхность":
            grid = np.linspace(-2, 2, 30)
            x, y = np.meshgrid(grid, grid)
            fig = go.Figure(go.Surface(x=x, y=y, z=np.sin(x) * np.cos(y)))
        elif choice == "Диаграмма Ганта":
            tasks = pd.DataFrame({"Этап": ["Запрос", "Предложение", "Согласование"], "Начало": ["2026-01-01", "2026-01-10", "2026-02-01"], "Окончание": ["2026-01-10", "2026-02-01", "2026-02-20"]})
            fig = px.timeline(tasks, x_start="Начало", x_end="Окончание", y="Этап", color="Этап")
            fig.update_yaxes(autorange="reversed")
        elif choice == "Диаграмма Парето":
            fig = go.Figure()
            fig.add_bar(x=categories["Категория"], y=categories["Значение"], name="Значение")
            fig.add_scatter(x=categories["Категория"], y=categories["Значение"].cumsum() / categories["Значение"].sum() * 100, name="Накопленная доля, %", yaxis="y2", mode="lines+markers")
            fig.update_layout(yaxis2=dict(title="Накопленная доля, %", overlaying="y", side="right", range=[0, 100]))
        elif choice == "Диаграмма связей":
            fig = go.Figure()
            fig.add_scatter(x=[0, 1, None, 0, 1, None, 1, 2], y=[0, 1, None, 0, -1, None, 1, 0], mode="lines", line=dict(color="#94A3B8"), hoverinfo="skip", showlegend=False)
            fig.add_scatter(x=[0, 1, 1, 2], y=[0, 1, -1, 0], mode="markers+text", text=["Запрос", "Предложение", "Партнёр", "Заказ"], textposition="top center", marker=dict(size=24, color="#4F46E5"), showlegend=False)
            fig.update_xaxes(visible=False)
            fig.update_yaxes(visible=False)
        elif choice == "100% накопительная диаграмма":
            fig = go.Figure()
            for name, values in (("Продажи", [70, 50, 30]), ("План", [30, 50, 70])):
                fig.add_bar(x=["Янв", "Фев", "Мар"], y=values, name=name)
            fig.update_layout(barmode="stack", yaxis_title="Доля, %")
        elif choice == "Параллельные координаты":
            fig = px.parallel_coordinates(categories, dimensions=["Значение", "План"], color="Значение")
        elif choice == "Полярная столбчатая диаграмма":
            fig = px.bar_polar(categories, r="Значение", theta="Категория", color="Категория")
        else:
            fig = go.Figure(go.Sankey(node={"label": ["Запросы", "Предложения", "Заказы", "В работе"]}, link={"source": [0, 1, 1], "target": [1, 2, 3], "value": [75, 25, 50]}))
        fig.update_layout(height=500, margin=dict(l=20, r=20, t=35, b=20))
        st.plotly_chart(fig, width="stretch", key=f"{key}_plotly", alt=f"Пример: {choice}")
