from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch
from ff11reader import application, macro_saving
from ff11reader.domain import Character, Text
from ff11reader.editing import macro_key
from ff11reader.macro_save_proposal import replay_macro_proposal
from tests.property_support import isolated
from tests.test_manual_macro_saving import ManualFixture


class MacroSaveProposalTests(unittest.TestCase):
    def test_regenerated_plan_matches_full_replay_and_inputs_are_detached(self):
        with isolated() as base:
            fixture = ManualFixture(base, 'macro', 7, 2)
            fixture.set_line(b'/echo ' + bytes.fromhex('fd07010064fd'))
            fixture.edit_line('/say 【Robe0】')
            plan = fixture.preview()
            fresh = fixture.load()
            original = deepcopy(fresh)
            changes = {(c.address, c.line): c for f in plan.files for c in f.changes}
            before, after = replay_macro_proposal(fresh, 'abc', changes, {})
            full = deepcopy(fresh)
            def field(m, n, old):
                c = changes.get((macro_key(m), n))
                return Text(c.after, c.provenance.hex(), 'draft', c.tokens) if c else old
            full.characters[0].macros = [replace(m, title=field(m, 0, m.title),
                lines=tuple(field(m, n, t) for n, t in enumerate(m.lines, 1)))
                for m in full.characters[0].macros]
            self.assertEqual(macro_saving.prepare_macro_save(before, after, 'abc', 'all'),
                             macro_saving.prepare_macro_save(fresh, full, 'abc', 'all'))
            self.assertEqual(len(before.characters[0].macros), 1)
            before.items.clear()
            after.sources.clear()
            after.characters[0].inventory.clear()
            self.assertTrue(after.items)
            self.assertTrue(before.sources)
            self.assertEqual(fresh, original)

    def test_unrelated_values_are_not_copied_and_missing_address_is_rejected(self):
        class Unrelated:
            def __deepcopy__(self, memo):
                raise AssertionError('unrelated values copied')
        with isolated() as base:
            fixture = ManualFixture(base, 'macro', 7, 2)
            fixture.edit(title='New')
            plan = fixture.preview()
            fresh = fixture.load()
            fresh.characters.append(Character('def', books=Unrelated()))
            fresh.rank_augments = Unrelated()
            changes = {(c.address, c.line): c for f in plan.files for c in f.changes}
            before, after = replay_macro_proposal(fresh, 'abc', changes, {})
            self.assertEqual(len(before.characters), 1)
            self.assertEqual(before.characters[0].equipsets, [])
            self.assertEqual(macro_saving.prepare_macro_save(before, after, 'abc', 'all'), plan)
            with self.assertRaisesRegex(ValueError, '再読込結果'):
                replay_macro_proposal(fresh, 'abc', {((40, 10, 'alt', 10), 0):next(iter(changes.values()))}, {})

    def test_execution_still_reloads_and_rejects_changed_proposal(self):
        with isolated() as base:
            fixture = ManualFixture(base, 'macro', 7, 1)
            fixture.edit(title='New')
            plan = fixture.preview()
            fresh = fixture.load()
            address = plan.files[0].changes[0].address
            index = next(i for i, m in enumerate(fresh.characters[0].macros) if macro_key(m) == address)
            target = fresh.characters[0].macros[index]
            fresh.characters[0].macros[index] = replace(target, title=replace(target.title, display='changed'))
            original = fixture.bytes()
            with patch.object(application, 'load_snapshot', return_value=fresh) as reload:
                with self.assertRaises(ValueError):
                    macro_saving.execute_macro_save(plan, base/'backups')
                reload.assert_called_once()
            self.assertEqual(fixture.bytes(), original)
