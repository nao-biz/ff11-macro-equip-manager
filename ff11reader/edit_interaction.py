"""UI-independent edit stages; application callbacks own validation and history."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class EditInteraction:
    target: Any = None
    original: Any = None
    stage: str = 'select'

    def begin(self, target, original):
        if self.stage != 'select':
            raise ValueError('現在の編集を確定または取消してください。')
        self.target, self.original, self.stage = target, original, 'edit'

    def open_candidate(self):
        if self.stage != 'edit':
            raise ValueError('内容編集中に候補を開いてください。')
        self.stage = 'candidate'

    def close_candidate(self):
        if self.stage == 'candidate':
            self.stage = 'edit'

    def commit(self, draft, apply: Callable):
        if self.stage != 'edit':
            raise ValueError('内容編集中に確定してください。')
        # The callback validates and publishes one atomic transaction.
        # On failure the original and edit stage remain available for correction.
        self.stage = 'applying'
        try:
            apply(self.target, self.original, draft)
        except Exception:
            self.stage = 'edit'
            raise
        self.stage = 'select'
        self.original = None
        return self.target

    def cancel(self):
        if self.stage == 'applying':
            raise ValueError('確定処理の完了を待ってください。')
        if self.stage == 'candidate':
            self.close_candidate()
            return None
        if self.stage != 'edit':
            return None
        restored = (self.target, self.original)
        self.stage = 'select'
        self.original = None
        return restored


class DraftHistory:
    """Undo within one input session, separate from published Editor history."""
    def __init__(self, original):
        self.values = [original]
        self.cursor = 0

    def observe(self, value):
        if value != self.values[self.cursor]:
            self.values[self.cursor + 1:] = [value]
            self.cursor += 1

    def step(self, direction):
        self.cursor = max(0, min(len(self.values)-1, self.cursor+direction))
        return self.values[self.cursor]
