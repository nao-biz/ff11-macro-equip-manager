"""Shared restore guarantees through both format-specific entry points."""
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch
from ff11reader import file_io, macro_saving, equipment_saving
from tests.property_support import GameFixture, isolated


class BackupRestoreTests(unittest.TestCase):
    def test_interruption_retries_without_changing_backup_or_other_files(self):
        for kind, restore in (('macro', macro_saving.restore_macro_backup),
                              ('equipment', equipment_saving.restore_equipment_backup)):
            with self.subTest(kind=kind), isolated() as base:
                fixture = GameFixture(base, kind, 1, 2)
                fixture.fix()
                plan = fixture.preview()
                folder = fixture.save(plan)
                backup = {p.name:p.read_bytes() for p in folder.iterdir()}
                other = fixture.folder / 'unrelated.dat'
                other.write_bytes(b'keep')
                with patch.object(file_io, 'atomic_replace') as replace:
                    self.assertEqual(restore(folder), tuple(f.target for f in plan.files))
                    replace.assert_not_called()
                real = file_io.atomic_replace
                def fail_second(target, raw):
                    if str(target) == plan.files[1].target:
                        raise OSError('interrupted restore')
                    real(target, raw)
                with patch.object(file_io, 'atomic_replace', side_effect=fail_second):
                    with self.assertRaisesRegex(OSError, 'interrupted'):
                        restore(folder, True)
                self.assertEqual(Path(plan.files[0].target).read_bytes(), plan.files[0].original)
                self.assertEqual(Path(plan.files[1].target).read_bytes(), plan.files[1].replacement)
                restore(folder, True)
                restore(folder, True)
                for file in plan.files:
                    self.assertEqual(Path(file.target).read_bytes(), file.original)
                self.assertEqual({p.name:p.read_bytes() for p in folder.iterdir()}, backup)
                self.assertEqual(other.read_bytes(), b'keep')

    def test_change_after_unlock_is_preserved_and_stops_restore(self):
        for kind, restore in (('macro', macro_saving.restore_macro_backup),
                              ('equipment', equipment_saving.restore_equipment_backup)):
            with self.subTest(kind=kind), isolated() as base:
                fixture = GameFixture(base, kind, 1, 2)
                fixture.fix()
                plan = fixture.preview()
                folder = fixture.save(plan)
                first = Path(plan.files[0].target)
                @contextmanager
                def changed_after_unlock(target):
                    yield target.read_bytes()
                    if target == first:
                        target.write_bytes(b'external update')
                with patch.object(file_io, 'locked_read', changed_after_unlock):
                    with self.assertRaisesRegex(ValueError, '置換直前'):
                        restore(folder, True)
                self.assertEqual(first.read_bytes(), b'external update')
                self.assertEqual(Path(plan.files[1].target).read_bytes(), plan.files[1].replacement)
