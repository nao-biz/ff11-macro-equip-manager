import os
import tkinter as tk
import unittest
from unittest.mock import patch
from ff11reader.edit_interaction import EditInteraction


class InteractionTests(unittest.TestCase):
    def test_failed_commit_retains_original_and_stage(self):
        flow = EditInteraction(); flow.begin(2, 'before')
        def reject(*_): raise ValueError('invalid')
        with self.assertRaises(ValueError): flow.commit('draft', reject)
        self.assertEqual((flow.stage, flow.original), ('edit', 'before'))
        self.assertEqual(flow.cancel(), (2, 'before'))

    def test_candidate_cancel_is_one_level(self):
        flow = EditInteraction(); flow.begin(1, 'before'); flow.open_candidate()
        self.assertIsNone(flow.cancel())
        self.assertEqual(flow.stage, 'edit')
        self.assertEqual(flow.cancel(), (1, 'before'))

    def test_apply_reentry_is_rejected_and_failure_can_retry(self):
        flow = EditInteraction(); flow.begin(1, 'before')
        calls = []
        def apply(target, before, draft):
            calls.append((target, before, draft))
            with self.assertRaises(ValueError): flow.commit(draft, apply)
            with self.assertRaises(ValueError): flow.begin(2, 'other')
            with self.assertRaises(ValueError): flow.cancel()
            raise OSError('synthetic failure')
        with self.assertRaises(OSError): flow.commit('draft', apply)
        self.assertEqual(flow.stage, 'edit')
        self.assertEqual(flow.original, 'before')
        self.assertEqual(len(calls), 1)
        flow.commit('corrected', lambda *args: calls.append(args))
        self.assertEqual(flow.stage, 'select')
        self.assertEqual(calls[-1], (1, 'before', 'corrected'))


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION') == '1', 'Synthetic Tk checks')
class MockTests(unittest.TestCase):
    def setUp(self):
        from prototypes.interaction_mock import InteractionMock
        self.root = tk.Tk(); self.errors=[]
        self.root.report_callback_exception=lambda *e:self.errors.append(e)
        self.mock = InteractionMock(self.root); self.root.update(); self.root.focus_force()
        self.ime = patch('prototypes.interaction_mock.ime_composing', return_value=False)
        self.ime.start()

    def tearDown(self):
        self.root.destroy(); self.ime.stop()
        self.assertFalse(self.errors)

    def key(self, key):
        entry=self.mock.entries[self.mock.selected]
        entry.focus_force();self.root.update();entry.event_generate('<'+key+'>');self.root.update()

    def test_commit_undo_redo_and_cancel_keep_tokens(self):
        m=self.mock;before=m.values[1]
        self.key('Return');m.entries[1].insert('end',' <me>');self.key('Return')
        self.assertEqual(m.cursor,1);self.assertEqual(m.values[1].tokens,before.tokens)
        self.key('Control-z');self.assertEqual(m.values[1],before)
        self.key('Control-y');self.assertTrue(m.values[1].display.endswith(' <me>'))
        accepted=m.values[1]
        self.key('Return');m.entries[1].insert('end',' cancel');self.key('Escape')
        self.assertEqual(m.controllers[1].value,accepted);self.assertEqual(m.cursor,1)

    def test_error_retains_edit_and_nested_escape(self):
        m=self.mock;self.key('Return');m.entries[1].insert('end','x'*100);self.key('Return')
        self.assertEqual(m.flow.stage,'edit');self.assertEqual(m.cursor,0)
        self.assertIn('長すぎ',m.message.cget('text'))
        self.key('Escape');self.key('Return');self.key('Tab')
        self.assertEqual(m.flow.stage,'candidate')
        popup=m.controllers[1].popup;popup.event_generate('<Escape>');self.root.update()
        self.assertEqual(m.flow.stage,'edit')
        self.assertIs(self.root.focus_get(),m.entries[1])
        self.key('Escape');self.assertEqual(m.flow.stage,'select')

    def test_name_selection_and_mouse_does_not_lose_draft(self):
        m=self.mock;m.select(0);before=m.entries[0].get();m.entries[0].insert('end','x')
        self.assertEqual(m.entries[0].get(),before)
        self.key('Return');m.entries[0].insert('end','X');m.select(2)
        self.assertEqual(m.selected,0);self.assertEqual(m.flow.stage,'edit')
        self.key('Return');self.assertEqual(m.values[0].display,before+'X')
        self.assertEqual(m.cursor,1)

    def test_noop_and_redo_branch_after_new_commit(self):
        m=self.mock
        self.key('Return');self.key('Return')
        self.assertEqual(m.cursor,0);self.assertEqual(m.history,[])
        self.key('Return');m.entries[1].insert('end',' A');self.key('Return')
        self.key('Control-z')
        self.key('Return');m.entries[1].insert('end',' B');self.key('Return')
        self.assertEqual(m.cursor,1);self.assertEqual(len(m.history),1)
        accepted=m.values[1]
        self.key('Control-y');self.assertEqual(m.values[1],accepted)
        self.assertTrue(accepted.display.endswith(' B'))
