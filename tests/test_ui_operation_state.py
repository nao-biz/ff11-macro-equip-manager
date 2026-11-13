import unittest
from ff11reader.ui_operation_state import OperationState


class OperationStateTests(unittest.TestCase):
    def test_task_exclusivity_and_game_gate_have_independent_lifetimes(self):
        state = OperationState(object())
        state.set_game_blocked(True)
        state.start_task()  # Automatic refresh is allowed while user actions are blocked.
        with self.assertRaisesRegex(RuntimeError, '実行中'):
            state.start_task()
        state.finish_task()
        self.assertFalse(state.running)
        self.assertTrue(state.blocked)
        state.set_game_blocked(False)
        self.assertFalse(state.blocked)

    def test_registration_is_lazy_and_root_local(self):
        root = object()
        state, other = OperationState(root), OperationState(object())
        calls = []
        def factory(owner):
            calls.append(owner)
            return object()
        self.assertFalse(state.blocked)
        busy, runner = state.busy(factory), state.runner(factory)
        self.assertIs(state.busy(factory), busy)
        self.assertIs(state.runner(factory), runner)
        self.assertEqual(calls, [root, root])
        state.start_task()
        self.assertFalse(other.running)

    def test_failed_registration_can_be_retried(self):
        state = OperationState(object())
        def fail(root):
            raise RuntimeError('registration failed')
        with self.assertRaisesRegex(RuntimeError, 'registration'):
            state.runner(fail)
        runner = object()
        self.assertIs(state.runner(lambda root:runner), runner)
