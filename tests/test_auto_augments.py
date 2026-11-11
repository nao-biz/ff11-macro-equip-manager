import copy
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ff11reader.augment_sources import AugmentSource
from ff11reader.augment_store import AugmentStore
from ff11reader.augment_names import apply_names
from ff11reader.domain import Snapshot
from tests.test_augment_import import character, fixture, encoded


class AutoImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.inbox = self.base/'inbox'
        self.inbox.mkdir()
        self.store = AugmentStore(self.base/'store')
        self.source = AugmentSource('installation','abc',123,1,str(self.inbox),'synthetic trace')
        self.store.sources.register(self.source)
        self.snapshot = Snapshot('test','now',[character()],{},[],[],installation_key='installation')
        self.snapshot.characters[0].display_name = 'Manual'

    def publish(self, stamp='2026-11-03T00:00:00Z', name='Automatic', **changes):
        value = fixture()
        value['captured_at'] = stamp
        value['character']['name'] = name
        value['character'].update(changes)
        filename = 'auto-1-123-' + stamp.replace('-','').replace(':','') + '-000001.json'
        path = self.inbox/filename
        path.write_bytes(encoded(value))
        return path

    def test_startup_reload_name_and_independent_history_input(self):
        self.publish()
        before = copy.deepcopy(self.snapshot)
        observations, errors = self.store.restore(self.snapshot)
        self.assertFalse(errors)
        self.assertEqual(self.snapshot, before)
        apply_names(self.snapshot, observations)
        self.assertEqual(self.snapshot.characters[0].display_name,'Automatic')
        self.assertEqual(self.snapshot.characters[0].identity_status,'export_verified')
        self.publish('2026-11-04T00:00:00Z','Renamed')
        observations, errors = AugmentStore(self.base/'store').restore(self.snapshot)
        self.assertFalse(errors)
        self.assertEqual(observations['abc'].export.character_name,'Renamed')

    def test_old_and_tmp_do_not_replace(self):
        newest = self.publish('2026-11-04T00:00:00Z')
        observations, _ = self.store.restore(self.snapshot)
        saved = self.store.path('installation','abc').read_bytes()
        newest.unlink()
        self.publish('2026-11-03T00:00:00Z','Old')
        (self.inbox/'auto-1-123-20261105T000000Z-000001.json.tmp').write_text('partial')
        with patch.object(self.store,'save',side_effect=AssertionError('unexpected write')):
            restored, errors = self.store.restore(self.snapshot)
        self.assertFalse(errors)
        self.assertEqual(restored,observations)
        self.assertEqual(self.store.path('installation','abc').read_bytes(),saved)

    def test_later_export_in_same_second_replaces_individual_information(self):
        first = self.publish()
        self.store.restore(self.snapshot)
        value = json.loads(first.read_bytes())
        value['character']['name'] = 'Latest'
        second = first.with_name(first.name.replace('000001.json','000002.json'))
        second.write_bytes(encoded(value))
        observations, errors = self.store.restore(self.snapshot)
        self.assertFalse(errors)
        self.assertEqual(observations['abc'].export.character_name, 'Latest')

    def test_wrong_identity_corrupt_latest_and_failed_save_keep_pair(self):
        self.publish()
        previous, _ = self.store.restore(self.snapshot)
        saved = self.store.path('installation','abc').read_bytes()
        for changes in ({'id':124}, {'server':2}):
            self.publish('2026-11-04T00:00:00Z',**changes)
            result, errors = self.store.restore(self.snapshot)
            self.assertEqual(result,previous)
            self.assertIn('abc',errors)
        path = self.publish('2026-11-04T00:00:00Z')
        path.write_bytes(b'partial')
        result, errors = self.store.restore(self.snapshot)
        self.assertEqual(result,previous)
        self.assertIn('abc',errors)
        self.publish('2026-11-04T00:00:00Z','New')
        with patch.object(Path,'replace',side_effect=OSError('failure')):
            result, errors = self.store.restore(self.snapshot)
        self.assertEqual(result,previous)
        self.assertIn('abc',errors)
        self.assertEqual(self.store.path('installation','abc').read_bytes(),saved)

    def test_unknown_binding_and_old_store_require_confirmation(self):
        self.publish()
        self.store.restore(self.snapshot)
        path=self.store.path('installation','abc')
        value=json.loads(path.read_bytes())
        value['version']=1
        value.pop('binding')
        path.write_bytes(encoded(value))
        self.assertIsNotNone(self.store.load('installation','abc'))
        self.store.sources.path.unlink()
        result, errors=self.store.restore(self.snapshot)
        self.assertFalse(result)
        self.assertIn('abc',errors)

    def test_installation_and_other_character_isolation(self):
        self.publish()
        self.snapshot.installation_key='other'
        self.assertEqual(self.store.restore(self.snapshot),({},{}))
        with self.assertRaises(ValueError):
            self.store.sources.register(replace(self.source,server=2))

    def test_missing_inbox_retains_saved_information(self):
        path=self.publish()
        old,_=self.store.restore(self.snapshot)
        path.unlink();self.inbox.rmdir()
        result,errors=self.store.restore(self.snapshot)
        self.assertEqual(result,old)
        self.assertIn('abc',errors)

    def test_first_export_wait_empty_or_missing_and_real_read_failures(self):
        from ff11reader.augment_inbox import ExportPending
        for exists in (True, False):
            if not exists:self.inbox.rmdir()
            observations, notices = self.store.restore(self.snapshot)
            self.assertFalse(observations)
            self.assertIsInstance(notices['abc'], ExportPending)
            self.assertIn('ゲームにログインすると自動取得されます', notices['abc'])
        self.inbox.mkdir()
        with patch.object(Path, 'iterdir', side_effect=PermissionError('denied')):
            _, notices = self.store.restore(self.snapshot)
        self.assertNotIsInstance(notices['abc'], ExportPending)
        self.store.sources.register(replace(self.source,directory=str(self.base/'lost'/'data')))
        _, notices = self.store.restore(self.snapshot)
        self.assertNotIsInstance(notices['abc'], ExportPending)

    def test_duplicate_binding_is_rejected(self):
        value=json.loads(self.store.sources.path.read_bytes())
        value['sources']*=2
        self.store.sources.path.write_bytes(encoded(value))
        with self.assertRaises(ValueError):self.store.sources.read()

    def test_two_characters_share_inbox_without_cross_import(self):
        self.publish(name='CharacterA')
        self.snapshot.characters.append(replace(character(),folder_id='def'))
        self.store.sources.register(replace(self.source,folder_id='def',character_id=456))
        value=fixture();value['character'].update(id=456,name='CharacterB')
        (self.inbox/'auto-1-456-20261103T000000Z-000001.json').write_bytes(encoded(value))
        observations,errors=self.store.restore(self.snapshot)
        self.assertFalse(errors)
        apply_names(self.snapshot,observations)
        self.assertEqual([c.display_name for c in self.snapshot.characters],['CharacterA','CharacterB'])
        self.assertEqual(observations['abc'].export.character_id,123)
        self.assertEqual(observations['def'].export.character_id,456)
