import gc
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import mpr_collector as ui


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        # Older Tkinter releases may finalize abandoned images/variables on a
        # worker thread unless previous test windows are collected here.
        gc.collect()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = Path(self.temp.name)
        self.config_patch = patch.object(ui, 'app_config_dir', return_value=self.cfg)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.app = ui.MPRCollectorApp()
        self.app.update()
        self.app.withdraw()
        self.addCleanup(self._destroy_app)

    def _destroy_app(self):
        app = self.app
        app.destroy()
        self.app = None
        del app
        gc.collect()

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

    def test_existing_destination_is_replaced_by_default(self):
        root = self.cfg / 'experiment'
        root.mkdir()
        source = root / 'sample.mpr'
        source.write_bytes(b'new result')
        destination = self.cfg / 'collected'
        destination.mkdir()
        target = destination / source.name
        target.write_bytes(b'old result')
        self.app.root_folder.set(str(root))
        self.app.destination_folder.set(str(destination))
        self.app._apply_root_entry()
        self.app.selection_rules[root.resolve()] = True
        self.app.scan_files()
        self.wait_for_job()
        self.assertTrue(self.app.overwrite_existing.get())
        row = self.app.files_table.get_children()[0]
        self.assertEqual(self.app.files_table.set(row, 'action'), 'Replace')
        with patch.object(ui.messagebox, 'askyesno', return_value=True), patch.object(ui.messagebox, 'showinfo'):
            self.app.copy_files()
            self.wait_for_job()
        self.assertEqual(target.read_bytes(), b'new result')
        self.assertEqual(source.read_bytes(), b'new result')

    def test_transferred_absolute_preset_rebases_nested_rules(self):
        old_root = self.cfg / 'old_computer'  # This path does not exist here.
        new_root = self.cfg / 'current_computer'
        (new_root / 'batch' / 'skip' / 'include_again').mkdir(parents=True)
        self.app.root_folder.set(str(new_root))
        self.app._apply_root_entry()
        preset = {'shared': {'root': str(old_root), 'rules': [
            {'path': str(old_root), 'selected': True},
            {'path': str(old_root / 'batch' / 'skip'), 'selected': False},
            {'path': str(old_root / 'batch' / 'skip' / 'include_again'), 'selected': True},
        ]}}
        self.app.presets_path.write_text(json.dumps(preset), encoding='utf-8')
        self.app.preset_name.set('shared')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        warning.assert_not_called()
        self.assertEqual(self.app.selection_rules, {
            new_root.resolve(): True,
            (new_root / 'batch' / 'skip').resolve(): False,
            (new_root / 'batch' / 'skip' / 'include_again').resolve(): True,
        })
        self.assertEqual(Path(self.app.root_folder.get()).resolve(), new_root.resolve())

    def test_new_preset_remains_usable_after_moving_mother_folder(self):
        old_root = self.cfg / 'original'
        excluded = old_root / 'batch' / 'skip'
        excluded.mkdir(parents=True)
        self.app.root_folder.set(str(old_root))
        self.app._apply_root_entry()
        self.app.selection_rules = {old_root.resolve(): True, excluded.resolve(): False}
        with patch.object(ui.simpledialog, 'askstring', return_value='portable'):
            self.app.save_preset()
        stored = json.loads(self.app.presets_path.read_text(encoding='utf-8'))['portable']
        self.assertEqual([item['path'] for item in stored['rules']], ['.', 'batch/skip'])

        new_root = self.cfg / 'moved'
        old_root.rename(new_root)
        self.app.root_folder.set(str(new_root))
        self.app._apply_root_entry()
        self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {
            new_root.resolve(): True,
            (new_root / 'batch' / 'skip').resolve(): False,
        })

    def test_transferred_preset_prompts_for_mother_folder_and_cancel_keeps_selection(self):
        old_root = self.cfg / 'not_here'
        new_root = self.cfg / 'available'
        (new_root / 'batch').mkdir(parents=True)
        self.app.presets_path.write_text(json.dumps({'shared': {
            'root': str(old_root),
            'rules': [{'path': str(old_root / 'batch'), 'selected': True}],
        }}), encoding='utf-8')
        self.app.preset_name.set('shared')
        with patch.object(ui.filedialog, 'askdirectory', return_value=''), patch.object(ui.messagebox, 'showwarning'):
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {})
        self.assertIsNone(self.app._loaded_root)
        with patch.object(ui.filedialog, 'askdirectory', return_value=str(new_root)), patch.object(ui.messagebox, 'showwarning'):
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {(new_root / 'batch').resolve(): True})
        self.assertEqual(self.app._loaded_root, new_root.resolve())

    def test_transferred_preset_finds_unique_moved_final_folder(self):
        old_root = self.cfg / 'old'
        new_root = self.cfg / 'new'
        selected = new_root / 'new_group' / 'sample'
        excluded = selected / 'skip'
        excluded.mkdir(parents=True)
        self.app.root_folder.set(str(new_root))
        self.app._apply_root_entry()
        self.app.presets_path.write_text(json.dumps({'shared': {
            'root': str(old_root),
            'rules': [
                {'path': str(old_root / 'old_group' / 'sample'), 'selected': True},
                {'path': str(old_root / 'old_group' / 'sample' / 'skip'), 'selected': False},
            ],
        }}), encoding='utf-8')
        self.app.preset_name.set('shared')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        warning.assert_not_called()
        self.assertEqual(self.app.selection_rules, {selected.resolve(): True, excluded.resolve(): False})

    def test_ambiguous_final_folder_does_not_replace_current_selection(self):
        old_root = self.cfg / 'old'
        new_root = self.cfg / 'new'
        first = new_root / 'first' / 'sample'
        second = new_root / 'second' / 'sample'
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        self.app.root_folder.set(str(new_root))
        self.app._apply_root_entry()
        self.app.selection_rules = {first.resolve(): True}
        self.app.presets_path.write_text(json.dumps({'shared': {
            'root': str(old_root),
            'rules': [{'path': str(old_root / 'old_group' / 'sample'), 'selected': True}],
        }}), encoding='utf-8')
        self.app.preset_name.set('shared')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {first.resolve(): True})
        self.assertIn('ambiguous', warning.call_args.args[1].lower())

    def test_empty_saved_folder_cannot_select_entire_mother_folder(self):
        root = self.cfg / 'available'
        safe = root / 'safe'
        safe.mkdir(parents=True)
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.selection_rules = {safe.resolve(): True}
        self.app.presets_path.write_text(json.dumps({'bad': {
            'root': str(self.cfg / 'old'), 'path_format': 'relative',
            'rules': [{'path': '', 'selected': True}],
        }}), encoding='utf-8')
        self.app.preset_name.set('bad')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {safe.resolve(): True})
        warning.assert_called_once()

    def test_malformed_saved_selection_cannot_turn_exclusion_into_inclusion(self):
        root = self.cfg / 'available'
        root.mkdir()
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.presets_path.write_text(json.dumps({'bad': {
            'root': str(self.cfg / 'old'), 'path_format': 'relative',
            'rules': [{'path': '.', 'selected': 'false'}],
        }}), encoding='utf-8')
        self.app.preset_name.set('bad')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {})
        warning.assert_called_once()

    def test_out_of_order_moved_exclusion_does_not_select_wrong_parent(self):
        root = self.cfg / 'available'
        selected = root / 'sample'
        unrelated = root / 'elsewhere' / 'skip'
        selected.mkdir(parents=True)
        unrelated.mkdir(parents=True)
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.presets_path.write_text(json.dumps({'bad': {
            'root': str(self.cfg / 'old'), 'path_format': 'relative',
            'rules': [
                {'path': 'sample/skip', 'selected': False},
                {'path': 'sample', 'selected': True},
            ],
        }}), encoding='utf-8')
        self.app.preset_name.set('bad')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {})
        warning.assert_called_once()

    def test_nested_exclusion_matches_within_its_selected_parent(self):
        old_root = self.cfg / 'old'
        new_root = self.cfg / 'new'
        parent = new_root / 'batch' / 'sample'
        excluded = parent / 'new_parent' / 'skip'
        excluded.mkdir(parents=True)
        (new_root / 'unrelated' / 'skip').mkdir(parents=True)
        self.app.root_folder.set(str(new_root))
        self.app._apply_root_entry()
        self.app.presets_path.write_text(json.dumps({'shared': {
            'root': str(old_root), 'path_format': 'relative',
            'rules': [
                {'path': 'batch/sample', 'selected': True},
                {'path': 'batch/sample/old_parent/skip', 'selected': False},
            ],
        }}), encoding='utf-8')
        self.app.preset_name.set('shared')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        warning.assert_not_called()
        self.assertEqual(self.app.selection_rules, {parent.resolve(): True, excluded.resolve(): False})

    def test_legacy_list_preset_rebases_unique_final_folder(self):
        old_root = self.cfg / 'old'
        new_root = self.cfg / 'new'
        chosen = new_root / 'new_group' / 'sample'
        chosen.mkdir(parents=True)
        self.app.root_folder.set(str(new_root))
        self.app._apply_root_entry()
        self.app.presets_path.write_text(json.dumps({'legacy': [str(old_root / 'old_group' / 'sample')]}),
                                         encoding='utf-8')
        self.app.preset_name.set('legacy')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        warning.assert_not_called()
        self.assertEqual(self.app.selection_rules, {chosen.resolve(): True})

    def test_legacy_list_ambiguous_folder_keeps_selection(self):
        old_root = self.cfg / 'old'
        new_root = self.cfg / 'new'
        first = new_root / 'first' / 'sample'
        second = new_root / 'second' / 'sample'
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        self.app.root_folder.set(str(new_root))
        self.app._apply_root_entry()
        self.app.selection_rules = {first.resolve(): True}
        self.app.presets_path.write_text(json.dumps({'legacy': [str(old_root / 'old_group' / 'sample')]}),
                                         encoding='utf-8')
        self.app.preset_name.set('legacy')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {first.resolve(): True})
        self.assertIn('ambiguous', warning.call_args.args[1].lower())

    def test_explicit_mother_folder_overrides_existing_saved_root(self):
        saved_root = self.cfg / 'saved_root'
        current_root = self.cfg / 'current_root'
        (saved_root / 'batch').mkdir(parents=True)
        (current_root / 'batch').mkdir(parents=True)
        self.app.root_folder.set(str(current_root))
        self.app._apply_root_entry()
        self.app.presets_path.write_text(json.dumps({'shared': {
            'root': str(saved_root),
            'rules': [{'path': str(saved_root / 'batch'), 'selected': True}],
        }}), encoding='utf-8')
        self.app.preset_name.set('shared')
        self.app.load_preset()
        self.assertEqual(Path(self.app.root_folder.get()).resolve(), current_root.resolve())
        self.assertEqual(self.app.selection_rules, {(current_root / 'batch').resolve(): True})

    def test_empty_preset_cannot_clear_current_selection(self):
        root = self.cfg / 'available'
        safe = root / 'safe'
        safe.mkdir(parents=True)
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.selection_rules = {safe.resolve(): True}
        for raw in ({'root': str(root), 'path_format': 'relative', 'rules': []}, []):
            with self.subTest(raw=raw):
                self.app.presets_path.write_text(json.dumps({'empty': raw}), encoding='utf-8')
                self.app.preset_name.set('empty')
                with patch.object(ui.messagebox, 'showwarning') as warning:
                    self.app.load_preset()
                self.assertEqual(self.app.selection_rules, {safe.resolve(): True})
                warning.assert_called_once()

    def test_conflicting_duplicate_preset_rule_keeps_selection(self):
        root = self.cfg / 'available'
        safe = root / 'safe'
        safe.mkdir(parents=True)
        self.app.root_folder.set(str(root))
        self.app._apply_root_entry()
        self.app.selection_rules = {safe.resolve(): True}
        self.app.presets_path.write_text(json.dumps({'bad': {
            'root': str(root), 'path_format': 'relative',
            'rules': [
                {'path': 'safe', 'selected': True},
                {'path': 'safe', 'selected': False},
            ],
        }}), encoding='utf-8')
        self.app.preset_name.set('bad')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        self.assertEqual(self.app.selection_rules, {safe.resolve(): True})
        warning.assert_called_once()

    def test_literal_tilde_folder_in_portable_preset(self):
        old_root = self.cfg / 'old'
        chosen = self.cfg / 'new' / '~' / 'sample'
        chosen.mkdir(parents=True)
        self.app.root_folder.set(str(self.cfg / 'new'))
        self.app._apply_root_entry()
        self.app.presets_path.write_text(json.dumps({'shared': {
            'root': str(old_root), 'path_format': 'relative',
            'rules': [{'path': '~/sample', 'selected': True}],
        }}), encoding='utf-8')
        self.app.preset_name.set('shared')
        with patch.object(ui.messagebox, 'showwarning') as warning:
            self.app.load_preset()
        warning.assert_not_called()
        self.assertEqual(self.app.selection_rules, {chosen.resolve(): True})

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
