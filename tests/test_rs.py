import json
import unittest

from streamlit.testing.v1 import AppTest


SOURCE = '''
import pandas as pd
import streamlit as st
from tabs import tab_rs as rs
rows = []
for year in [2025, 2026]:
    for city in ['Тверь', 'Москва']:
        for month in [3, 4]:
            for material in ['А', 'Б']:
                rows.append({'Год': year, 'Месяц': month, 'Город': city,
                             'Дистрибьютор': 'Русский Свет', 'Материал': material,
                             'Сумма_без_НДС': 100 if year == 2025 else 150})
sales = pd.DataFrame(rows)
base = sales.copy()
if st.session_state.get('filtered', False):
    base = base[(base['Город'] == 'Тверь') & (base['Месяц'] == 4)]
if st.session_state.get('empty', False):
    base = base.iloc[0:0]
ctx = {'base': base, 'sales': sales, 'base_year': 2025,
       'curr_year': st.session_state.get('year', 2026)}
if st.session_state.get('quarterly_rows') is not None:
    from rs_plans import COLUMNS
    frame = pd.DataFrame(st.session_state.pop('quarterly_rows'), columns=COLUMNS)
    rs._store_quarterly_plans(frame, ['Тверь', 'Москва'])
prepared = rs._prepare(ctx)
if prepared is not None:
    st.session_state['prepared_monthly'] = prepared[4]
    st.session_state['prepared_plan'] = prepared[5]
    st.session_state['prepared_heatmap'] = prepared[7]
rs.render(ctx)
'''


class RussianLightTests(unittest.TestCase):
    def app(self, plan=False):
        app = AppTest.from_string(SOURCE, default_timeout=30)
        if plan:
            import pandas as pd
            app.session_state['rs_plans'] = pd.DataFrame(
                [[200, 400], [400, 200]], index=['Москва', 'Тверь'], columns=['Мар', 'Апр'])
        return app.run()

    def healthy(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertFalse(app.error, [e.value for e in app.error])

    def test_layout_palette_and_plan_totals(self):
        app = self.app(plan=True)
        self.healthy(app)
        self.assertEqual([t.label for t in app.tabs],
                         ['📊 Обзор', '📈 Динамика', '🏙 По Офисам', '🎯 План'])
        self.assertEqual(len(app.tabs[0].get('plotly_chart')), 4)
        self.assertEqual(len(app.tabs[1].get('plotly_chart')), 5)
        self.assertEqual(len(app.tabs[2].get('plotly_chart')), 4)
        self.assertEqual(len(app.tabs[3].get('file_uploader')), 1)
        monthly = app.session_state['prepared_monthly']
        self.assertEqual(monthly['План'].tolist(), [600, 600])
        self.assertEqual(monthly['Факт отчётного года'].tolist(), [600, 600])
        self.assertEqual(monthly['Выполнение, %'].tolist(), [100, 100])
        self.assertEqual(app.session_state['prepared_heatmap'].loc['Тверь'].tolist(), [75, 150])
        for chart in app.get('plotly_chart'):
            for trace in json.loads(chart.proto.spec)['data']:
                expected = {'2025': '#94A3B8', '2026': '#4F46E5',
                            'Факт 2025': '#94A3B8', 'Факт 2026': '#4F46E5',
                            'План 2026': '#B45309'}.get(trace.get('name'))
                if expected:
                    self.assertEqual(trace['marker']['color'], expected)
        # Both charts must belong to the same office row.
        pairs = 0
        for block in app.tabs[2]:
            if block.type == 'flex_container':
                columns = [child for child in block.children.values() if child.type == 'column']
                if columns:
                    self.assertEqual([len(c.get('plotly_chart')) for c in columns], [1, 1])
                    pairs += 1
        self.assertEqual(pairs, 2)
        app.button(key='rs_plans_save').click().run()
        self.healthy(app)
        # После сохранения квартальные суммы перераспределены на все три месяца.
        self.assertEqual(app.session_state['prepared_monthly']['План'].sum(), 400)
        self.assertEqual(app.session_state['rs_plans_by_year'][2026].to_numpy().sum(), 1200)

    def test_filters_keep_plans_and_years_are_separate(self):
        app = self.app(plan=True)
        app.session_state['filtered'] = True
        app.run()
        self.healthy(app)
        self.assertEqual(app.session_state['prepared_monthly']['План'].tolist(), [200])
        self.assertEqual(len(app.session_state['prepared_plan']), 2)
        app.session_state['filtered'] = False
        app.session_state['year'] = 2025
        app.run()
        self.healthy(app)
        self.assertEqual(app.session_state['prepared_monthly']['План'].sum(), 0)
        app.session_state['year'] = 2026
        app.run()
        self.healthy(app)
        self.assertEqual(app.session_state['prepared_monthly']['План'].sum(), 1200)

    def test_no_plan_and_empty_filters(self):
        app = self.app()
        self.healthy(app)
        self.assertTrue(app.session_state['prepared_heatmap'].isna().all().all())
        app.session_state['empty'] = True
        app.run()
        self.healthy(app)
        self.assertEqual(len(app.get('plotly_chart')), 0)

    def test_quarterly_import_replaces_year_and_reaches_charts(self):
        app = self.app(plan=True)
        app.session_state['quarterly_rows'] = [
            ['Тверь', 2026, 1, 100], ['Тверь', 2026, 2, 300],
            ['Москва', 2027, 4, 600],
        ]
        app.run()
        self.healthy(app)
        # Выбраны март и апрель: остаток I квартала + 1/3 II квартала.
        self.assertEqual(app.session_state['prepared_monthly']['План'].tolist(), [33.34, 100])
        plan = app.session_state['rs_plans_by_year'][2026]
        self.assertAlmostEqual(plan.loc['Тверь'].sum(), 400)
        self.assertEqual(app.session_state['rs_plans_by_year'][2027].loc['Москва'].sum(), 600)
        app.session_state['filtered'] = True
        app.run()
        self.healthy(app)
        self.assertEqual(app.session_state['prepared_monthly']['План'].tolist(), [100])


if __name__ == '__main__':
    unittest.main()
