import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ff11reader import addon_installer as installer
from ff11reader.windower_settings import WindowerSettings
from tests.test_windower_settings import make_windower


def contents(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = make_windower(self.base/'Windower')
        self.settings = WindowerSettings(self.base/'app/settings.json')
        self.addon = self.root/'addons/ff11export'
        self.addon.mkdir(parents=True)
        (self.addon/'data').mkdir()
        (self.addon/'data/export.json').write_bytes(b'keep export')
        (self.addon/'observe-login.enabled').write_bytes(b'keep optional diagnostic')
        (self.root/'scripts').mkdir()
        self.init = self.root/'scripts/init.txt'
        self.original_init = '# 日本語設定\r\nlua l other\r\n'.encode('cp932')
        self.init.write_bytes(self.original_init)

    def test_install_completion_receipt_and_same_version_skip_after_restart(self):
        before = contents(self.root)
        self.settings.save(self.root)
        files, receipt = installer.bundled()
        for name, data in files.items(): self.assertEqual((self.addon/name).read_bytes(), data)
        self.assertEqual(self.init.read_bytes(), self.original_init+b'lua load ff11export\r\n')
        for name, data in before.items():
            if name != 'scripts/init.txt': self.assertEqual((self.root/name).read_bytes(), data)
        config = json.loads(self.settings.path.read_bytes())
        self.assertEqual(config['deployment'], receipt)
        originals = list((self.base/'app/windower-backups').glob('*/scripts/init.txt'))
        self.assertEqual([p.read_bytes() for p in originals], [self.original_init])
        stamps = {p: p.stat().st_mtime_ns for p in self.base.rglob('*') if p.is_file()}
        restored = WindowerSettings(self.settings.path)
        with patch.object(installer, 'install', side_effect=AssertionError('Repeated deployment')):
            restored.save(self.root)
            self.assertEqual(restored.read(), self.root)
            restored.inbox()
        self.assertEqual(stamps, {p:p.stat().st_mtime_ns for p in stamps})

    def test_existing_identical_install_is_adopted_without_target_writes(self):
        files, _ = installer.bundled()
        for name, data in files.items(): (self.addon/name).write_bytes(data)
        self.init.write_bytes(b'\xef\xbb\xbflua l ff11export\n')
        with patch.object(installer, 'replace_bytes', side_effect=AssertionError('Unnecessary write')):
            self.settings.save(self.root)
        self.assertTrue(json.loads(self.settings.path.read_bytes())['deployment']['completed'])
        self.assertFalse((self.base/'app/windower-backups').exists())

    def test_bundle_content_update_and_folder_change(self):
        self.settings.save(self.root)
        old = json.loads(self.settings.path.read_bytes())
        bundle = self.base/'bundle'; bundle.mkdir()
        for name, data in installer.bundled()[0].items(): (bundle/name).write_bytes(data)
        target = self.addon/'export_core.lua'
        original = target.read_bytes()
        (bundle/'export_core.lua').write_bytes(original+b'\n-- new bundle content\n')
        init_stamp = self.init.stat().st_mtime_ns
        with patch.object(installer, 'BUNDLE', bundle): self.settings.save(self.root)
        new = json.loads(self.settings.path.read_bytes())
        self.assertNotEqual(old['deployment']['bundle_sha256'], new['deployment']['bundle_sha256'])
        self.assertEqual(old['deployment']['addon_version'], new['deployment']['addon_version'])
        self.assertEqual(target.read_bytes(), (bundle/'export_core.lua').read_bytes())
        self.assertEqual(init_stamp, self.init.stat().st_mtime_ns)
        backups = list((self.base/'app/windower-backups').glob('*/addons/ff11export/export_core.lua'))
        self.assertEqual([p.read_bytes() for p in backups], [original])
        other = make_windower(self.base/'other')
        first = contents(self.root)
        self.settings.save(other)
        self.assertEqual(first, contents(self.root))
        self.assertEqual(self.settings.read(), other)
        self.assertTrue((other/'addons/ff11export/ff11export.lua').is_file())

    def test_old_config_migrates_only_on_explicit_save(self):
        self.settings.path.parent.mkdir()
        old = dict(format='ff11-windower-settings', version=1, folder=str(self.root))
        self.settings.path.write_text(json.dumps(old), encoding='utf-8')
        before = contents(self.root)
        self.assertEqual(self.settings.read(), self.root)
        self.assertEqual(contents(self.root), before)
        self.settings.save(self.root)
        self.assertEqual(json.loads(self.settings.path.read_bytes())['version'], 2)

    def test_config_save_failure_restores_targets_and_retry_succeeds(self):
        (self.addon/'ff11export.lua').write_bytes(b'old addon')
        before = contents(self.root)
        with patch('ff11reader.windower_settings.atomic_json', side_effect=OSError('config failure')):
            with self.assertRaisesRegex(OSError, 'config failure'): self.settings.save(self.root)
        self.assertEqual(contents(self.root), before)
        self.assertFalse(self.settings.path.exists())
        self.settings.save(self.root)
        self.assertTrue(json.loads(self.settings.path.read_bytes())['deployment']['completed'])

    def test_middle_write_failure_rolls_back_and_keeps_old_config(self):
        self.settings.save(self.root)
        old_config = self.settings.path.read_bytes()
        other = make_windower(self.base/'other')
        before = contents(other)
        real = installer.replace_bytes
        def fail(path, data):
            if path.name == 'auto_export.lua': raise OSError('write failure')
            real(path, data)
        with patch.object(installer, 'replace_bytes', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'write failure'): self.settings.save(other)
        self.assertEqual(contents(other), before)
        self.assertEqual(self.settings.path.read_bytes(), old_config)

    def test_unsupported_init_and_backup_failure_leave_targets_unchanged(self):
        self.init.write_bytes('lua l other'.encode('utf-16'))
        before = contents(self.root)
        with self.assertRaisesRegex(ValueError, '文字コード'): self.settings.save(self.root)
        self.assertEqual(contents(self.root), before)
        self.init.write_bytes(self.original_init)
        before = contents(self.root)
        with patch.object(installer, 'backup_changes', side_effect=OSError('backup failure')):
            with self.assertRaises(OSError): self.settings.save(self.root)
        self.assertEqual(contents(self.root), before)
        self.assertFalse(self.settings.path.exists())

    def test_rollback_failure_reports_backup_and_leaves_no_completion(self):
        (self.addon/'ff11export.lua').write_bytes(b'old addon')
        real = installer.replace_bytes
        def fail(path, data):
            if path.name == 'export_core.lua' or data == b'old addon':
                raise OSError('synthetic I/O failure')
            real(path, data)
        with patch.object(installer, 'replace_bytes', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'バックアップ:'):
                self.settings.save(self.root)
        backups = list((self.base/'app/windower-backups').glob('*/addons/ff11export/ff11export.lua'))
        self.assertEqual([p.read_bytes() for p in backups], [b'old addon'])
        self.assertFalse(self.settings.path.exists())

    def test_link_outside_selected_folder_is_rejected(self):
        outside = self.base/'external-init.txt'; outside.write_bytes(b'outside')
        original_resolve = Path.resolve
        def resolve(path, *args, **kwargs):
            return outside if path == self.init else original_resolve(path, *args, **kwargs)
        before = contents(self.root)
        with patch.object(Path, 'resolve', resolve):
            with self.assertRaisesRegex(ValueError, 'フォルダ外'): self.settings.save(self.root)
        self.assertEqual(contents(self.root), before)
        self.assertEqual(outside.read_bytes(), b'outside')


class StartupCommandTests(unittest.TestCase):
    def test_active_command_duplicates_comments_and_line_endings(self):
        for existing in (b'lua load ff11export', b' LUA L FF11EXPORT \r\n',
                         b'\xef\xbb\xbflua load "ff11export"\n',
                         b'lua l other; lua load ff11export // comment\n'):
            with self.subTest(existing=existing):
                self.assertEqual(installer.startup_bytes(existing), existing)
        for original, newline in ((b'',b'\r\n'),(b'lua l other\n',b'\n'),
                                  (b'# lua load ff11export\r\n',b'\r\n'),
                                  (b'// lua load ff11export\n',b'\n'),
                                  (b'lua load ff11export_extra',b'\r\n')):
            with self.subTest(original=original):
                updated = installer.startup_bytes(original)
                self.assertTrue(updated.startswith(original))
                self.assertTrue(updated.endswith(b'lua load ff11export'+newline))
                self.assertEqual(installer.startup_bytes(updated), updated)
