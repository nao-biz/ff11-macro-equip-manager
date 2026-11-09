import unittest
from ff11reader import application
from ff11reader.combined_saving import prepare_combined_save
from ff11reader.dictionaries import resolve_token
from ff11reader.domain import Character, InventoryRow, Macro, Snapshot, Text, TextToken
from ff11reader.edit_application import Editor
from ff11reader.item_tokens import item_id_from_token
from ff11reader.save_inputs import copy_save_input, required_item_ids
from tests.test_equipment_slots import record
from tests.test_validation_loading import fixture, regenerated


class SaveInputTests(unittest.TestCase):
    def test_item_token_dependency_uses_the_same_legacy_forms_as_resolution(self):
        for language in (1, 2, 3, 4):
            for kind, hi, lo, expected in ((7, 0x12, 0x34, 0x1234), (9, 255, 100, 100),
                                           (10, 0x12, 255, 0x1200), (7, 255, 255, 65535)):
                payload = bytes((kind, language, hi, lo))
                self.assertEqual(item_id_from_token(payload), expected)
                self.assertEqual(resolve_token(payload, {}, {expected:{'name':'item'}}), 'item')
        for payload in (b'', bytes((2, 1, 1, 1)), bytes((7, 0, 1, 1)),
                        bytes((9, 1, 0, 100)), bytes((10, 1, 1, 0))):
            self.assertIsNone(item_id_from_token(payload))

    def test_raw_provenance_and_explicit_tokens_are_retained_without_copying_unrelated_items(self):
        class Unrelated:
            def __deepcopy__(self, memo): raise AssertionError('unrelated catalog copied')
        line = Text('【New】', '00fd0902ff64fd', 'draft', (TextToken(0, 5, '0A0112FF'),))
        macro = Macro(1, 1, 'ctrl', 1, Text('', '', 'cp932'), (line,)*6, 'fd07033412fd')
        character = Character('abc', macros=[macro], inventory=[InventoryRow(0, 1, 200)])
        expected = {100, 0x1200, 0x3412, 200}
        self.assertEqual(required_item_ids(character), expected)
        items = {key:{'name':str(key), 'metadata':{'nested':[key]}} for key in expected}
        items[999] = Unrelated()
        source = Snapshot('test', '', [character], items, [], [])
        first = copy_save_input(source, character)
        second = copy_save_input(source, character)
        self.assertEqual(set(first.items), expected)
        first.items[100]['metadata']['nested'].clear()
        self.assertEqual(second.items[100]['metadata']['nested'], [100])
        self.assertEqual(source.items[100]['metadata']['nested'], [100])
        self.assertNotIn(999, first.items)

    def test_unheld_new_item_token_is_on_both_sides_and_saves_with_the_full_plan(self):
        with fixture() as (f, root, master):
            master.write_bytes(master.read_bytes() + record(0x1200, 0, 'Unused') + record(0x6001, 0, 'Other'))
            original = application.load_snapshot(root)
            f.editor = Editor(original, f.base/'new-item.json')
            address = f.specs[0]['key']
            macro = f.editor.capture_save_session().read('abc', 'macros', address)
            lines = list(macro.lines)
            lines[f.specs[0]['line']-1] = Text('/echo 【Unused】', '', 'draft', (TextToken(6, 14, '0A0112FF'),))
            f.editor.apply(f.editor.prepare_macro_edit('abc', address, macro.title.display, lines))
            session = f.editor.capture_save_session()
            before, after, _ = session.save_inputs('abc', session.changes_since_save())
            self.assertIn(0x1200, before.items)
            self.assertEqual(before.items, after.items)
            self.assertNotIn(0x6001, before.items)
            plans = f.editor.prepare_writeback()
            self.assertEqual(plans[0], prepare_combined_save(session.saved, session.working, 'abc', ()))
            self.assertEqual(regenerated(original, plans[0].macro), plans[0].macro)
            f.editor.writeback(plans, f.base/'backups')
            self.assertFalse(f.editor.session.dirty)
            loaded = application.load_snapshot(root)
            saved = next(m for m in loaded.characters[0].macros if (m.book,m.palette,m.bank,m.key)==address)
            self.assertEqual(saved.lines[f.specs[0]['line']-1].display, '/echo 【Unused】')
