"""Real synthetic DAT reads for scoped save validation, without a mocked loader."""
from contextlib import contextmanager
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from ff11reader import application, codecs, macro_saving
from ff11reader import icons, equipment_stat_names, rank_augments  # Load code before the I/O guard.
from ff11reader.adapters import LocalReader
from ff11reader.edit_application import Editor
from ff11reader.editing import plan_macro_fixes
from ff11reader.macro_save_proposal import replay_macro_proposal
from ff11reader.snapshot_loading import load_macro_validation_snapshot
from tests.property_support import isolated
from tests.test_manual_macro_saving import ManualFixture
from tests.test_equipment_slots import record


@contextmanager
def fixture():
    with isolated() as base, patch.object(application.store, 'read_labels', return_value={}):
        f = ManualFixture(base, 'macro', 7, 2)
        root = f.folder.parent.parent
        master = root/'ROM'/'1'/'1.DAT'
        master.parent.mkdir(parents=True)
        master.write_bytes(record(100, 0, 'Robe0') + record(101, 0, 'Robe1'))
        table = bytearray((max(codecs.DAT_IDS) + 1) * 2)
        for logical in codecs.DAT_IDS:
            struct.pack_into('<H', table, logical * 2, 129)
        (root/'FTABLE.DAT').write_bytes(table)
        f.set_line(b'/echo ' + bytes.fromhex('fd07010064fd'))
        f.editor = Editor(application.load_snapshot(root), base/'fresh.json')
        yield f, root, master


def regenerated(snapshot, plan):
    changes = {(c.address, c.line):c for f in plan.files for c in f.changes}
    bases = {a:b.hex() for f in plan.files for a, _, b in f.records}
    before, after = replay_macro_proposal(snapshot, plan.character, changes, bases)
    return macro_saving.prepare_macro_save(before, after, plan.character, plan.scope)


class ValidationLoadingTests(unittest.TestCase):
    def test_scoped_and_full_reads_regenerate_identical_token_and_fix_plans(self):
        for scope in ('all', 'storage-fix'):
            with self.subTest(scope=scope), fixture() as (f, root, _):
                if scope == 'all':
                    f.edit_line('/say 【Robe0】')
                else:
                    source = f.editor.snapshot()
                    f.editor.macro_fixes('abc', plan_macro_fixes(source.characters[0], source.items))
                plan = f.editor.prepare_macro_save('abc', scope)
                full = application.load_snapshot(root)
                scoped = load_macro_validation_snapshot(root, 'abc', [p.page for p in plan.files])
                self.assertEqual(regenerated(scoped, plan), regenerated(full, plan))
                self.assertEqual(regenerated(scoped, plan), plan)
                macro_saving.execute_macro_save(plan, f.base/'backups')
                for file in plan.files:
                    self.assertEqual(Path(file.target).read_bytes(), file.replacement)

    def test_reads_only_target_pages_and_inventory_and_does_not_render_icons(self):
        with fixture() as (f, root, _):
            other = root/'USER'/'def'; other.mkdir()
            (other/'mcr.dat').write_bytes((f.folder/'mcr.dat').read_bytes())
            read = LocalReader.read
            paths = []
            def observe(reader, path):
                paths.append(path)
                return read(reader, path)
            with patch.object(LocalReader, 'read', observe), patch('ff11reader.icons.item_icon', side_effect=AssertionError('UI icon')):
                scoped = load_macro_validation_snapshot(root, 'abc', [0])
            self.assertEqual([c.folder_id for c in scoped.characters], ['abc'])
            self.assertEqual(len(scoped.characters[0].macros), 20)
            self.assertTrue(scoped.characters[0].inventory)
            self.assertNotIn(f.folder/'mcr1.dat', paths)
            self.assertFalse(any(p.parent == other for p in paths))
            self.assertTrue(all(v['icon_png'] is None for v in scoped.items.values()))

    def test_same_timestamp_dependency_changes_abort_before_writing(self):
        for dependency in ('macro', 'dictionary', 'inventory'):
            with self.subTest(dependency=dependency), fixture() as (f, root, master):
                if dependency == 'inventory':
                    source = f.editor.snapshot()
                    f.editor.macro_fixes('abc', plan_macro_fixes(source.characters[0], source.items))
                    plan = f.editor.prepare_macro_save('abc', 'storage-fix')
                    target = f.folder/'wr.dat'
                else:
                    f.edit_line('/say 【Robe0】'); plan = f.preview()
                    target = Path(plan.files[0].target) if dependency == 'macro' else master
                stamp = target.stat()
                raw = bytearray(target.read_bytes()); raw[-1] ^= 1; target.write_bytes(raw)
                os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                current = {Path(p.target):Path(p.target).read_bytes() for p in plan.files}
                with self.assertRaises(ValueError):
                    macro_saving.execute_macro_save(plan, f.base/'backups')
                self.assertEqual({p:p.read_bytes() for p in current}, current)
                self.assertFalse((f.base/'backups').exists())

    def test_changes_during_read_are_hash_checked_and_invalid_scope_rejected(self):
        with fixture() as (f, root, master):
            verify = LocalReader.verify_unchanged
            def mutate_then_verify(reader):
                stamp = master.stat()
                raw = bytearray(master.read_bytes()); raw[-1] ^= 1; master.write_bytes(raw)
                os.utime(master, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                return verify(reader)
            with patch.object(LocalReader, 'verify_unchanged', mutate_then_verify):
                with self.assertRaisesRegex(RuntimeError, 'Sources changed'):
                    load_macro_validation_snapshot(root, 'abc', [0])
            for folder, pages in (('../abc', [0]), ('abc', [-1]), ('abc', [400])):
                with self.assertRaises(ValueError):
                    load_macro_validation_snapshot(root, folder, pages)
