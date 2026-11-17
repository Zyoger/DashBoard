import unittest
import pandas as pd
from project_analytics import prepare_projects, validate_offers, metrics, monthly_metrics, monthly_comparison, distributor_comparison, distributor_group, month_bounds, compare_periods, latest_year_rows
from datetime import date


class ProjectAnalyticsTests(unittest.TestCase):
    def test_latest_year_uses_unfiltered_source(self):
        source = pd.DataFrame({"Дата создания": pd.to_datetime(["2025-02-01", "2026-04-01", None])})
        year, result = latest_year_rows(source, source.iloc[[0, 2]])
        self.assertEqual(year, 2026)
        self.assertTrue(result.empty)
        year, result = latest_year_rows(source, source)
        self.assertEqual(result.index.tolist(), [1])

    def test_distributor_groups_are_explicit_and_keep_unknown_names(self):
        self.assertEqual(distributor_group("Русский Свет филиал, г.Тверь Осн."), "Русский Свет")
        self.assertEqual(distributor_group("ЭТМ ОП1, г.Малоярославец"), "ЭТМ")
        self.assertEqual(distributor_group('ООО "ТОТАЛЭЛЕКТРО" ОП БРЯНСК'), 'ООО "ТОТАЛЭЛЕКТРО"')
        self.assertEqual(distributor_group('ООО "ЭЛЕКТРОСТРОЙ"'), 'ООО "ЭЛЕКТРОСТРОЙ"')
        self.assertEqual(distributor_group("ЭТМстрой"), "ЭТМстрой")
        self.assertEqual(distributor_group(None), "(не указано)")

    def test_month_bounds_include_leap_day_and_cross_year(self):
        self.assertEqual(month_bounds("2024-02", "2024-02"), (date(2024, 2, 1), date(2024, 2, 29)))
        self.assertEqual(month_bounds("2025-12", "2026-01"), (date(2025, 12, 1), date(2026, 1, 31)))
        with self.assertRaises(ValueError):
            month_bounds("2026-02", "2026-01")

    def test_month_range_includes_last_day_at_any_time(self):
        frame = pd.DataFrame({"Дата создания": pd.to_datetime(["2024-02-01", "2024-02-29 23:59:59", "2024-03-01"], format="mixed")})
        periods = compare_periods(frame, month_bounds("2024-02", "2024-02"), month_bounds("2024-03", "2024-03"))
        self.assertEqual([len(part) for part in periods], [2, 1])

    def setUp(self):
        self.data = prepare_projects(pd.DataFrame({
            "Проект": ["100 - A", "100 - A", None],
            "Объект / предложение": ["1 - A", "2 - B", "3 - C"],
            "Стоимость для дистрибьютора, руб.": [100., 200., 0.],
            "Заказы, руб.": [50., 0., 0.],
            "Стадия": ["Полный заказ", "Другая", "Другая"],
        }))

    def test_metrics_use_ids_and_distributor_value(self):
        validate_offers(self.data)
        result = metrics(self.data)
        self.assertEqual(result["Количество проектов"], 1)
        self.assertEqual(result["Количество предложений"], 3)
        self.assertEqual(result["Сумма предложений, руб."], 300)
        self.assertAlmostEqual(result["Конверсия в заказ, %"], 100 / 3)
        self.assertAlmostEqual(result["Реализация потенциала, %"], 50 / 300 * 100)

    def test_duplicate_offer_rejected(self):
        with self.assertRaisesRegex(ValueError, "повторных"):
            validate_offers(pd.concat([self.data, self.data.iloc[:1]]))

    def test_zero_denominator_is_undefined(self):
        result = metrics(self.data.iloc[0:0])
        self.assertIsNone(result["Конверсия в заказ, %"])
        self.assertIsNone(result["Реализация потенциала, %"])

    def test_monthly_ratios_are_calculated_from_rows(self):
        self.data["Дата создания"] = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-02-01"])
        monthly = monthly_metrics(self.data).set_index("Месяц")
        self.assertEqual(monthly.loc[1, "Количество предложений"], 2)
        self.assertEqual(monthly.loc[1, "Конверсия в заказ, %"], 50)
        self.assertAlmostEqual(monthly.loc[1, "Реализация потенциала, %"], 50 / 300 * 100)

    def test_comparison_total_is_recalculated_and_outside_period_missing(self):
        self.data["Дата создания"] = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-02-01"])
        current = self.data.copy()
        current["Дата создания"] += pd.DateOffset(years=1)
        table = monthly_comparison([self.data, current], (date(2025,1,1), date(2025,2,28)), (date(2026,1,1), date(2026,2,28)))
        self.assertAlmostEqual(table.loc["Итого", "Конверсия в заказ, % — прошлый"], 100 / 3)
        self.assertTrue(pd.isna(table.loc["3", "Количество предложений — прошлый"]))
        self.assertEqual(table.loc["Итого", "Количество предложений: динамика, %"], 0)

    def test_distributor_comparison_preserves_all_periods_and_empty_names(self):
        self.data["Дистрибьютор"] = ["А", "Б", None]
        result = distributor_comparison([self.data.iloc[:2], self.data.iloc[1:]])
        self.assertEqual(set(result.index), {"А", "Б", "(не указано)"})
        self.assertEqual(result.loc["А", "Количество — прошлый"], 1)
        self.assertEqual(result.loc["А", "Количество — текущий"], 0)
        self.assertEqual(result.loc["Б", "Предложения — текущий"], 200)
        self.assertEqual(result.loc["А", "Заказы — прошлый"], 50)
        self.assertEqual(result.loc["(не указано)", "Количество — текущий"], 1)
