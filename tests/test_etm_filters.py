from pathlib import Path
from unittest import TestCase

from streamlit.testing.v1 import AppTest


ROOT = str(Path(__file__).resolve().parents[1] / 'app.py')
SOURCE = '''
import runpy
from unittest.mock import patch
import pandas as pd
import streamlit as st
rows=[]
for geo,op,category,amount in [('Север','Тверь ОП1','А',100),('Юг','Тула ОП1','Б',300)]:
    row={'ПОК':'DKC (138+2572)','РК':'РК','ДП':'ДП','Макрорегион ДКС':'Центр (ЦО)',
         'ОП':op,'37 кл':'К','География':geo,'Тип подразделения':'ОП',
         'Товарная категория':category,'Специализация':category}
    for month in [1,2]:
        row.update({f'Факт_{month}_2025':amount/2,f'Факт_{month}_2026':amount,f'План_{month}_2026':amount*2})
    rows.append(row)
df=pd.DataFrame(rows)
st.session_state['etm_bytes']=b'synthetic'
with patch('tabs.tab_etm._read_etm',return_value=(df,[1,2])):
    runpy.run_path(ROOT,run_name='__main__')
'''.replace('runpy.run_path(ROOT,', f'runpy.run_path({ROOT!r},')


class EtmGeographyTests(TestCase):
    def healthy(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertFalse(app.error, [e.value for e in app.error])

    def fact(self, app):
        etm = next(t for t in app.tabs if t.label == '🟧 ЭТМ')
        return next(m.value for m in etm.metric if m.label == 'Факт 2026')

    def test_remove_and_restore_south_updates_all_dependent_filters(self):
        app = AppTest.from_string(SOURCE, default_timeout=30).run()
        self.healthy(app)
        self.assertEqual(self.fact(app), '800')
        for _ in range(2):
            app.multiselect(key='etm_sidebar_v104_geo').set_value(['Север']).run()
            self.healthy(app)
            self.assertEqual(self.fact(app), '200')
            app.multiselect(key='etm_sidebar_v104_geo').set_value(['Север','Юг']).run()
            self.healthy(app)
            self.assertEqual(self.fact(app), '800')
            self.assertEqual(app.multiselect(key='etm_sidebar_v104_op').value, ['Тверь ОП1','Тула ОП1'])
            self.assertEqual(app.multiselect(key='etm_sidebar_v104_dimension_Товарные категории').value, ['А','Б'])
        app.multiselect(key='etm_sidebar_v104_op').set_value(['Тула ОП1']).run()
        self.assertEqual(self.fact(app), '600')
        app.multiselect(key='etm_sidebar_v104_geo').set_value(['Север']).run()
        self.healthy(app)
        self.assertEqual(self.fact(app), '200')
        app.multiselect(key='etm_sidebar_v104_geo').set_value([]).run()
        self.healthy(app)
        etm = next(t for t in app.tabs if t.label == '🟧 ЭТМ')
        self.assertEqual(len(etm.metric), 0)
        app.multiselect(key='etm_sidebar_v104_geo').set_value(['Юг']).run()
        self.healthy(app)
        self.assertEqual(self.fact(app), '600')
        app.selectbox(key='etm_sidebar_period_end').set_value(1).run()
        app.multiselect(key='etm_sidebar_v104_geo').set_value(['Север','Юг']).run()
        self.healthy(app)
        self.assertEqual(app.selectbox(key='etm_sidebar_period_end').value, 1)
        self.assertEqual(self.fact(app), '400')
