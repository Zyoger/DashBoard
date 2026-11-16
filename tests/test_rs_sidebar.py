from unittest import TestCase
from pathlib import Path

from streamlit.testing.v1 import AppTest


class SidebarPlanTests(TestCase):
    def test_upload_location(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        uploaders = app.sidebar.get('file_uploader')
        self.assertNotIn('План продаж РС', [w.label for w in uploaders])
        self.assertIn('Файл плана (.csv)', [w.label for w in uploaders])

    def test_upload_does_not_overwrite_manual_edits_on_rerun(self):
        source = '''
from io import BytesIO
from unittest.mock import patch
import pandas as pd
import streamlit as st
from tabs import tab_rs as rs
from rs_plans import COLUMNS
frame=pd.DataFrame([['Тверь',2026,1,300],['Тверь',2026,2,600]], columns=COLUMNS)
with patch('tabs.tab_rs.parse_quarterly_plans', return_value=frame):
    rs.load_quarterly_upload(BytesIO(b'file'), ['Тверь'])
if st.session_state.get('manual'):
    st.session_state['rs_plans_by_year'][2026].loc['Тверь','Янв']=777
st.metric('План января',st.session_state['rs_plans_by_year'][2026].loc['Тверь','Янв'])
'''
        app = AppTest.from_string(source, default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '100.0')
        app.session_state['manual'] = True
        app.run()
        app.session_state['manual'] = False
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '777.0')
