import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mpr_collector as ui


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = patch.object(ui, 'app_config_dir', return_value=self.base)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.app = ui.MPRCollectorApp()
        self.app.update()
        self.addCleanup(self.app.destroy)
        self.root = self.base / 'experiments'
        (self.root / 'child').mkdir(parents=True)
        self.app.root_folder.set(str(self.root))
        self.app._apply_root_entry()
        self.node = self.app.tree.get_children()[0]
        self.app.update()

    def event(self, node, element):
        self.app.tree.see(node)
        self.app.update()
        x, y, width, height = self.app.tree.bbox(node)
        y += height // 2
        for px in range(x, x + width):
            if element in self.app.tree.identify_element(px, y):
                return SimpleNamespace(x=px, y=y)
        self.fail(f'No {element} target found')

    def test_folder_label_click_preserves_inclusions_and_exclusions(self):
        self.app.selection_rules = {self.root.resolve(): True, (self.root / 'child').resolve(): False}
        self.app._selection_changed()
        before = dict(self.app.selection_rules)
        self.app._on_tree_click(self.event(self.node, 'text'))
        self.assertEqual(self.app.selection_rules, before)

    def test_checkbox_toggles_once_per_double_click(self):
        self.assertTrue(hasattr(self.app, '_selection_images'))
        event = self.event(self.node, 'image')
        self.app._on_tree_click(event)
        self.app._on_tree_double_click(event)
        self.assertEqual(self.app.selection_rules, {self.root.resolve(): True})
        self.app._on_tree_click(event)
        self.assertEqual(self.app.selection_rules, {})

    def test_double_click_label_expands_without_changing_selection(self):
        self.app.tree.item(self.node, open=False)
        event = self.event(self.node, 'text')
        self.app._on_tree_click(event)
        self.app._on_tree_double_click(event)
        self.assertTrue(self.app.tree.item(self.node, 'open'))
        self.assertEqual(self.app.selection_rules, {})

    def test_popup_sort_filter_and_close_leave_main_table_unchanged(self):
        self.assertTrue(hasattr(self.app, 'open_review_window'))
        a = self.root / 'alpha.mpr'
        b = self.root / 'beta.mpr'
        a.write_bytes(b'a'); b.write_bytes(b'b')
        self.app._finish_scan([a.resolve(), b.resolve()])
        self.app.files_table.column('name', width=333)
        original = [self.app.files_table.item(i, 'values') for i in self.app.files_table.get_children()]
        self.app.open_review_window()
        self.app.update()
        view = self.app.review_popup_view
        view.sort_by('name'); view.sort_by('name')
        view.search.set('beta')
        self.app.update()
        self.assertEqual(len(view.table.get_children()), 1)
        self.assertEqual(self.app.files_table.column('name', 'width'), 333)
        self.assertEqual([self.app.files_table.item(i, 'values') for i in self.app.files_table.get_children()], original)
        self.assertIsNone(self.app.grab_current())
        self.app.review_window.destroy()
        self.app._finish_scan([a.resolve()])
        self.assertEqual(len(self.app.files_table.get_children()), 1)

    def test_autofit_includes_longest_value_and_caps_extreme_paths(self):
        self.assertTrue(hasattr(self.app, 'review_view'))
        view = self.app.review_view
        view.set_rows([dict(name='sample.mpr', copy_as='filename_with_a_long_suffix.mpr',
                            action='Copy', naming='Name adjusted', modified='', source='long/' * 100)])
        view.autofit('copy_as')
        self.assertGreater(view.table.column('copy_as', 'width'), 100)
        view.autofit('source')
        self.assertLessEqual(view.table.column('source', 'width'), 520)
        self.assertLessEqual(view.table.column('source', 'width'), view.table.winfo_width() // 2 + 1)

    def test_dark_theme_applies_to_entries_and_popup(self):
        from mpr_collector_themes import COLOR_SCHEMES
        self.assertIn('Dark Red', COLOR_SCHEMES)
        self.assertIn('Dark Blue', COLOR_SCHEMES)
        self.app.open_review_window()
        self.app.color_scheme.set('Dark Red')
        self.app._on_color_scheme_changed()
        self.app.update()
        style = ui.ttk.Style(self.app)
        self.assertEqual(style.lookup('TEntry', 'foreground'), COLOR_SCHEMES['Dark Red']['text'])
        self.assertEqual(self.app.review_window.cget('background'), COLOR_SCHEMES['Dark Red']['bg'])

    def test_reset_layout_restores_new_name_change_column(self):
        self.app.files_table.column('naming', width=500)
        self.app.reset_layout()
        self.assertEqual(self.app.files_table.column('naming', 'width'), 140)
