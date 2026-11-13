"""Pure macro planning decisions, independent of loading and save execution."""
from copy import deepcopy
from dataclasses import replace
import unittest
from ff11reader.codecs import text
from ff11reader.domain import Character, Macro
from ff11reader.macro_save_changes import needs_dictionary, collect_changes, macro_changes


def field(value, width=61):
    raw = value + b'\0' + b'Z' * (width-len(value)-1)
    return text(raw)


class MacroSaveChangesTests(unittest.TestCase):
    def setUp(self):
        self.macro = Macro(1, 1, 'ctrl', 1, field(b'Old', 10), (field(b'/echo old'),) * 6)

    def test_plain_name_and_line_changes_need_no_dictionary(self):
        edited = replace(self.macro, title=replace(self.macro.title, display='New'))
        before = Character('abc', macros=[self.macro])
        after = Character('abc', macros=[edited])
        snapshot = deepcopy((before, after))
        self.assertFalse(needs_dictionary(before, after, 'all'))
        grouped, deferred, bases = collect_changes(before, after, 'all', lambda _:None, {})
        self.assertEqual(deferred, [])
        self.assertEqual(bases, {})
        self.assertEqual(tuple(grouped), (0,))
        self.assertEqual(grouped[0][0].line, 0)
        self.assertEqual(grouped[0][0].replacement, b'New\0ZZZZZZ')
        self.assertEqual((before, after), snapshot)

    def test_fix_scope_preserves_manual_changes_as_deferred(self):
        edited = replace(self.macro, title=replace(self.macro.title, display='New'),
                         lines=(replace(self.macro.lines[0], display='/say new'),) + self.macro.lines[1:])
        changes, deferred, base = macro_changes(self.macro, edited, 'storage-fix', lambda _:None, {})
        self.assertEqual(changes, ())
        self.assertEqual(base, b'')
        self.assertEqual(len(deferred), 2)
        self.assertTrue(deferred[0].target.endswith('名前'))
        self.assertTrue(deferred[1].target.endswith('1行目'))

    def test_unchanged_relocated_provenance_does_not_add_dictionary_or_base(self):
        token_line = field(bytes.fromhex('fd07010064fd'))
        before = replace(self.macro, lines=(token_line,) + self.macro.lines[1:], raw_hex=bytes(380).hex())
        after = replace(before, raw_hex=(b'X' * 380).hex())
        self.assertFalse(needs_dictionary(Character('abc', macros=[before]), Character('abc', macros=[after]), 'all'))
        self.assertEqual(macro_changes(before, after, 'all', lambda _:None, {}), ((), (), b''))

    def test_encoding_error_identifies_macro_and_field(self):
        after = replace(self.macro, title=replace(self.macro.title, display='123456789'))
        with self.assertRaisesRegex(ValueError, 'ブック 01.*CTRL 1 / 名前.*8バイト'):
            macro_changes(self.macro, after, 'all', lambda _:None, {})
