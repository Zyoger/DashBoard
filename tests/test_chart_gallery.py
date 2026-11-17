from unittest import TestCase
from unittest.mock import MagicMock, patch
from tabs import tab_test


class ChartGalleryTests(TestCase):
    def test_table_indicators_and_filters_render(self):
        with patch.object(tab_test, "st") as ui:
            ui.dataframe.return_value.selection.rows = [0, 1]
            ui.data_editor.side_effect = lambda frame, **kwargs: frame
            ui.columns.side_effect = lambda count: [MagicMock() for _ in range(count)]
            ui.multiselect.return_value = ["А", "Б"]
            ui.slider.side_effect = [0, (0, 150)]
            ui.text_input.return_value = ""
            ui.selectbox.return_value = "Все"
            ui.checkbox.return_value = False
            tab_test._render_tables()
            tab_test._render_indicators()
            tab_test._render_filters()
            tab_test._render_badges()
            tab_test._render_kpi_cards()
            tab_test._render_details()
            ui.download_button.assert_called_once()
            self.assertGreaterEqual(ui.dataframe.call_count, 5)
            ui.progress.assert_called_once()
            self.assertEqual(ui.expander.call_count, 2)

    def test_each_example_builds(self):
        with patch.object(tab_test, "st") as ui:
            for choice in [name for group in tab_test.EXAMPLE_GROUPS.values() for name in group]:
                with self.subTest(choice=choice):
                    ui.reset_mock()
                    ui.selectbox.side_effect = lambda *args, **kwargs: choice
                    tab_test._render_example([choice], "example")
                    self.assertTrue(any((ui.line_chart.called, ui.area_chart.called, ui.bar_chart.called,
                                         ui.scatter_chart.called, ui.map.called, ui.plotly_chart.called,
                                         ui.altair_chart.called, ui.vega_lite_chart.called, ui.echarts_chart.called,
                                         ui.pydeck_chart.called, ui.mermaid_chart.called, ui.graphviz_chart.called)))
