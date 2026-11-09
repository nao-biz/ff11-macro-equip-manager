"""Read policy, source evidence and semantic decoding have separate contracts."""
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from ff11reader import application, macro_saving
from ff11reader.adapters import LocalReader
from ff11reader.edit_application import Editor
from ff11reader.loaded_files import LoadedFiles
from ff11reader.read_requests import CharacterReadRequest
from ff11reader.resource_catalog import AUGMENT_NAME_RESOURCES, RANK_RESOURCES
from ff11reader.saving import digest
from ff11reader.snapshot_loading import load_macro_validation_snapshot
from tests.property_support import checksum
from tests.test_validation_loading import fixture, regenerated


class ReadBoundaryTests(unittest.TestCase):
    def test_generic_request_selects_equipment_without_adding_inventory(self):
        with fixture() as (f, root, _):
            (f.folder/'es0.dat').write_bytes(checksum(bytearray(1624)))
            folders = ['abc']; names = {'ES0.DAT'}
            request = CharacterReadRequest(folders, names)
            folders.append('def'); names.add('mcr.dat')
            reader = LocalReader(root)
            characters = reader.load_characters(request=request)
            self.assertEqual(len(characters), 1)
            self.assertEqual(len(characters[0].equipsets), 20)
            self.assertEqual(characters[0].macros, [])
            self.assertEqual(characters[0].inventory, [])
            self.assertEqual([Path(s['path']).name for s in reader.sources], ['es0.dat'])
            self.assertEqual(request.folders, ('abc',))

    def test_request_rejects_paths_outside_character_files(self):
        for folders, names in ((('../abc',), None), (('abc',), {'../mcr.dat'}),
                               (('abc',), {'C:\\file'}), (('abc',), {'.'})):
            with self.subTest(folders=folders, names=names), self.assertRaises(ValueError):
                CharacterReadRequest(folders, names)

    def test_unused_assets_are_observed_without_decoding_and_still_guard_saves(self):
        with fixture() as (f, root, _):
            table_path = root/'FTABLE.DAT'
            table = bytearray(table_path.read_bytes())
            table.extend(bytes(max(AUGMENT_NAME_RESOURCES + RANK_RESOURCES)*2+2-len(table)))
            for logical in AUGMENT_NAME_RESOURCES + RANK_RESOURCES:
                struct.pack_into('<H', table, logical*2, 130)
            table_path.write_bytes(table)
            asset = root/'ROM'/'1'/'2.DAT'
            asset.write_bytes(b'undecodable-but-observed-source')
            full = application.load_snapshot(root)
            f.editor = Editor(full, f.base/'with-assets.json')
            f.edit_line('/say 【Robe0】'); plan = f.preview()
            expected = regenerated(full, plan)
            with (patch.object(LocalReader, 'load_augment_names', side_effect=AssertionError('unused decoder')),
                  patch.object(LocalReader, 'load_rank_augments', side_effect=AssertionError('unused decoder'))):
                scoped = load_macro_validation_snapshot(root, 'abc', [0])
                self.assertEqual(regenerated(scoped, plan), expected)
            evidence = LoadedFiles(scoped.sources)
            self.assertIn(asset.resolve(), evidence.shared_resources(root))
            self.assertIn(str(asset.resolve()), dict(plan.dependencies))
            stamp = asset.stat(); asset.write_bytes(b'changed-but-same-timestamp')
            os.utime(asset, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            originals = {Path(p.target):Path(p.target).read_bytes() for p in plan.files}
            with self.assertRaises(ValueError):
                macro_saving.execute_macro_save(plan, f.base/'backups')
            self.assertEqual({p:p.read_bytes() for p in originals}, originals)

    def test_incidental_read_is_not_a_dependency_and_table_changes_are_rejected(self):
        with fixture() as (f, root, _):
            f.edit_line('/say 【Robe0】'); expected = f.preview()
            original = application.load_snapshot(root)
            extra = root/'ROM'/'unrelated.dat'; extra.write_bytes(b'unrelated')
            original.sources.append({'path':str(extra), 'sha256':digest(extra.read_bytes())})
            self.assertEqual(regenerated(original, expected), expected)
            evidence = LoadedFiles(original.sources)
            self.assertNotIn(extra.resolve(), evidence.shared_resources(root))
            table = root/'FTABLE.DAT'; stamp = table.stat()
            raw = bytearray(table.read_bytes()); raw[0] ^= 1; table.write_bytes(raw)
            os.utime(table, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            with self.assertRaisesRegex(ValueError, '配置表'):
                evidence.shared_resources(root)
