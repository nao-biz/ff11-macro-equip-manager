"""Startup master ownership through real synthetic reload and save operations."""
from contextlib import ExitStack
from copy import deepcopy
import os
import io
import json
import reader as cli
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from ff11reader import application, codecs, equipment_saving
from ff11reader.adapters import LocalReader
from ff11reader.edit_application import Editor
from ff11reader.master_data import MasterData
from ff11reader.snapshot_loading import verify_master_data, items_with_icons
from tests.test_validation_loading import fixture
from tests.test_equipment_slots import record, SlotFixture
from tests.test_saving import checksum


def forbid_decoding():
    stack = ExitStack()
    for method in ('load_items', 'load_phrases', 'load_augment_names', 'load_rank_augments'):
        stack.enter_context(patch.object(LocalReader, method, side_effect=AssertionError(method)))
    stack.enter_context(patch.object(codecs, 'item_records', side_effect=AssertionError('item decode')))
    stack.enter_context(patch.object(equipment_saving, 'item_records', side_effect=AssertionError('equipment item decode')))
    return stack


class MasterLifecycleTests(unittest.TestCase):
    def test_cli_export_serializes_readonly_values_without_runtime_owner(self):
        with fixture() as (f, root, _):
            target = f.base/'export.json'
            with patch('sys.argv', ['reader.py', '--root', str(root), '--export', str(target)]), patch('sys.stdout', io.StringIO()):
                cli.main()
            value = json.loads(target.read_text(encoding='utf-8'))
            self.assertNotIn('master_data', value)
            self.assertEqual(value['items']['100']['name'], 'Robe0')
            self.assertEqual(value['characters'][0]['folder_id'], 'abc')

    def test_deep_readonly_values_share_and_own_constructor_input(self):
        items = {1:{'nested':[{'name':'original'}]}}
        master = MasterData('root', items, {}, {}, {}, None, (), (), frozenset())
        items[1]['nested'][0]['name'] = 'outside'
        self.assertEqual(master.items[1]['nested'][0]['name'], 'original')
        self.assertIs(deepcopy(master), master)
        with self.assertRaises(TypeError): master.items[1]['nested'][0]['name'] = 'inside'
        with self.assertRaises(TypeError): del master.items._values

    def test_reload_refreshes_inventory_and_keeps_master_identity_and_evidence(self):
        with fixture() as (f, root, _):
            f.editor.root = root.resolve()
            initial = f.editor.snapshot()
            path = f.folder/'wr.dat'; raw = bytearray(path.read_bytes())
            struct.pack_into('<BBH', raw, 0xA3C+20+16, 1, 0, 101)
            path.write_bytes(checksum(raw))
            with forbid_decoding(): f.editor.reload()
            current = f.editor.snapshot()
            self.assertNotEqual(current.characters[0].inventory, initial.characters[0].inventory)
            self.assertIs(current.master_data, initial.master_data)
            self.assertIs(current.phrases, initial.phrases)
            self.assertEqual(current.master_data.sources, initial.master_data.sources)
            self.assertTrue(any(r.item_id == 101 for r in current.characters[0].inventory))

    def test_save_fork_undo_and_reload_do_not_decode_masters(self):
        with fixture() as (f, root, _):
            master = f.editor.master_data
            with forbid_decoding():
                f.edit_line('/say 【Robe0】')
                f.editor.undo()
                self.assertFalse(f.editor.session.dirty)
                f.editor.redo()
                session = f.editor.capture_save_session()
                self.assertIs(session.view().master_data, master)
                before, after, _ = session.save_inputs('abc', session.changes_since_save())
                self.assertIs(before.items, master.items)
                self.assertIs(after.items, master.items)
                plans = f.editor.prepare_writeback()
                f.editor.writeback(plans, f.base/'backups')
                self.assertFalse(f.editor.session.dirty)
                reloaded = application.load_snapshot(root, master)
                self.assertIs(reloaded.master_data, master)
            fresh = application.load_snapshot(root)
            self.assertIsNot(fresh.master_data, master)
            self.assertEqual(fresh.characters, reloaded.characters)

    def test_master_change_with_same_timestamp_keeps_edits_and_stops_save(self):
        with fixture() as (f, root, path):
            # Plain text does not add dictionary dependencies to its macro plan.
            f.edit_line('/echo changed')
            plans = f.editor.prepare_writeback()
            snapshot = f.editor.snapshot()
            stamp = path.stat()
            path.write_bytes(path.read_bytes() + record(102, 0, 'New'))
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            with self.assertRaisesRegex(ValueError, '再起動'):
                f.editor.writeback(plans, f.base/'backups')
            self.assertEqual(f.editor.snapshot(), snapshot)
            for plan in plans:
                for file in plan.files: self.assertEqual(Path(file.target).read_bytes(), file.original)
            self.assertFalse((f.base/'backups').exists())
            reused = application.load_snapshot(root, snapshot.master_data)
            self.assertNotIn(102, reused.items)
            with self.assertRaisesRegex(ValueError, '再起動'): verify_master_data(reused.master_data)
            self.assertIn(102, application.load_snapshot(root).items)

    def test_other_installation_rejects_reused_master(self):
        with fixture() as (f, root, _):
            other = f.base/'other'; (other/'USER').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'インストール先'):
                application.load_snapshot(other, f.editor.master_data)

    def test_new_item_icon_renders_without_redecoding_dictionary(self):
        with fixture() as (f, root, path):
            raw = bytearray(record(102, 0, 'New').translate(codecs.ROTATE))
            struct.pack_into('<IiiHHI', raw, 0x295, 40, 32, 32, 1, 8, 0)
            path.write_bytes(path.read_bytes() + bytes(((v<<5)|(v>>3))&255 for v in raw))
            master = application.load_snapshot(root).master_data
            self.assertIsNone(master.items[102]['icon_png'])
            with forbid_decoding(): result = items_with_icons(master, {102})
            self.assertTrue(result[102]['icon_png'])
            self.assertIsNone(master.items[102]['icon_png'])
            self.assertIs(result[100], master.items[100])


class EquipmentMasterLifecycleTests(SlotFixture):
    def setUp(self):
        super().setUp()
        self.table.write_bytes(self.table.read_bytes().ljust(0x20000, b'\0'))

    def test_equipment_save_uses_shared_items_and_checks_locked_evidence(self):
        root = self.folder.parent.parent
        self.editor = Editor(application.load_snapshot(root), self.base/'shared.json', root=root)
        with forbid_decoding():
            self.edit()
            plan = self.preview()
            self.editor.save_equipment(plan, self.base/'backups')
        reopened = application.load_snapshot(root)
        piece = reopened.characters[0].equipsets[0].slots[0]
        self.assertEqual((piece.item_id, piece.container, piece.index), (0x4001, 1, 3))
        self.assertFalse(self.editor.session.dirty)

    def test_cached_item_validation_rejects_mismatched_locked_catalog(self):
        root = self.folder.parent.parent
        master = application.load_snapshot(root).master_data
        data = {self.table.resolve():self.table.read_bytes(), self.master.resolve():self.master.read_bytes()+b'x'}
        with self.assertRaisesRegex(ValueError, '再起動'):
            equipment_saving.validation_items(root.resolve(), (str(self.master.resolve()),), data, master)
