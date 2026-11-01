"""Synthetic domain tests for VIEW-004 placement (no filesystem or game access)."""
from copy import deepcopy
from dataclasses import replace
import random
import unittest

from ff11reader.domain import Character, Equipset, Macro, Slot, Text
from ff11reader.edit_values import SLOT_NAMES
from ff11reader.paste_placement import calculate_placement, assess_placement


def text(value=''):
    return Text(value, '', 'synthetic')


def macro(book=1, palette=1, bank='ctrl', key=1, title=''):
    return Macro(book, palette, bank, key, text(title), (text(),) * 6)


def palette(book, number):
    return [macro(book, number, bank, n) for bank in ('ctrl', 'alt') for n in range(1, 11)]


def equipment(number, title='', action='keep'):
    return Equipset(number, text(title), tuple(Slot(n, action, None, None, None, '') for n in SLOT_NAMES))


class PastePlacementTests(unittest.TestCase):
    def test_noncontiguous_macros_keep_holes_and_other_book(self):
        c = Character('a', macros=palette(1, 1) + palette(2, 5))
        # The unselected hole is occupied and must not block placement.
        c.macros[-5] = replace(c.macros[-5], title=text('Keep'))  # Alt 6
        before = deepcopy(c)
        result = assess_placement(c, 'macro', [(1, 1, 'ctrl', 3), (1, 1, 'ctrl', 1)], (2, 5, 'alt', 5))
        self.assertTrue(result.allowed)
        self.assertEqual([p.target for p in result.placements], [(2, 5, 'alt', 5), (2, 5, 'alt', 7)])
        self.assertEqual(c, before)

    def test_rectangle_origin_need_not_be_selected(self):
        result = calculate_placement('macro', [(1, 1, 'ctrl', 3), (1, 1, 'alt', 1)], (3, 8, 'ctrl', 5))
        self.assertEqual([p.target for p in result.placements], [(3, 8, 'ctrl', 7), (3, 8, 'alt', 5)])

    def test_linear_gaps_and_key_zero(self):
        for kind, selected, anchor, expected in (
            ('palette', [(1, 1), (1, 3)], (4, 5), [(4, 5), (4, 7)]),
            ('equipment', [(1,), (3,)], (10,), [(10,), (12,)]),
            ('macro', [(1, 1, 'ctrl', 8), (1, 1, 'ctrl', 10)], (2, 1, 'alt', 8),
             [(2, 1, 'alt', 8), (2, 1, 'alt', 10)]),
        ):
            with self.subTest(kind=kind):
                result = calculate_placement(kind, selected, anchor)
                self.assertEqual([p.target for p in result.placements], expected)

    def test_overflow_never_returns_partial_placements(self):
        cases = [
            ('macro', [(1, 1, 'ctrl', 1), (1, 1, 'ctrl', 3)], (1, 1, 'ctrl', 9)),
            ('macro', [(1, 1, 'ctrl', 1), (1, 1, 'alt', 1)], (1, 1, 'alt', 1)),
            ('palette', [(1, 1), (1, 3)], (40, 9)),
            ('equipment', [(1,), (3,)], (199,)),
        ]
        for kind, selected, anchor in cases:
            with self.subTest(kind=kind, anchor=anchor):
                result = calculate_placement(kind, selected, anchor)
                self.assertFalse(result.allowed)
                self.assertEqual(result.placements, ())
                self.assertEqual(result.issues[0].reason, 'out_of_range')
                self.assertEqual(result.issues[0].source, selected[-1])

    def test_invalid_selections_are_rejected(self):
        cases = [
            ('equipment', [], (1,)), ('equipment', [(True,)], (1,)),
            ('equipment', [(1,), (1,)], (2,)), ('equipment', [(1,)], (201,)),
            ('palette', [(1, 1), (2, 2)], (3, 1)), ('palette', [(41, 1)], (1, 1)),
            ('macro', [(1, 1, 'ctrl', 1), (1, 2, 'ctrl', 2)], (1, 3, 'ctrl', 1)),
            ('macro', [(1, 1, 'ctrl', 0)], (1, 1, 'ctrl', 1)),
            ('macro', [(1, 1, 'bad', 1)], (1, 1, 'ctrl', 1)),
            ('macro', [(1, 1)], (1, 1, 'ctrl', 1)),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                calculate_placement(*args)

    def test_macro_name_or_line_blocks_entire_selection(self):
        for filled in (replace(macro(key=7), title=text('Named')),
                       replace(macro(key=7), lines=(text('/echo hi'),) + (text(),) * 5)):
            c = Character('a', macros=palette(1, 1))
            c.macros[6] = filled
            result = assess_placement(c, 'macro', [(1, 1, 'ctrl', 1), (1, 1, 'ctrl', 3)], (1, 1, 'ctrl', 5))
            self.assertFalse(result.allowed)
            self.assertEqual(result.placements, ())
            self.assertEqual(result.issues[0].target, (1, 1, 'ctrl', 7))
            self.assertEqual(result.issues[0].reason, 'occupied')

    def test_equipment_empty_rule_and_overlap(self):
        for title, action in (('Named', 'keep'), ('', 'remove'), ('', 'equip'), ('', 'unknown')):
            c = Character('a', equipsets=[equipment(1), equipment(2, title, action)])
            result = assess_placement(c, 'equipment', [(1,)], (2,))
            self.assertEqual(result.issues[0].reason, 'occupied')
        c = Character('a', equipsets=[equipment(1, 'Source'), equipment(2)])
        self.assertTrue(assess_placement(c, 'equipment', [(1,)], (2,)).allowed)
        # Cutting does not empty the source before collision checking.
        self.assertEqual(assess_placement(c, 'equipment', [(1,)], (1,)).issues[0].reason, 'occupied')

    def test_missing_duplicate_and_truncated_values_are_unavailable(self):
        for values in ([], [equipment(2), equipment(2)], [replace(equipment(2), slots=())]):
            c = Character('a', equipsets=[equipment(1), *values])
            self.assertEqual(assess_placement(c, 'equipment', [(1,)], (2,)).issues[0].reason, 'unavailable')
        for values in ([], [macro(key=2), macro(key=2)], [replace(macro(key=2), lines=())]):
            c = Character('a', macros=[macro(), *values])
            self.assertEqual(assess_placement(c, 'macro', [(1, 1, 'ctrl', 1)], (1, 1, 'ctrl', 2)).issues[0].reason, 'unavailable')
        result = assess_placement(Character('a', equipsets=[equipment(2)]), 'equipment', [(1,)], (2,))
        self.assertEqual(result.issues[0].side, 'source')

    def test_palette_requires_all_twenty_and_reports_member(self):
        c = Character('a', macros=palette(1, 1) + palette(2, 3))
        self.assertTrue(assess_placement(c, 'palette', [(1, 1)], (2, 3)).allowed)
        c.macros[-1] = replace(c.macros[-1], title=text('Occupied'))
        result = assess_placement(c, 'palette', [(1, 1)], (2, 3))
        self.assertEqual(result.issues[0].member, (2, 3, 'alt', 10))
        c.macros.pop()
        self.assertEqual(assess_placement(c, 'palette', [(1, 1)], (2, 3)).issues[0].reason, 'unavailable')
        c.macros.pop(0)
        result = assess_placement(c, 'palette', [(1, 1)], (2, 3))
        self.assertEqual({i.side for i in result.issues}, {'source', 'target'})


class PlacementProperties(unittest.TestCase):
    def test_generated_translations_against_independent_coordinate_model(self):
        rng = random.Random(20261102)
        for kind, rows, columns in (('macro', 2, 10), ('palette', 1, 10), ('equipment', 1, 200)):
            for _ in range(150):
                selected = rng.sample([(r, c) for r in range(rows) for c in range(columns)], rng.randint(1, min(8, columns)))
                target = (rng.randrange(rows), rng.randrange(columns))
                def address(rc, book):
                    r, c = rc
                    if kind == 'macro':return (book, 1, ('ctrl', 'alt')[r], c + 1)
                    if kind == 'palette':return (book, c + 1)
                    return (c + 1,)
                request = [address(p, 1) for p in selected]
                before = deepcopy(request)
                expected = [(r - min(x[0] for x in selected) + target[0], c - min(x[1] for x in selected) + target[1]) for r, c in sorted(selected)]
                result = calculate_placement(kind, request, address(target, 2))
                self.assertEqual(result.allowed, all(r < rows and c < columns for r, c in expected))
                if result.allowed:
                    self.assertEqual([p.target for p in result.placements], [address(p, 2) for p in expected])
                    self.assertEqual(len({p.target for p in result.placements}), len(selected))
                    self.assertEqual(calculate_placement(kind, reversed(request), address(target, 2)), result)
                else:self.assertEqual(result.placements, ())
                self.assertEqual(request, before)

    def test_generated_collision_checks_are_atomic_and_pure(self):
        rng = random.Random(17)
        for _ in range(100):
            selected = sorted(rng.sample(range(1, 50), 5))
            targets = [100 + n - selected[0] for n in selected]
            blocked = rng.choice(targets)
            c = Character('a', equipsets=[equipment(n, 'Busy' if n == blocked else '') for n in range(1, 201)])
            before = deepcopy(c)
            result = assess_placement(c, 'equipment', [(n,) for n in selected], (100,))
            self.assertFalse(result.allowed)
            self.assertEqual(result.placements, ())
            self.assertEqual([i.target for i in result.issues], [(blocked,)])
            self.assertEqual(c, before)
