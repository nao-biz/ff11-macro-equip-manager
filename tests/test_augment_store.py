import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from ff11reader.augment_store import AugmentStore
from ff11reader.augment_import import parse
from ff11reader.augment_sources import AugmentSource
from ff11reader.domain import Snapshot
from tests.test_augment_import import fixture, encoded, character

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.store=AugmentStore(self.directory/'observations')
        self.export=parse(encoded(fixture()))
        self.snapshot=Snapshot('test','now',[character()],{},[],[],installation_key='installation')
        for folder in ('abc','def'):
            self.store.sources.register(AugmentSource('installation',folder,123,1,str(self.directory),'synthetic observation'))
    def test_restart_and_reconcile_without_original_export(self):
        before=copy.deepcopy(self.snapshot)
        self.store.save('installation','abc',self.export)
        reopened=AugmentStore(self.directory/'observations')
        observations,errors=reopened.restore(self.snapshot)
        self.assertFalse(errors)
        self.assertEqual(observations['abc'].export,self.export)
        self.assertEqual(observations['abc'].item(self.snapshot.characters[0].inventory[0]).path,'B')
        self.assertEqual(self.snapshot,before)
        self.snapshot.characters[0].inventory[0]=replace(self.snapshot.characters[0].inventory[0],index=2)
        observations,errors=reopened.restore(self.snapshot)
        self.assertNotIn(12,observations['abc'].accepted_bags)
        self.assertIsNone(observations['abc'].item(self.snapshot.characters[0].inventory[1]))
        self.assertEqual(reopened.load('installation','abc'),self.export)
    def test_character_and_installation_isolation(self):
        self.store.save('installation','abc',self.export)
        self.assertIsNone(self.store.load('other','abc'))
        self.assertIsNone(self.store.load('installation','def'))
        data=self.store.path('installation','abc').read_bytes()
        self.store.path('installation','def').write_bytes(data)
        with self.assertRaises(ValueError):self.store.load('installation','def')
    def test_failed_replace_or_fsync_preserves_previous(self):
        self.store.save('installation','abc',self.export)
        old=self.store.path('installation','abc').read_bytes()
        newer=replace(self.export,captured_at='2026-11-04T00:00:00Z')
        for fault in (patch.object(Path,'replace',side_effect=OSError('replace failed')),patch('ff11reader.augment_sources.os.fsync',side_effect=OSError('fsync failed'))):
            with fault,self.assertRaises(OSError):self.store.save('installation','abc',newer)
            self.assertEqual(self.store.path('installation','abc').read_bytes(),old)
            self.assertEqual(list(self.store.directory.glob('*.tmp')),[])
        self.store.save('installation','abc',newer)
        self.assertEqual(self.store.load('installation','abc'),newer)
    def test_corrupt_character_does_not_block_others(self):
        self.store.save('installation','abc',self.export)
        self.store.save('installation','def',self.export)
        self.snapshot.characters.append(replace(character(),folder_id='def'))
        path=self.store.path('installation','abc');path.write_bytes(b'broken')
        observations,errors=self.store.restore(self.snapshot)
        self.assertEqual(set(observations),{'def'})
        self.assertEqual(set(errors),{'abc'})
        self.assertEqual(path.read_bytes(),b'broken')
