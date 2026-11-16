from decimal import Decimal
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import pandas as pd

from rs_plans import COLUMNS, WIDE_COLUMNS, parse_quarterly_plans, quarterly_to_monthly, validate_quarterly_plans


class QuarterlyPlanTests(TestCase):
    def frame(self, rows):
        return pd.DataFrame(rows, columns=COLUMNS)

    def test_cent_conservation_for_every_quarter(self):
        for q in range(1, 5):
            for amount in [0, .01, .02, .04, 100, 100.01, 9999999.99]:
                with self.subTest(q=q, amount=amount):
                    monthly = quarterly_to_monthly(self.frame([['Тверь', 2026, q, amount]]))[2026]
                    values = monthly.loc['Тверь'].tolist()
                    self.assertEqual(sum(Decimal(str(v)) for v in values), Decimal(str(amount)))
                    self.assertTrue(all(v >= 0 for v in values))
                    self.assertTrue(all(v == 0 for i, v in enumerate(values) if i // 3 != q - 1))
        self.assertEqual(quarterly_to_monthly(self.frame([['Тверь', 2026, 1, 100]]))[2026].iloc[0, :3].tolist(),
                         [33.33, 33.33, 33.34])

    def test_validation_and_duplicates(self):
        for row in [
            ['', 2026, 1, 100], ['Тверь', 2026.5, 1, 100],
            ['Тверь', 2026, 0, 100], ['Тверь', 2026, 5, 100],
            ['Тверь', 2026, 1, -1], ['Тверь', 2026, 1, None],
            ['Тверь', 2026, 1, float('inf')], ['Тверь', 2026, 1, 1.001],
        ]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                validate_quarterly_plans(self.frame([row]))
        with self.assertRaisesRegex(ValueError, 'повторяющиеся'):
            validate_quarterly_plans(self.frame([['Тверь', 2026, 1, 100], [' тверь ', 2026, 1, 200]]))
        with self.assertRaisesRegex(ValueError, 'столбцы'):
            validate_quarterly_plans(pd.DataFrame({'Год': [2026]}))

    def test_four_independent_quarter_totals(self):
        frame = pd.DataFrame([['Тверь', 2026, 100, 300, 600, 1200]], columns=WIDE_COLUMNS)
        monthly = quarterly_to_monthly(frame)[2026].loc['Тверь'].tolist()
        self.assertEqual(monthly, [33.33, 33.33, 33.34, 100, 100, 100, 200, 200, 200, 400, 400, 400])
        with self.assertRaisesRegex(ValueError, 'повторяющиеся'):
            validate_quarterly_plans(pd.concat([frame, frame]))
        frame.loc[0, '2 квартал'] = None
        self.assertEqual(quarterly_to_monthly(frame)[2026].iloc[0, 3:6].sum(), 0)

    def test_reading_trims_names_and_ignores_empty_rows(self):
        frame = self.frame([[None]*4, [' Тверь ', 2026, 2, '1 000,01']])
        with patch('rs_plans.pd.read_excel', return_value=frame):
            result = parse_quarterly_plans(b'bytes are passed to Excel reader')
        self.assertEqual(result.iloc[0].tolist(), ['Тверь', 2026, 2, 1000.01])

    def test_delivered_template_contract(self):
        import openpyxl
        path = Path(__file__).resolve().parents[1] / 'outputs/01a1e535-rs-plans/rs_quarterly_plan_template.xlsx'
        wb = openpyxl.load_workbook(path, data_only=False)
        sheet = wb['Планы РС']
        self.assertEqual([sheet.cell(1, c).value for c in range(1, 7)], WIDE_COLUMNS)
        self.assertTrue(sheet['H2'].value.startswith('=IF('))
        self.assertEqual(sheet['A2'].value, None)
        self.assertEqual(len(sheet.data_validations.dataValidation), 2)
        wb.close()
        with self.assertRaisesRegex(ValueError, 'хотя бы одну строку'):
            parse_quarterly_plans(path.read_bytes())
