"""Root-owned UI operation registration and exclusive execution state."""


class OperationState:
    def __init__(self, root):
        self.root = root
        self._busy = None
        self._runner = None
        self._running = False
        self._game_blocked = False

    def busy(self, factory):
        if self._busy is None:
            self._busy = factory(self.root)
        return self._busy

    def runner(self, factory):
        if self._runner is None:
            self._runner = factory(self.root)
        return self._runner

    @property
    def running(self):
        return self._running

    @property
    def blocked(self):
        return self._running or self._game_blocked

    @property
    def game_blocked(self):
        return self._game_blocked

    def set_game_blocked(self, blocked):
        self._game_blocked = blocked

    def start_task(self):
        if self._running:
            raise RuntimeError('別の処理を実行中です。')
        self._running = True

    def finish_task(self):
        self._running = False


def operations(widget):
    root = widget._root()
    state = getattr(root, '_ff11_operations', None)
    if state is None:
        state = OperationState(root)
        setattr(root, '_ff11_operations', state)
    return state
