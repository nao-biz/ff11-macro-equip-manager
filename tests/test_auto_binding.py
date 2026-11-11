"""Synthetic native identity and first-login import; no game files are accessed."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from lupa.lua51 import LuaRuntime
from ff11reader.augment_import import parse, export_value
from ff11reader.augment_store import AugmentStore
from ff11reader.domain import Snapshot
from tests.test_augment_import import character, fixture, encoded

ROOT = Path(__file__).resolve().parents[1]


class NativeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(encoding=None, unpack_returned_tuples=True)
        self.module = self.lua.execute((ROOT/'addons/ff11export/user_directory.lua').read_bytes())
        self.base = 0x100000
        self.data = bytearray(0x20000)
        self.path_offset = 0x100
        path = bytes.fromhex('8B0D000000008B542408528B818000000050E80000000081C6F4010000508B44241456680000000050E8')
        self.data[0x100:0x100+len(path)] = path
        self.word(0x102, self.base+0x800)
        self.word(0x113, 0x200-(0x100+23))
        self.word(0x124, self.base+0x500)
        self.data[0x500:0x509] = b'%s/%x/%s\0'
        self.data[0x200:0x210] = bytes.fromhex('8B44240450E80000000083C404C20400')
        self.word(0x206, 0x300-(0x200+10))
        self.data[0x300:0x31e] = bytes.fromhex('8B4C24048D04CD000000002BC18B0D000000008D04808B848124380100C3')
        self.word(0x30f, self.base+0x804)
        self.word(0x800, self.base+0x1000)
        self.word(0x804, self.base+0x2000)
        self.word(0x1080, 0)
        self.entry(0, 0xabc, b'Alpha')
        self.entry(1, 0xdef, b'Beta')

    def word(self, offset, value):
        struct.pack_into('<I', self.data, offset, value)

    def entry(self, slot, content, name):
        at = 0x2000+0x13824+slot*140
        self.word(at, content)
        self.data[at+12:at+28] = name.ljust(16, b'\0')
        self.data[at+28:at+44] = b'Synthetic'.ljust(16, b'\0')

    def read(self, address, size):
        offset = address-self.base
        if offset < 0 or offset+size > len(self.data):
            raise OSError('unreadable')
        return bytes(self.data[offset:offset+size])

    def resolve(self):
        return self.module.resolve(bytes(self.data), self.base, self.read, b'C:/synthetic')

    def test_windower4_adapter_uses_lua51_native_bridge(self):
        self.data[:2] = b'MZ'
        self.word(60, 0x40)
        self.data[0x40:0x44] = b'PE\0\0'
        self.word(0x90, len(self.data))
        self.lua.globals().resolver = self.module
        self.lua.globals().read_native = self.read
        self.lua.globals().module_native = lambda: (self.base, b'C:/synthetic/FFXiMain.dll')
        self.lua.execute(b"""
            package.preload.user_directory=function()return resolver end
            windower={addon_path='synthetic/'}
            package.loadlib=function(path,symbol)
                assert(path=='synthetic/ff11identity-v1.dll' and symbol=='luaopen_ff11identity')
                return function()return {read=read_native,module=module_native}end
            end
        """)
        adapter = self.lua.execute((ROOT/'addons/ff11export/user_directory_win32.lua').read_bytes())
        reader = adapter.new(self.lua.eval(b'function(s)return s end'))
        self.assertEqual(reader(b'Alpha',b'Synthetic')[b'folder_id'],b'abc')

    def test_selected_slot_switch_and_identity_guards(self):
        read = self.resolve()
        self.assertEqual(read(b'Alpha', b'Synthetic')[b'folder_id'], b'abc')
        self.word(0x1080, 1)
        self.assertEqual(read(b'Beta', b'Synthetic')[b'folder_id'], b'def')
        for name, world in ((b'Alpha', b'Synthetic'), (b'Beta', b'Other')):
            with self.assertRaises(Exception): read(name, world)
        self.word(0x1080, 16)
        with self.assertRaises(Exception): read(b'Beta', b'Synthetic')

    def test_unknown_or_ambiguous_game_build_is_rejected(self):
        self.data[0x100] = 0
        with self.assertRaises(Exception): self.resolve()
        self.setUp()
        self.data[0x600:0x62b] = self.data[0x100:0x12b]
        with self.assertRaises(Exception): self.resolve()

    def test_selection_changes_during_read_is_rejected(self):
        original = self.read
        calls = []
        def unstable(address, size):
            result = original(address, size)
            if size == 44:
                calls.append(True)
                self.word(0x1080, 1)
            return result
        read = self.module.resolve(bytes(self.data), self.base, unstable, b'C:/synthetic')
        with self.assertRaises(Exception): read(b'Alpha', b'Synthetic')
        self.assertTrue(calls)


class AutomaticBindingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.inbox = self.root/'Windower/addons/ff11export/data'
        self.inbox.mkdir(parents=True)
        self.store = AugmentStore(self.root/'app/observations')
        self.store.settings.path.parent.mkdir(parents=True)
        self.store.settings.path.write_text(json.dumps(dict(format='ff11-windower-settings',version=1,
                                                          folder=str(self.root/'Windower'))))
        self.key = hashlib.sha256(str(self.root).casefold().encode()).hexdigest()
        chars = [character(), character()]
        chars[1].folder_id = 'def'
        for c in chars: (self.root/'USER'/c.folder_id).mkdir(parents=True)
        self.snapshot = Snapshot('synthetic','now',chars,{},[],[],installation_key=self.key)

    def publish(self, cid=123, folder='abc', server=1, **origin_changes):
        value = fixture()
        value['character'].update(id=cid, server=server, name='Alpha' if cid==123 else 'Beta')
        value['origin'] = dict(method='ffxi-user-directory-v1',installation=str(self.root),folder_id=folder)
        value['origin'].update(origin_changes)
        path = self.inbox/f'auto-{server}-{cid}-20261103T000000Z-000001.json'
        path.write_bytes(encoded(value))
        return path

    def test_first_login_multiple_characters_import_and_restart(self):
        self.publish()
        self.publish(456,'def')
        observations, errors = self.store.restore(self.snapshot)
        self.assertFalse(errors)
        self.assertEqual(set(observations), {'abc','def'})
        self.assertEqual(observations['def'].export.character_name, 'Beta')
        before = self.store.sources.path.read_bytes()
        restored, errors = AugmentStore(self.store.directory).restore(self.snapshot)
        self.assertEqual(restored, observations)
        self.assertFalse(errors)
        self.assertEqual(self.store.sources.path.read_bytes(), before)

    def test_conflicting_batch_publishes_no_bindings(self):
        self.publish()
        self.publish(456,'abc')
        observations, errors = self.store.restore(self.snapshot)
        self.assertFalse(observations)
        self.assertIn('キャラ対応', errors)
        self.assertFalse(self.store.sources.path.exists())

    def test_existing_identity_cannot_move_to_another_folder(self):
        self.publish()
        self.store.restore(self.snapshot)
        before = self.store.sources.path.read_bytes()
        self.publish(folder='def')
        observations, errors = self.store.restore(self.snapshot)
        self.assertIn('キャラ対応', errors)
        self.assertNotIn('def', observations)
        self.assertEqual(self.store.sources.path.read_bytes(), before)

    def test_other_installation_legacy_and_unsafe_folder_are_not_bound(self):
        p = self.publish(installation=str(self.root/'other'))
        self.assertFalse(self.store.restore(self.snapshot)[0])
        value = fixture()
        p.write_bytes(encoded(value))
        self.assertFalse(self.store.restore(self.snapshot)[0])
        self.publish(folder='../abc')
        self.assertIn('キャラ対応', self.store.restore(self.snapshot)[1])
        self.assertFalse(self.store.sources.path.exists())

    def test_failed_registration_retries_and_provenance_roundtrips(self):
        p = self.publish()
        original = parse(p.read_bytes())
        self.assertEqual(parse(encoded(export_value(original))), original)
        with patch('ff11reader.augment_sources.atomic_json', side_effect=OSError('disk')):
            observations, errors = self.store.restore(self.snapshot)
        self.assertFalse(observations)
        self.assertIn('キャラ対応', errors)
        self.assertFalse(self.store.sources.path.exists())
        self.assertIn('abc', self.store.restore(self.snapshot)[0])
