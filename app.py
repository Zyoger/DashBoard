from io import BytesIO

import pandas as pd
import streamlit as st

from data_loader import load_sales
from plans import load_plans, parse_plans
from tabs import tab_dynamics, tab_project, tab_rs, tab_etm, tab_partners

st.set_page_config(page_title="Продажи ЦО", layout="wide")

ETM_SHEETS = {
    "Товарные категории": ("%ВП ГО DKC по ТГ", "Товарная категория"),
    "Специализации": ("%ВП ГО DKC по спец", "Специализация"),
}

SALES_FILTER_KEYS = ["sales_city", "sales_dist", "sales_material",
                     "sales_base_year", "sales_curr_year"]


def _reset_etm_filters():
    for state_key in list(st.session_state.keys()):
        if state_key.startswith("etm_sidebar_"):
            st.session_state.pop(state_key, None)


# Загруженные пользователем файлы живут только в памяти сессии —
# на диск ничего не записывается.
if "sales_bytes" not in st.session_state:
    st.session_state["sales_bytes"] = None
if "plan_bytes" not in st.session_state:
    st.session_state["plan_bytes"] = None
if "etm_bytes" not in st.session_state:
    st.session_state["etm_bytes"] = None
if "project_bytes" not in st.session_state:
    st.session_state["project_bytes"] = None
if "plans_df" not in st.session_state:
    # стартовый план из data/plans.csv, если файл есть в репозитории
    st.session_state["plans_df"] = load_plans()


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


def _project_multiselect(label, series, key):
    options = sorted(series.dropna().astype(str).unique().tolist())
    return _multiselect(label, options, key, default=options)


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
            if payload != st.session_state["sales_bytes"]:
                st.session_state["sales_bytes"] = payload
                for state_key in SALES_FILTER_KEYS:
                    st.session_state.pop(state_key, None)
                st.cache_data.clear()
            st.success(f"Файл продаж: {sales_upload.name}")

        if st.session_state["sales_bytes"] is not None and st.button(
            "🗑 Очистить загруженный файл продаж", key="clear_sales"
        ):
            st.session_state["sales_bytes"] = None
            for state_key in SALES_FILTER_KEYS:
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
            if payload != st.session_state["plan_bytes"]:
                st.session_state["plan_bytes"] = payload
                try:
                    st.session_state["plans_df"] = parse_plans(BytesIO(payload))
                    st.success(f"Файл плана: {plan_upload.name}")
                except Exception as exc:
                    st.error(f"Не удалось прочитать файл плана: {exc}")

        st.divider()
        st.caption("Выгрузка ЭТМ")
        etm_upload = st.file_uploader(
            "Файл ЭТМ (.xlsx)", type=["xlsx"], key="etm_file_uploader"
        )
        if etm_upload is not None:
            payload = etm_upload.getvalue()
            if payload != st.session_state["etm_bytes"]:
                st.session_state["etm_bytes"] = payload
                _reset_etm_filters()
                st.cache_data.clear()
            st.success(f"Файл ЭТМ: {etm_upload.name}")

        if st.session_state["etm_bytes"] is not None and st.button(
            "🗑 Очистить загруженный файл ЭТМ", key="clear_etm"
        ):
            st.session_state["etm_bytes"] = None
            _reset_etm_filters()
            st.cache_data.clear()
            st.rerun()

        st.divider()
        st.caption("Проектное взаимодействие")
        project_upload = st.file_uploader(
            "Файл проектного взаимодействия (.xlsx)", type=["xlsx"], key="project_file_uploader"
        )
        if project_upload is not None:
            payload = project_upload.getvalue()
            if payload != st.session_state["project_bytes"]:
                st.session_state["project_bytes"] = payload
                for state_key in list(st.session_state.keys()):
                    if state_key.startswith("project_") and state_key != "project_bytes":
                        st.session_state.pop(state_key, None)
                st.cache_data.clear()
            st.success(f"Файл проектов: {project_upload.name}")

        if st.session_state["project_bytes"] is not None and st.button(
            "🗑 Очистить файл проектного взаимодействия", key="clear_project"
        ):
            st.session_state["project_bytes"] = None
            for state_key in list(st.session_state.keys()):
                if state_key.startswith("project_") and state_key != "project_bytes":
                    st.session_state.pop(state_key, None)
            st.cache_data.clear()
            st.rerun()

        st.caption("Файлы обрабатываются в памяти и нигде не сохраняются.")

    # ------------------------- ПРОДАЖИ -------------------------------
    sales = None
    base = pd.DataFrame()
    plans = st.session_state["plans_df"]
    years = []
    city, dist, material = [], [], []
    base_year = curr_year = None
    sales_error = None

    if st.session_state["sales_bytes"] is not None:
        @st.cache_data(show_spinner="Читаю файл продаж…")
        def _load_sales(payload: bytes):
            return load_sales(BytesIO(payload))

        try:
            sales = _load_sales(st.session_state["sales_bytes"])
            years = sorted(int(y) for y in sales["Год"].dropna().unique())

            with st.expander("🔎 Фильтры продаж", expanded=False):
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

    # Фильтры ЭТМ показываем только после загрузки файла.
    if st.session_state["etm_bytes"] is not None:
        with st.expander("🟧 Фильтры ЭТМ", expanded=False):
            etm_kind = st.radio(
                "Разрез аналитики",
                list(ETM_SHEETS),
                horizontal=False,
                key="etm_kind_sidebar",
            )
            sheet_name, dimension = ETM_SHEETS[etm_kind]
            try:
                etm_df, etm_fact_months = tab_etm._read_etm(
                    st.session_state["etm_bytes"], sheet_name
                )

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
                if available_months:
                    period_end = st.selectbox(
                        "Период по",
                        available_months,
                        index=len(available_months) - 1,
                        format_func=lambda month: f"{tab_etm.MONTHS[month - 1]} {tab_etm.CURR_YEAR}",
                        key="etm_sidebar_period_end",
                    )
                else:
                    period_end = None
                    st.warning("В загруженной выгрузке ЭТМ не найдены месяцы с фактическими данными.")

                if st.button("↩️ Сбросить фильтры ЭТМ", key="etm_sidebar_reset"):
                    _reset_etm_filters()
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

    # ---------------------- ПРОЕКТНОЕ ВЗАИМОДЕЙСТВИЕ ----------------------
    project_df = None
    project_filtered_df = None
    project_error = None
    project_filters = {}
    if st.session_state["project_bytes"] is not None:
        try:
            project_df = tab_project.parse_project_file(st.session_state["project_bytes"])
            with st.expander("🤝 Фильтры проектного взаимодействия", expanded=False):
                project_distributors = _project_multiselect(
                    "Дистрибьютор / филиал", project_df["Дистрибьютор"], "project_sidebar_dist"
                )
                city_source = project_df[
                    project_df["Дистрибьютор"].astype(str).isin(project_distributors)
                ] if project_distributors else project_df.iloc[0:0]
                project_cities = _project_multiselect(
                    "Город", city_source["Город"], "project_sidebar_city"
                )
                project_industries = _project_multiselect(
                    "Подотрасль", project_df["Подотрасль"], "project_sidebar_industry"
                )
                project_stages = _project_multiselect(
                    "Стадия", project_df["Стадия"], "project_sidebar_stage"
                )
                project_managers = _project_multiselect(
                    "Ответственный", project_df["Ответственный"], "project_sidebar_manager"
                )
                project_clients = _project_multiselect(
                    "Конечный клиент", project_df["Конечный клиент"], "project_sidebar_client"
                )
                valid_project_dates = project_df["Дата создания"].dropna()
                if not valid_project_dates.empty:
                    project_date_min = valid_project_dates.min().date()
                    project_date_max = valid_project_dates.max().date()
                    project_date_range = st.date_input(
                        "Период создания записей",
                        value=(project_date_min, project_date_max),
                        min_value=project_date_min,
                        max_value=project_date_max,
                        key="project_sidebar_date_range",
                    )
                else:
                    project_date_range = ()
                if st.button("↩️ Сбросить фильтры проектов", key="project_sidebar_reset"):
                    for state_key in list(st.session_state.keys()):
                        if state_key.startswith("project_sidebar_"):
                            st.session_state.pop(state_key, None)
                    st.rerun()

            project_filtered_df = project_df[
                project_df["Дистрибьютор"].astype(str).isin(project_distributors)
                & project_df["Город"].astype(str).isin(project_cities)
                & project_df["Подотрасль"].astype(str).isin(project_industries)
                & project_df["Стадия"].astype(str).isin(project_stages)
                & project_df["Ответственный"].astype(str).isin(project_managers)
                & project_df["Конечный клиент"].astype(str).isin(project_clients)
            ].copy()
            if isinstance(project_date_range, (tuple, list)) and len(project_date_range) == 2:
                project_start, project_end = project_date_range
                project_filtered_df = project_filtered_df[
                    project_filtered_df["Дата создания"].dt.date.between(project_start, project_end)
                ]
            project_filters = {
                "distributors": project_distributors,
                "cities": project_cities,
                "industries": project_industries,
                "stages": project_stages,
                "managers": project_managers,
                "clients": project_clients,
                "date_range": project_date_range,
            }
        except Exception as exc:
            project_error = str(exc)
            st.error(f"Не удалось прочитать файл проектного взаимодействия: {exc}")
    else:
        project_df = None
        project_filtered_df = None
        project_error = None

# =====================================================================
# СТАРТОВЫЙ ЭКРАН — пока не загружен ни один источник данных
# =====================================================================
if (st.session_state["sales_bytes"] is None
        and st.session_state["etm_bytes"] is None
        and st.session_state["project_bytes"] is None):
    st.title("📊 Продажи ЦО")
    st.markdown(
        """
        Дашборд аналитики продаж Центрального округа.

        **Что внутри:**
        - **📈 Динамика** — KPI, YoY, план/факт и сводная таблица «дистрибьютор → город»;
        - **🤝 Проектное взаимодействие** — проекты, стадии, стоимость предложений,
          заказы, аналитика по дистрибьюторам и детализация;
        - **🟧 ЭТМ** — выполнение плана и динамика по офисам продаж;
        - **🟦 Русский Свет** и **👥 Партнеры** — остальные разделы приложения.

        **Как начать:**
        1. Откройте слева раздел **«📂 Загрузка данных»**;
        2. Загрузите нужный источник: продажи, ЭТМ или проектное взаимодействие;
        3. Для вкладки проектов файл продаж не требуется;
        4. При необходимости настройте фильтры в боковой панели.

        Файлы обрабатываются только в памяти сессии и нигде не сохраняются.
        """
    )
    st.stop()

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
    "project_df": project_df,
    "project_filtered_df": project_filtered_df,
    "project_filters": project_filters,
    "project_error": project_error,
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
