from pathlib import Path

import streamlit as st

from data_loader import load_sales
from plans import load_plans

from tabs import tab_dynamics, tab_project, tab_rs, tab_etm, tab_partners

st.set_page_config(page_title="Продажи ЦО", layout="wide")

DATA_PATH = Path("data/sales.xlsx")


# ============================================================
# САЙДБАР — общий для всех вкладок
# ============================================================
with st.sidebar:
    st.header("Данные")
    up = st.file_uploader("Загрузить новую выгрузку (.xlsx)", type=["xlsx"])
    if up is not None:
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_bytes(up.getvalue())
        st.success(f"Файл загружен: {up.name}")
        st.cache_data.clear()

    if not DATA_PATH.exists():
        st.warning("Положите выгрузку в data/sales.xlsx или загрузите через кнопку выше")
        st.stop()

    @st.cache_data(show_spinner="Читаю файл…")
    def _load(path_str: str, mtime: float):
        return load_sales(path_str)

    try:
        sales = _load(str(DATA_PATH), DATA_PATH.stat().st_mtime)
    except Exception as e:
        st.error(f"Ошибка чтения файла: {e}")
        st.stop()

    years = sorted(int(y) for y in sales["Год"].dropna().unique())

    st.header("Фильтры")
    cities = sorted(sales["Город"].dropna().unique())
    city = st.multiselect("Город", cities, default=cities)

    dists = sorted(sales["Дистрибьютор"].dropna().unique())
    dist = st.multiselect("Дистрибьютор", dists, default=dists)

    mats = (sales[["Код_материала", "Материал"]]
            .drop_duplicates()
            .sort_values("Код_материала")["Материал"]
            .tolist())
    material = st.multiselect("Материал", mats, default=mats)

    st.subheader("Сравнение годов (YoY)")
    base_year = st.selectbox("Базовый год (прошлый)", years,
                             index=max(0, len(years) - 2))
    curr_year = st.selectbox("Отчётный год (текущий)", years,
                             index=max(0, len(years) - 1))
    if base_year == curr_year:
        st.warning("Базовый и отчётный годы совпадают — YoY будет 0/∞.")

# ============================================================
# ПОДГОТОВКА ДАННЫХ (общая для всех вкладок)
# ============================================================
base = sales[
    sales["Город"].isin(city)
    & sales["Дистрибьютор"].isin(dist)
    & sales["Материал"].isin(material)
].copy()

plans = load_plans()

ctx = {
    "sales": sales,
    "base": base,
    "plans": plans,
    "city": city,
    "dist": dist,
    "material": material,
    "base_year": base_year,
    "curr_year": curr_year,
    "years": years,
}

# ============================================================
# ВКЛАДКИ
# ============================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Динамика",
    "🤝 Проектное взаимодействие",
    "🟦 Русский Свет",
    "🟧 ЭТМ",
    "👥 Партнеры",
])

with tab1:
    tab_dynamics.render(ctx)

with tab2:
    tab_project.render(ctx)

with tab3:
    tab_rs.render(ctx)

with tab4:
    tab_etm.render(ctx)

with tab5:
    tab_partners.render(ctx)