from pathlib import Path

import pandas as pd
import streamlit as st

from data_loader import load_sales
from plans import load_plans, PLANS_PATH
from tabs import tab_dynamics, tab_project, tab_rs, tab_etm, tab_partners

st.set_page_config(page_title="Продажи ЦО", layout="wide")

SALES_PATH = Path("data/sales.xlsx")
ETM_PATH = Path("data/etm.xlsx")
ETM_SHEETS = {
    "Товарные категории": ("%ВП ГО DKC по ТГ", "Товарная категория"),
    "Специализации": ("%ВП ГО DKC по спец", "Специализация"),
}

# флаги «пользователь явно загрузил файл в этой сессии»
if "sales_loaded" not in st.session_state:
    st.session_state["sales_loaded"] = False
if "etm_loaded" not in st.session_state:
    st.session_state["etm_loaded"] = False


def _multiselect(label, options, key, default=None):
    """Мультивыбор с очисткой устаревших значений при изменении родительских фильтров."""
    options = list(options)
    if key in st.session_state:
        current = st.session_state[key]
        if not isinstance(current, list):
            current = []
        st.session_state[key] = [value for value in current if value in options]
        return st.multiselect(label, options, key=key)
    return st.multiselect(label, options, default=default, key=key)


# =====================================================================
# ЕДИНАЯ БОКОВАЯ ПАНЕЛЬ: загрузка источников и все фильтры приложения
# =====================================================================
with st.sidebar:
    st.title("Параметры отчёта")

    with st.expander("📂 Загрузка данных", expanded=True):
        st.caption("Основная выгрузка продаж")
        sales_upload = st.file_uploader(
            "Файл продаж (.xlsx)", type=["xlsx"], key="sales_file_uploader"
        )
        if sales_upload is not None:
            payload = sales_upload.getvalue()
            SALES_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not SALES_PATH.exists() or SALES_PATH.read_bytes() != payload:
                SALES_PATH.write_bytes(payload)
                for state_key in ["sales_city", "sales_dist", "sales_material",
                                  "sales_base_year", "sales_curr_year"]:
                    st.session_state.pop(state_key, None)
                st.cache_data.clear()
            st.session_state["sales_loaded"] = True
            st.success(f"Файл продаж: {sales_upload.name}")

        if st.session_state["sales_loaded"] and st.button(
            "🗑 Очистить загруженный файл продаж", key="clear_sales"
        ):
            st.session_state["sales_loaded"] = False
            for state_key in ["sales_city", "sales_dist", "sales_material",
                              "sales_base_year", "sales_curr_year"]:
                st.session_state.pop(state_key, None)
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.caption("План продаж (CSV)")
        plan_upload = st.file_uploader(
            "Файл плана (.csv)", type=["csv"], key="plan_file_uploader"
        )
        if plan_upload is not None:
            payload = plan_upload.getvalue()
            PLANS_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not PLANS_PATH.exists() or PLANS_PATH.read_bytes() != payload:
                PLANS_PATH.write_bytes(payload)
            st.success(f"Файл плана: {plan_upload.name}")

        st.divider()
        st.caption("Выгрузка ЭТМ")
        etm_upload = st.file_uploader(
            "Файл ЭТМ (.xlsx)", type=["xlsx"], key="etm_file_uploader"
        )
        if etm_upload is not None:
            payload = etm_upload.getvalue()
            ETM_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not ETM_PATH.exists() or ETM_PATH.read_bytes() != payload:
                ETM_PATH.write_bytes(payload)
                for state_key in list(st.session_state.keys()):
                    if state_key.startswith("etm_sidebar_"):
                        st.session_state.pop(state_key, None)
                st.cache_data.clear()
            st.session_state["etm_loaded"] = True
            st.success(f"Файл ЭТМ: {etm_upload.name}")

        if st.session_state["etm_loaded"] and st.button(
            "🗑 Очистить загруженный файл ЭТМ", key="clear_etm"
        ):
            st.session_state["etm_loaded"] = False
            for state_key in list(st.session_state.keys()):
                if state_key.startswith("etm_sidebar_"):
                    st.session_state.pop(state_key, None)
            st.cache_data.clear()
            st.rerun()

    # ------------------------- ПРОДАЖИ -------------------------------
    sales = None
    base = pd.DataFrame()
    plans = load_plans()
    years = []
    city, dist, material = [], [], []
    base_year = curr_year = None
    sales_error = None

    # защита от рассинхрона: флаг есть, а файла нет
    if st.session_state["sales_loaded"] and not SALES_PATH.exists():
        st.session_state["sales_loaded"] = False

    if st.session_state["sales_loaded"]:
        @st.cache_data(show_spinner="Читаю файл продаж…")
        def _load_sales(path_str: str, mtime: float):
            return load_sales(path_str)

        try:
            sales = _load_sales(str(SALES_PATH), SALES_PATH.stat().st_mtime)
            years = sorted(int(y) for y in sales["Год"].dropna().unique())

            with st.expander("🔎 Фильтры продаж", expanded=True):
                cities = sorted(sales["Город"].dropna().unique())
                city = _multiselect("Город", cities, "sales_city", cities)

                dists = sorted(sales["Дистрибьютор"].dropna().unique())
                dist = _multiselect("Дистрибьютор", dists, "sales_dist", dists)

                mats = (sales[["Код_материала", "Материал"]]
                        .drop_duplicates()
                        .sort_values("Код_материала")["Материал"]
                        .tolist())
                material = _multiselect("Материал", mats, "sales_material", mats)

                st.subheader("Сравнение годов (YoY)")
                if years:
                    default_base = max(0, len(years) - 2)
                    default_curr = max(0, len(years) - 1)
                    base_year = st.selectbox(
                        "Базовый год (прошлый)", years,
                        index=default_base, key="sales_base_year"
                    )
                    curr_year = st.selectbox(
                        "Отчётный год (текущий)", years,
                        index=default_curr, key="sales_curr_year"
                    )
                    if base_year == curr_year:
                        st.warning("Базовый и отчётный годы совпадают — YoY будет 0/∞.")

            base = sales[
                sales["Город"].isin(city)
                & sales["Дистрибьютор"].isin(dist)
                & sales["Материал"].isin(material)
            ].copy()
        except Exception as exc:
            sales_error = str(exc)
            st.error(f"Ошибка чтения файла продаж: {exc}")
    else:
        st.info("Загрузите файл продаж в разделе «Загрузка данных», чтобы открыть вкладки продаж.")

    # --------------------------- ЭТМ ---------------------------------
    etm_context = None
    etm_error = None

    # защита от рассинхрона: флаг есть, а файла нет
    if st.session_state["etm_loaded"] and not ETM_PATH.exists():
        st.session_state["etm_loaded"] = False

    with st.expander("🟧 Фильтры ЭТМ", expanded=True):
        etm_kind = st.radio(
            "Разрез аналитики",
            list(ETM_SHEETS),
            horizontal=False,
            key="etm_kind_sidebar",
        )
        if st.session_state["etm_loaded"]:
            sheet_name, dimension = ETM_SHEETS[etm_kind]
            try:
                file_bytes = ETM_PATH.read_bytes()
                etm_df, etm_fact_months = tab_etm._read_etm(file_bytes, sheet_name)

                filter_fields = [
                    "Макрорегион ДКС", "География", "Тип подразделения",
                    "ОП", "РК", "ПОК",
                ]
                selected_filters = {}
                filter_keys = {
                    "Макрорегион ДКС": "etm_sidebar_macro",
                    "География": "etm_sidebar_geo",
                    "Тип подразделения": "etm_sidebar_unit_type",
                    "ОП": "etm_sidebar_op",
                    "РК": "etm_sidebar_rk",
                    "ПОК": "etm_sidebar_pok",
                }

                for field in filter_fields:
                    # Каждый следующий фильтр показывает только значения,
                    # доступные после применения предыдущих фильтров.
                    options_df = etm_df.copy()
                    for previous_field in filter_fields[:filter_fields.index(field)]:
                        chosen = selected_filters.get(previous_field, [])
                        options_df = options_df[
                            options_df[previous_field].astype(str).isin(chosen)
                        ]
                    options = sorted(options_df[field].dropna().astype(str).unique())
                    if field == "Макрорегион ДКС":
                        default = ["Центр (ЦО)"] if "Центр (ЦО)" in options else options
                    else:
                        default = options
                    selected_filters[field] = _multiselect(
                        field, options, filter_keys[field], default
                    )

                filtered_etm = etm_df.copy()
                for field in filter_fields:
                    chosen = selected_filters[field]
                    if chosen:
                        filtered_etm = filtered_etm[
                            filtered_etm[field].astype(str).isin(chosen)
                        ]
                    else:
                        filtered_etm = filtered_etm.iloc[0:0]

                dimension_options = sorted(
                    filtered_etm[dimension].dropna().astype(str).unique()
                )
                selected_dimensions = _multiselect(
                    dimension,
                    dimension_options,
                    f"etm_sidebar_dimension_{etm_kind}",
                    dimension_options,
                )
                if selected_dimensions:
                    filtered_etm = filtered_etm[
                        filtered_etm[dimension].astype(str).isin(selected_dimensions)
                    ]
                else:
                    filtered_etm = filtered_etm.iloc[0:0]

                available_months = etm_fact_months
                period_end = st.selectbox(
                    "Период по",
                    available_months,
                    index=len(available_months) - 1,
                    format_func=lambda month: f"{tab_etm.MONTHS[month - 1]} {tab_etm.CURR_YEAR}",
                    key="etm_sidebar_period_end",
                )
                if st.button("↩️ Сбросить фильтры ЭТМ", key="etm_sidebar_reset"):
                    for state_key in list(st.session_state.keys()):
                        if state_key.startswith("etm_sidebar_") and state_key != "etm_sidebar_kind":
                            del st.session_state[state_key]
                    st.rerun()

                etm_context = {
                    "df": etm_df,
                    "filtered": filtered_etm,
                    "kind": etm_kind,
                    "dimension": dimension,
                    "selected_filters": selected_filters,
                    "selected_dimensions": selected_dimensions,
                    "period_end": period_end,
                    "fact_months": etm_fact_months,
                }
            except Exception as exc:
                etm_error = str(exc)
                st.error(f"Не удалось прочитать выгрузку ЭТМ: {exc}")
        else:
            st.info("Загрузите файл ЭТМ в разделе «Загрузка данных», чтобы открыть аналитику ЭТМ.")

# =====================================================================
# ОБЩИЙ КОНТЕКСТ ДЛЯ ВКЛАДОК
# =====================================================================
ctx = {
    "sales": sales if sales is not None else pd.DataFrame(),
    "base": base,
    "plans": plans,
    "city": city,
    "dist": dist,
    "material": material,
    "base_year": base_year,
    "curr_year": curr_year,
    "years": years,
    "sales_error": sales_error,
    "etm": etm_context,
    "etm_error": etm_error,
}

# =====================================================================
# ВКЛАДКИ — только визуализация и аналитика
# =====================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Динамика",
    "🤝 Проектное взаимодействие",
    "🟦 Русский Свет",
    "🟧 ЭТМ",
    "👥 Партнеры",
])

with tab1:
    if sales is None:
        st.info("Для отображения динамики загрузите файл продаж в боковой панели.")
    elif base.empty:
        st.warning("По выбранным фильтрам продаж нет данных.")
    else:
        tab_dynamics.render(ctx)

with tab2:
    if sales is None:
        st.info("Для работы раздела загрузите файл продаж в боковой панели.")
    else:
        tab_project.render(ctx)

with tab3:
    if sales is None:
        st.info("Для работы раздела загрузите файл продаж в боковой панели.")
    else:
        tab_rs.render(ctx)

with tab4:
    tab_etm.render(ctx)

with tab5:
    if sales is None:
        st.info("Для работы раздела загрузите файл продаж в боковой панели.")
    else:
        tab_partners.render(ctx)