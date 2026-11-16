from pathlib import Path
from unittest import TestCase

from streamlit.testing.v1 import AppTest


DATA = '''
import pandas as pd
import streamlit as st
from tabs import tab_rs as rs
rows=[]
for dist,city in [('Русский Свет','Тверь'),('Русский Свет','Москва'),('Другой','Казань')]:
    for year in [2025,2026]:
        for month in [3,4]:
            for mat in ['А','Б']:
                rows.append({'Дистрибьютор':dist,'Город':city,'Год':year,'Месяц':month,
                             'Материал':mat,'Код_материала':mat,'Квартал':(month-1)//3+1,
                             'Дата':pd.Timestamp(year=year,month=month,day=1),'Сумма_без_НДС':100})
sales=pd.DataFrame(rows)
'''

SOURCE = DATA + '''
with st.sidebar:
    filters=rs.sidebar_filters(sales)
prepared=rs._prepare(dict({'sales':sales},**filters))
if prepared is not None:
    st.session_state['monthly']=prepared[4]
    st.session_state['offices']=prepared[2]
rs.render(dict({'sales':sales},**filters))
'''


class RussianLightFilterTests(TestCase):
    def healthy(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertFalse(app.error, [e.value for e in app.error])

    def test_geography_matches_etm_and_cascades(self):
        app = AppTest.from_string(SOURCE, default_timeout=30).run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_geography').value, ['Север','Юг'])
        app.multiselect(key='rs_sidebar_geography').set_value(['Север']).run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_cities').value, ['Тверь'])
        self.assertEqual(app.session_state['offices'].index.tolist(), ['Тверь'])
        self.assertEqual(app.session_state['monthly']['Факт отчётного года'].sum(), 400)
        app.multiselect(key='rs_sidebar_geography').set_value(['Север','Юг']).run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_cities').value, ['Москва','Тверь'])
        self.assertEqual(app.session_state['monthly']['Факт отчётного года'].sum(), 800)
        app.multiselect(key='rs_sidebar_geography').set_value(['Юг']).run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_cities').value, ['Москва'])
        self.assertEqual(app.session_state['offices'].index.tolist(), ['Москва'])
        app.multiselect(key='rs_sidebar_geography').set_value([]).run()
        self.healthy(app)
        self.assertEqual(len(app.get('plotly_chart')), 0)
        app.button(key='rs_sidebar_reset').click().run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_geography').value, ['Север','Юг'])
        self.assertEqual(app.multiselect(key='rs_sidebar_cities').value, ['Москва','Тверь'])

    def test_default_options_and_independent_months(self):
        app = AppTest.from_string(SOURCE, default_timeout=30).run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_cities').value, ['Москва','Тверь'])
        self.assertEqual(app.multiselect(key='rs_sidebar_materials').value, ['А','Б'])
        app.multiselect(key='rs_sidebar_cities').set_value(['Тверь']).run()
        app.multiselect(key='rs_sidebar_materials').set_value(['А']).run()
        app.selectbox(key='rs_sidebar_start').set_value(4).run()
        self.healthy(app)
        monthly = app.session_state['monthly']
        self.assertEqual(monthly.index.tolist(), ['Апр'])
        self.assertEqual(monthly["Факт отчётного года"].sum(), 100)
        self.assertEqual(app.session_state['offices'].index.tolist(), ['Тверь'])
        app.button(key='rs_sidebar_reset').click().run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_cities').value, ['Москва','Тверь'])
        self.assertEqual(app.selectbox(key='rs_sidebar_start').value, 3)

    def test_geography_change_refreshes_previously_narrowed_cities(self):
        source = SOURCE.replace("('Другой','Казань')", "('Русский Свет','Владимир'),('Другой','Казань')")
        app = AppTest.from_string(source, default_timeout=30).run()
        app.multiselect(key='rs_sidebar_cities').set_value(['Тверь','Москва']).run()
        app.multiselect(key='rs_sidebar_geography').set_value(['Север']).run()
        app.multiselect(key='rs_sidebar_geography').set_value(['Север','Юг']).run()
        self.healthy(app)
        self.assertEqual(app.multiselect(key='rs_sidebar_cities').value, ['Владимир','Москва','Тверь'])
        self.assertEqual(app.session_state['monthly']['Факт отчётного года'].sum(), 1200)

    def test_empty_selection_and_period_order(self):
        app = AppTest.from_string(SOURCE, default_timeout=30).run()
        app.selectbox(key='rs_sidebar_end').set_value(3).run()
        app.selectbox(key='rs_sidebar_start').set_value(4).run()
        self.assertEqual(app.selectbox(key='rs_sidebar_end').value, 4)
        app.multiselect(key='rs_sidebar_cities').set_value([]).run()
        self.healthy(app)
        self.assertEqual(len(app.get('plotly_chart')), 0)

    def test_general_sales_filters_do_not_affect_rs(self):
        root = str(Path(__file__).resolve().parents[1] / 'app.py')
        source = DATA + f'''
import runpy
from unittest.mock import patch
st.session_state['sales_bytes']=b'synthetic'
with patch('data_loader.load_sales',return_value=sales):
    runpy.run_path({root!r},run_name='__main__')
'''
        app = AppTest.from_string(source, default_timeout=30).run()
        self.healthy(app)
        app.multiselect(key='sales_dist').set_value(['Другой']).run()
        self.healthy(app)
        rs_tab = next(tab for tab in app.tabs if tab.label == '🟦 Русский Свет')
        fact = next(m.value for m in rs_tab.metric if m.label == 'Факт 2026')
        self.assertEqual(fact, '800')
        app.multiselect(key='rs_sidebar_cities').set_value(['Тверь']).run()
        self.healthy(app)
        rs_tab = next(tab for tab in app.tabs if tab.label == '🟦 Русский Свет')
        self.assertEqual(next(m.value for m in rs_tab.metric if m.label == 'Факт 2026'), '400')
        self.assertEqual(app.multiselect(key='sales_dist').value, ['Другой'])
