import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import mpr_collector as ui


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = Path(self.temp.name)
        self.config_patch = patch.object(ui, 'app_config_dir', return_value=self.cfg)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.app = ui.MPRCollectorApp()
        self.app.update()
        self.app.withdraw()
        self.addCleanup(self.app.destroy)

    def test_mother_folder_itself_can_be_selected(self):
        root = self.cfg / 'experiment'
        root.mkdir()
        (root / 'direct.mpr').write_bytes(b'x')
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        nodes = self.app.tree.get_children()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(self.app.item_paths[nodes[0]], root.resolve())

    def test_reapplying_same_root_preserves_selection(self):
        root = self.cfg / 'experiment'
        root.mkdir()
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.selection_rules[root.resolve()] = True
        self.app._apply_root_entry()
        self.assertEqual(self.app.selection_rules, {root.resolve(): True})

    def test_privacy_option_clears_saved_paths_but_keeps_theme(self):
        self.assertTrue(hasattr(self.app, 'remember_paths'))
        self.app.root_folder.set('C:/private-research')
        self.app.destination_folder.set('C:/private-output')
        self.app.remember_paths.set(False)
        self.app._save_last_folders()
        saved = json.loads((self.cfg / 'settings.json').read_text())
        self.assertEqual(saved['root_folder'], '')
        self.assertEqual(saved['destination_folder'], '')
        self.assertEqual(saved['color_scheme'], self.app.color_scheme.get())
        self.assertFalse(saved['remember_paths'])

    def test_background_job_returns_result_through_main_loop(self):
        self.assertTrue(hasattr(self.app, '_start_job'))
        received = []
        self.app._start_job(lambda: 42, received.append, 'Testing')
        deadline = time.monotonic() + 3
        while not received and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertEqual(received, [42])
        self.assertFalse(self.app._busy)

    def test_layout_saves_and_restores_resized_columns(self):
        self.app.files_table.column('name', width=333)
        self.app._save_last_folders()
        saved = json.loads((self.cfg / 'settings.json').read_text())
        self.assertIn('layout', saved)
        self.assertEqual(saved['layout']['columns']['name'], 333)
        reopened = ui.MPRCollectorApp()
        try:
            reopened.update()
            self.assertEqual(reopened.files_table.column('name', 'width'), 333)
        finally:
            reopened.destroy()

    def test_click_then_space_toggles_folder_instead_of_editing_path(self):
        root = self.cfg / 'experiment'
        root.mkdir()
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.deiconify()
        self.app.update()
        self.app.dest_entry.focus_force()
        self.app.update()
        node = self.app.tree.get_children()[0]
        x, y, width, height = self.app.tree.bbox(node)
        self.app.tree.event_generate('<Button-1>', x=x + 65, y=y + height // 2)
        self.app.update()
        self.assertEqual(self.app.focus_get(), self.app.tree)
        self.assertFalse(any(self.app.selection_rules.values()))
        self.app.tree.event_generate('<KeyPress-space>')
        self.app.update()
        self.assertTrue(any(self.app.selection_rules.values()))

    def test_scan_then_copy_keeps_source_and_creates_destination(self):
        root = self.cfg / 'experiment'
        root.mkdir()
        original = root / 'sample.mpr'
        original.write_bytes(b'original scientific data')
        self.app.root_folder.set(str(root))
        self.app.destination_folder.set(str(self.cfg / 'collected'))
        self.app._apply_root_entry()
        self.app.selection_rules[root.resolve()] = True
        self.app.scan_files()
        self.wait_for_job()
        self.assertEqual(self.app.scanned_files, [original.resolve()])
        with patch.object(ui.messagebox, 'askyesno', return_value=True), patch.object(ui.messagebox, 'showinfo'):
            self.app.copy_files()
            self.wait_for_job()
        self.assertEqual((self.cfg / 'collected/sample.mpr').read_bytes(), b'original scientific data')
        self.assertEqual(original.read_bytes(), b'original scientific data')

    def wait_for_job(self):
        deadline = time.monotonic() + 3
        while self.app._busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertFalse(self.app._busy)

    def test_invalid_edited_root_invalidates_previous_scan(self):
        root = self.cfg / 'experiment'
        root.mkdir()
        source = root / 'sample.mpr'
        source.write_bytes(b'sample')
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.selection_rules[root.resolve()] = True
        self.app._finish_scan([source.resolve()])
        self.app.root_folder.set(str(self.cfg / 'missing'))
        with patch.object(ui.messagebox, 'showwarning'):
            self.app._apply_root_entry()
        self.assertEqual(self.app.scanned_files, [])
