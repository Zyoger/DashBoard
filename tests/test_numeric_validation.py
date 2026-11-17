from io import StringIO
from unittest import TestCase
from unittest.mock import patch

import pandas as pd

from data_loader import load_sales
from numeric_validation import numeric_values
from plans import parse_plans
from tabs.tab_project import COLUMN_MAP, parse_project_file
from tabs.tab_etm import _read_etm


class NumericValidationTests(TestCase):
    def test_blank_and_invalid_values(self):
        result = numeric_values(pd.Series([None, "", " ", "12.5"]), "сумма")
        self.assertEqual(result.isna().tolist(), [True, True, True, False])
        self.assertEqual(result.iloc[3], 12.5)
        for value in ("ошибка", "inf", float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "строка Excel/CSV: 3"):
                numeric_values(pd.Series([0, value]), "сумма")

    def test_plan_validation_and_legacy_months(self):
        with self.assertRaisesRegex(ValueError, "обязательные столбцы"):
            parse_plans(StringIO("Год,План_без_НДС\n2026,100\n"))
        for row in ("2026,1,ошибка", "2026,5,100", "2026,1,", "2026.5,1,100"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                parse_plans(StringIO("Год,Квартал,План_без_НДС\n" + row + "\n"))
        result = parse_plans(StringIO("Год,Месяц,План_без_НДС\n2026,1,100\n2026,2,50\n"))
        self.assertEqual(result.iloc[0].tolist(), [2026, 1, 150])

    def test_sales_rejects_bad_amount_and_accepts_empty(self):
        columns = [f"c{i}" for i in range(10)] + ["Январь 2026"]
        frame = pd.DataFrame([[0]*6 + ["Тверь", "Д", "1", "М", "ошибка"]], columns=columns)
        with patch("data_loader.pd.read_excel", return_value=frame.copy()):
            with self.assertRaisesRegex(ValueError, "Январь 2026.*17"):
                load_sales("unused")
        frame.iloc[0, 10] = None
        with patch("data_loader.pd.read_excel", return_value=frame):
            self.assertEqual(load_sales("unused")["Сумма_без_НДС"].sum(), 0)

    def test_project_rejects_bad_amount(self):
        frame = pd.DataFrame([{key: None for key in COLUMN_MAP}])
        frame.loc[0, "Стоимость для клиента (без НДС)"] = "ошибка"
        parse_project_file.clear()
        with patch("tabs.tab_project.pd.read_excel", return_value=frame):
            with self.assertRaisesRegex(ValueError, "Стоимость для клиента.*2"):
                parse_project_file(b"bad project")

    def test_etm_validates_data_rows_but_ignores_totals(self):
        header = ["ПОК", "РК", "ДП", "Макрорегион ДКС", "ОП", "37 кл",
                  "Товарная категория", "Январь 2025", "ГО план янв26", "Январь 2026"]
        row = ["п", "р", "д", "центр", "Тверь", "к", "А", 1, 2, 3]
        total = ["итого", "р", "д", "центр", "Тверь", "к", "А", "ошибка", 2, 3]
        frame = pd.DataFrame([header, row, total])
        _read_etm.clear()
        with patch("tabs.tab_etm.pd.read_excel", return_value=frame):
            result, months = _read_etm(b"valid etm", "лист", expected_dimension="Товарная категория")
        self.assertEqual(months, [1])
        self.assertEqual(result["Факт_1_2026"].tolist(), [3])
        frame.iloc[1, 9] = "ошибка"
        with patch("tabs.tab_etm.pd.read_excel", return_value=frame):
            with self.assertRaisesRegex(ValueError, "Январь 2026.*2"):
                _read_etm(b"invalid etm", "лист", expected_dimension="Товарная категория")
