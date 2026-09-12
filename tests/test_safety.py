import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mpr_collector_core import collect_mpr_files_by_rules, copy_files_flat, plan_flat_copy_names


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, data=b'research'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path.resolve()

    def test_generated_name_cannot_collide_with_an_original_name(self):
        a = self.file('sample/cont/run.mpr', b'a')
        b = self.file('sample/run__cont.mpr', b'b')
        for sources in ([a, b], [b, a]):
            plan = plan_flat_copy_names(sources)
            self.assertEqual(len(set(n.casefold() for n in plan.values())), 2)
            self.assertEqual(plan[b], 'run__cont.mpr')
        self.assertEqual(plan_flat_copy_names([a, b]), plan_flat_copy_names([b, a]))

    def test_continuation_never_loses_suffix_in_mixed_depth_group(self):
        a = self.file('cell/cont/run.mpr')
        b = self.file('cell/extra/deep/cont2/run.mpr')
        plan = plan_flat_copy_names([a, b])
        self.assertEqual(plan[a], 'run__cont.mpr')
        self.assertEqual(plan[b], 'run__cont2.mpr')

    def test_plan_cannot_write_outside_destination(self):
        src = self.file('src/run.mpr')
        protected = self.file('outside.mpr', b'original')
        result = copy_files_flat([src], self.root / 'dst', overwrite=True,
                                 name_plan={src: '../outside.mpr'})
        self.assertEqual(protected.read_bytes(), b'original')
        self.assertEqual(result.failed, 1)

    def test_destination_cannot_overwrite_any_selected_source(self):
        a = self.file('src/a.mpr', b'a')
        b = self.file('src/b.mpr', b'b')
        result = copy_files_flat([a, b], a.parent, overwrite=True,
                                 name_plan={a: 'b.mpr', b: 'a.mpr'})
        self.assertEqual(a.read_bytes(), b'a')
        self.assertEqual(b.read_bytes(), b'b')
        self.assertEqual(result.failed, 2)

    def test_interrupted_copy_keeps_previous_destination_intact(self):
        src = self.file('src/run.mpr', b'new')
        dst = self.file('dst/run.mpr', b'old')
        def interrupted(source, target):
            Path(target).write_bytes(b'partial')
            raise OSError('Simulated disk failure')
        with patch('mpr_collector_core.shutil.copy2', side_effect=interrupted):
            result = copy_files_flat([src], dst.parent, overwrite=True)
        self.assertEqual(dst.read_bytes(), b'old')
        self.assertEqual(src.read_bytes(), b'new')
        self.assertEqual(result.failed, 1)
        self.assertEqual(list(dst.parent.iterdir()), [dst])

    def test_duplicate_custom_targets_fail_before_any_copy(self):
        a = self.file('src/a.mpr', b'a')
        b = self.file('src/b.mpr', b'b')
        dst = self.root / 'dst'
        result = copy_files_flat([a, b], dst, overwrite=True,
                                 name_plan={a: 'same.mpr', b: 'SAME.MPR'})
        self.assertEqual(result.failed, 2)
        self.assertEqual(list(dst.glob('*.mpr')), [])

    def test_missing_source_does_not_damage_destination(self):
        src = self.root / 'missing.mpr'
        dst = self.file('dst/missing.mpr', b'old')
        result = copy_files_flat([src], dst.parent, overwrite=True)
        self.assertEqual(result.failed, 1)
        self.assertEqual(dst.read_bytes(), b'old')

    def test_destination_creation_failure_is_reported(self):
        src = self.file('src/run.mpr')
        dest = self.file('not-a-directory')
        result = copy_files_flat([src], dest)
        self.assertEqual(result.failed, 1)

    def test_scan_does_not_report_success_when_a_branch_is_unreadable(self):
        root = self.root / 'experiments'
        root.mkdir()
        def unreadable(*args, **kwargs):
            if kwargs.get('onerror'):
                kwargs['onerror'](PermissionError('Unreadable experiment folder'))
            return iter(())
        with patch('mpr_collector_core.os.walk', side_effect=unreadable):
            with self.assertRaises(PermissionError):
                collect_mpr_files_by_rules({root: True})
