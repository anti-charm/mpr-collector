import os
import tempfile
import unittest
from pathlib import Path

from mpr_collector_core import collect_mpr_files, analyze_flat_name_conflicts, copy_files_flat, list_immediate_subfolders


class CollectMprFilesTests(unittest.TestCase):
    def test_scans_selected_folder_to_arbitrary_depth(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deep = root / 'Instrument-A' / 'Project-A' / 'Group-A' / 'Condition-A' / 'Run-01' / 'Sample-07' / 'rerun' / 'more' / 'deep'
            deep.mkdir(parents=True)
            target = deep / 'cell_07.mpr'
            target.write_bytes(b'data')
            (deep / 'ignore.txt').write_text('x')

            found = collect_mpr_files([root / 'Instrument-A'])

            self.assertEqual(found, [target.resolve()])

    def test_overlapping_selected_folders_do_not_duplicate_same_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            child = root / 'Instrument-A' / 'experiment'
            child.mkdir(parents=True)
            target = child / 'x.mpr'
            target.write_bytes(b'x')

            found = collect_mpr_files([root / 'Instrument-A', child])

            self.assertEqual(found, [target.resolve()])

    def test_extension_matching_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            root.mkdir(exist_ok=True)
            a = root / 'A.MPR'
            b = root / 'b.mpr'
            a.write_bytes(b'a')
            b.write_bytes(b'b')

            found = collect_mpr_files([root])

            self.assertEqual({p.name for p in found}, {'A.MPR', 'b.mpr'})

    def test_flat_name_conflicts_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / 'a'; b = root / 'b'
            a.mkdir(); b.mkdir()
            f1 = a / 'same.mpr'; f2 = b / 'same.MPR'
            f1.write_bytes(b'1'); f2.write_bytes(b'2')

            conflicts = analyze_flat_name_conflicts([f1, f2])

            self.assertEqual(len(conflicts), 1)
            self.assertEqual({p.resolve() for p in conflicts['same.mpr']}, {f1.resolve(), f2.resolve()})

    def test_copy_flat_skips_existing_by_default_and_never_moves_sources(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_dir = root / 'src'; dst = root / 'dst'
            src_dir.mkdir(); dst.mkdir()
            src = src_dir / 'file.mpr'
            src.write_bytes(b'new')
            existing = dst / 'file.mpr'
            existing.write_bytes(b'old')

            result = copy_files_flat([src], dst, overwrite=False)

            self.assertTrue(src.exists())
            self.assertEqual(existing.read_bytes(), b'old')
            self.assertEqual(result.skipped_existing, 1)
            self.assertEqual(result.copied, 0)

    def test_copy_flat_can_overwrite_when_explicitly_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_dir = root / 'src'; dst = root / 'dst'
            src_dir.mkdir(); dst.mkdir()
            src = src_dir / 'file.mpr'
            src.write_bytes(b'new')
            existing = dst / 'file.mpr'
            existing.write_bytes(b'old')

            result = copy_files_flat([src], dst, overwrite=True)

            self.assertTrue(src.exists())
            self.assertEqual(existing.read_bytes(), b'new')
            self.assertEqual(result.copied, 1)
            self.assertEqual(result.skipped_existing, 0)


class FolderBrowsingTests(unittest.TestCase):
    def test_lists_immediate_subfolders_of_mother_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Instrument-A").mkdir()
            (root / "Instrument-B").mkdir()
            (root / "not_a_folder.txt").write_text("x")

            found = list_immediate_subfolders(root)

            self.assertEqual([p.name for p in found], ["Instrument-A", "Instrument-B"])


if __name__ == '__main__':
    unittest.main()


class CopyNamePlanningTests(unittest.TestCase):
    def test_continuation_collisions_are_preserved_with_unique_names(self):
        from mpr_collector_core import plan_flat_copy_names
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cell = root / 'cell 12'
            cont = cell / 'cont'
            cont2 = cell / 'cont2'
            cont.mkdir(parents=True)
            cont2.mkdir(parents=True)
            f0 = cell / 'experiment_12_01_cycle_04.mpr'
            f1 = cont / 'experiment_12_01_cycle_04.mpr'
            f2 = cont2 / 'experiment_12_01_cycle_04.mpr'
            for f, data in [(f0,b'0'),(f1,b'1'),(f2,b'2')]:
                f.write_bytes(data)

            plan = plan_flat_copy_names([f0, f1, f2])

            self.assertEqual(plan[f0.resolve()], 'experiment_12_01_cycle_04.mpr')
            self.assertEqual(plan[f1.resolve()], 'experiment_12_01_cycle_04__cont.mpr')
            self.assertEqual(plan[f2.resolve()], 'experiment_12_01_cycle_04__cont2.mpr')
            self.assertEqual(len(set(n.lower() for n in plan.values())), 3)

    def test_repeated_parent_names_use_more_ancestry_until_unique(self):
        from mpr_collector_core import plan_flat_copy_names
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / 'cell 1' / 'cont'
            b = root / 'cell 2' / 'cont'
            a.mkdir(parents=True)
            b.mkdir(parents=True)
            f1 = a / 'same.mpr'; f2 = b / 'same.mpr'
            f1.write_bytes(b'1'); f2.write_bytes(b'2')

            plan = plan_flat_copy_names([f1, f2])

            self.assertEqual(len(set(n.lower() for n in plan.values())), 2)
            self.assertTrue(any('__cell 2__cont' in n.lower() or '__cell 1__cont' in n.lower() for n in plan.values()))

    def test_copy_flat_preserves_all_colliding_sources_using_plan(self):
        from mpr_collector_core import plan_flat_copy_names
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / 'cell 12'; cont = src / 'cont'; dst = root / 'dst'
            cont.mkdir(parents=True); dst.mkdir()
            f0 = src / 'same.mpr'; f1 = cont / 'same.mpr'
            f0.write_bytes(b'original'); f1.write_bytes(b'continuation')
            plan = plan_flat_copy_names([f0, f1])

            result = copy_files_flat([f0, f1], dst, overwrite=False, name_plan=plan)

            self.assertEqual(result.copied, 2)
            self.assertEqual((dst / 'same.mpr').read_bytes(), b'original')
            self.assertEqual((dst / 'same__cont.mpr').read_bytes(), b'continuation')
            self.assertTrue(f0.exists())
            self.assertTrue(f1.exists())


class DisplayPathTests(unittest.TestCase):
    def test_selected_folder_display_starts_at_mother_folder_name(self):
        from mpr_collector_core import relative_display_path
        root = Path('/example/Experiments')
        child = root / 'Instrument-A' / 'Project-A' / 'Condition-1'
        self.assertEqual(relative_display_path(child, root), r'Experiments\Instrument-A\Project-A\Condition-1')

class HierarchicalSelectionTests(unittest.TestCase):
    def test_selecting_parent_includes_all_descendant_mpr_files_and_exclusion_skips_branch(self):
        from mpr_collector_core import collect_mpr_files_by_rules, set_selection_rule
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'Experiments'
            keep = root / 'Instrument-A' / 'Project-A' / 'Method-A' / 'deep' / 'sample 1'
            skip = root / 'Instrument-A' / 'Project-A' / 'Method-B' / 'very' / 'deep' / 'sample 2'
            keep.mkdir(parents=True)
            skip.mkdir(parents=True)
            keep_file = keep / 'keep.mpr'
            skip_file = skip / 'skip.mpr'
            keep_file.write_bytes(b'keep')
            skip_file.write_bytes(b'skip')

            rules = {}
            set_selection_rule(rules, root / 'Instrument-A' / 'Project-A', True)
            set_selection_rule(rules, root / 'Instrument-A' / 'Project-A' / 'Method-B', False)

            found = collect_mpr_files_by_rules(rules)
            self.assertEqual(found, [keep_file.resolve()])

    def test_reselecting_grandchild_inside_excluded_branch_is_supported(self):
        from mpr_collector_core import collect_mpr_files_by_rules, set_selection_rule
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent = root / 'experiment'
            excluded = parent / 'Group-A'
            wanted = excluded / 'Group-B'
            unwanted = excluded / 'Group-C'
            wanted.mkdir(parents=True)
            unwanted.mkdir(parents=True)
            wanted_file = wanted / 'wanted.mpr'
            unwanted_file = unwanted / 'unwanted.mpr'
            wanted_file.write_bytes(b'w')
            unwanted_file.write_bytes(b'u')

            rules = {}
            set_selection_rule(rules, parent, True)
            set_selection_rule(rules, excluded, False)
            set_selection_rule(rules, wanted, True)

            self.assertEqual(collect_mpr_files_by_rules(rules), [wanted_file.resolve()])

    def test_parent_state_is_partial_when_descendant_is_excluded(self):
        from mpr_collector_core import selection_state, set_selection_rule
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent = root / 'parent'; child = parent / 'child'
            child.mkdir(parents=True)
            rules = {}
            set_selection_rule(rules, parent, True)
            self.assertEqual(selection_state(parent, rules), 'checked')
            set_selection_rule(rules, child, False)
            self.assertEqual(selection_state(parent, rules), 'partial')
            self.assertEqual(selection_state(child, rules), 'unchecked')

    def test_selecting_parent_clears_older_descendant_exclusions(self):
        from mpr_collector_core import selection_state, set_selection_rule
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent = root / 'parent'; child = parent / 'child'
            child.mkdir(parents=True)
            rules = {}
            set_selection_rule(rules, parent, True)
            set_selection_rule(rules, child, False)
            set_selection_rule(rules, parent, True)
            self.assertEqual(selection_state(parent, rules), 'checked')
            self.assertEqual(selection_state(child, rules), 'checked')


class OverwriteSafetyTests(unittest.TestCase):
    def test_overwrite_replaces_only_same_named_planned_files_and_keeps_unrelated_destination_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src_dir = root / 'src'; dst = root / 'dst'
            src_dir.mkdir(); dst.mkdir()
            src = src_dir / 'update.mpr'
            src.write_bytes(b'new')
            (dst / 'update.mpr').write_bytes(b'old')
            unrelated = dst / 'keep_me.mpr'
            unrelated.write_bytes(b'keep')

            result = copy_files_flat([src], dst, overwrite=True)

            self.assertEqual(result.copied, 1)
            self.assertEqual((dst / 'update.mpr').read_bytes(), b'new')
            self.assertEqual(unrelated.read_bytes(), b'keep')


class StableContinuationNamingTests(unittest.TestCase):
    def test_continuation_folder_gets_stable_suffix_even_when_scanned_without_original(self):
        from mpr_collector_core import plan_flat_copy_names
        with tempfile.TemporaryDirectory() as td:
            cont = Path(td) / 'cell 1' / 'cont2'
            cont.mkdir(parents=True)
            f = cont / 'same.mpr'
            f.write_bytes(b'x')
            plan = plan_flat_copy_names([f])
            self.assertEqual(plan[f.resolve()], 'same__cont2.mpr')

class SettingsPersistenceTests(unittest.TestCase):
    def test_settings_round_trip_preserves_last_root_and_destination_paths(self):
        from mpr_collector_core import load_folder_settings, save_folder_settings
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / 'settings.json'
            root = Path(td) / 'Experiments'
            dest = Path(td) / 'Collected MPR'
            save_folder_settings(settings, root, dest)
            loaded_root, loaded_dest = load_folder_settings(settings)
            self.assertEqual(loaded_root, str(root))
            self.assertEqual(loaded_dest, str(dest))

class LocalProgramStorageTests(unittest.TestCase):
    def test_program_data_directory_is_created_next_to_collector(self):
        from mpr_collector_core import local_program_data_dir
        with tempfile.TemporaryDirectory() as td:
            program_dir = Path(td) / 'MPR Collector'
            program_dir.mkdir()
            result = local_program_data_dir(program_dir)
            self.assertEqual(result, program_dir.resolve() / 'MPR_Collector_Data')
            self.assertTrue(result.is_dir())


class AppSettingsTests(unittest.TestCase):
    def test_app_settings_round_trip_includes_color_scheme(self):
        from mpr_collector_core import load_app_settings, save_app_settings
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / 'settings.json'
            save_app_settings(settings, 'C:/Experiments', 'C:/Collected', 'Sage & Linen')
            loaded = load_app_settings(settings)
            self.assertEqual(loaded['root_folder'], 'C:/Experiments')
            self.assertEqual(loaded['destination_folder'], 'C:/Collected')
            self.assertEqual(loaded['color_scheme'], 'Sage & Linen')


class ColorSchemeTests(unittest.TestCase):
    def test_six_or_more_professional_color_schemes_are_available(self):
        from mpr_collector_themes import COLOR_SCHEMES
        self.assertGreaterEqual(len(COLOR_SCHEMES), 6)
        required = {
            'bg', 'card', 'border', 'text', 'muted', 'accent',
            'accent_hover', 'accent_pressed', 'soft', 'soft_hover',
            'select_bg', 'table_alt', 'rename_bg', 'entry_bg',
            'shadow', 'gradient_start', 'gradient_middle', 'gradient_end',
        }
        for name, scheme in COLOR_SCHEMES.items():
            self.assertTrue(name.strip())
            self.assertTrue(required.issubset(scheme.keys()), name)
