import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ff11reader.windower_settings import WindowerSettings
from tests import test_auto_augments as auto_cases


def make_windower(folder):
    folder.mkdir(parents=True)
    (folder/'Windower.exe').write_bytes(b'synthetic')
    return folder


class WindowerSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.settings = WindowerSettings(self.base/'settings.json')

    def test_first_save_restart_and_change_without_addon(self):
        self.assertIsNone(self.settings.read())
        first = make_windower(self.base/'日本語 Windower')
        self.settings.save(first)
        restored = WindowerSettings(self.settings.path)
        self.assertEqual(restored.read(), first.resolve())
        self.assertEqual(restored.inbox(), first.resolve()/'addons/ff11export/data')
        self.assertTrue((first/'addons/ff11export/ff11export.lua').is_file())
        self.assertIn(b'lua load ff11export', (first/'scripts/init.txt').read_bytes())
        second = make_windower(self.base/'Moved')
        restored.save(second)
        self.assertEqual(self.settings.read(), second.resolve())

    def test_invalid_and_failed_save_preserve_previous(self):
        first = make_windower(self.base/'first')
        self.settings.save(first)
        before = self.settings.path.read_bytes()
        for invalid in ('', self.base, first/'Windower.exe', self.base/'missing'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.settings.save(invalid)
            self.assertEqual(self.settings.path.read_bytes(), before)
        second = make_windower(self.base/'second')
        with patch('ff11reader.augment_sources.os.fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.settings.save(second)
        self.assertEqual(self.settings.path.read_bytes(), before)
        self.assertFalse(list(self.base.glob('*.tmp')))

    def test_corrupt_configuration_is_not_unconfigured(self):
        for value in (b'broken', b'x'*16385, b'[]', json.dumps(dict(
                format='ff11-windower-settings',version=True,folder=str(self.base))).encode()):
            self.settings.path.write_bytes(value)
            with self.assertRaises(ValueError): self.settings.read()


class WindowerInboxTests(unittest.TestCase):
    setUp = auto_cases.AutoImportTests.setUp
    publish = auto_cases.AutoImportTests.publish
    def test_changed_location_keeps_binding_and_uses_new_inbox(self):
        self.publish()
        self.store.restore(self.snapshot)
        binding = self.store.sources.path.read_bytes()
        root = make_windower(self.base/'Windower')
        self.inbox = root/'addons/ff11export/data'
        self.inbox.mkdir(parents=True)
        self.publish('2026-11-04T00:00:00Z', 'Moved')
        self.store.settings.save(root)
        # An installed addon creates its data directory only when it exports.
        result, errors = self.store.restore(self.snapshot)
        self.assertFalse(errors)
        self.assertEqual(result['abc'].export.character_name, 'Moved')
        self.assertEqual(self.store.sources.path.read_bytes(), binding)
        self.assertEqual(self.snapshot.characters[0].display_name, 'Manual')
        self.publish('2026-11-05T00:00:00Z', 'Wrong', id=999)
        previous, errors = self.store.restore(self.snapshot)
        self.assertIn('abc', errors)
        self.assertEqual(previous, result)

    def test_missing_or_corrupt_new_location_keeps_saved_export(self):
        self.publish()
        previous, _ = self.store.restore(self.snapshot)
        root = make_windower(self.base/'Windower')
        self.store.settings.save(root)
        result, errors = self.store.restore(self.snapshot)
        self.assertEqual(result, previous)
        self.assertIn('abc', errors)
        self.store.settings.path.write_bytes(b'broken')
        result, errors = self.store.restore(self.snapshot)
        self.assertEqual(result, previous)
        self.assertIn('abc', errors)
