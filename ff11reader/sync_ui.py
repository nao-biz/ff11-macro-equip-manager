"""Process gate and automatic refresh; Tk and editor ownership stay on the UI side."""
from queue import Queue, Empty
from threading import Event, Lock, Thread
from .sync_observation import SyncObserver, Observation, SyncConflict
from .ui_tasks import TaskScreen, background, is_running
from .ui_operation_state import operations


class SyncMonitor:
    def __init__(self, view, *, observer=None, interval=500):
        self.view, self.app = view, view.app
        self.interval = interval
        self.screen = None
        self.busy = False
        self.applied = None
        self.conflict = None
        self.messages = Queue()
        self.stop = Event()
        self.lock = Lock()
        self.job = None
        if observer is None and view.editor.root is None:return
        self.observer = observer or SyncObserver(view.editor.root, view.snapshot.sources,
                                                view.editor.state_path.parent)
        self.app.bind('<Destroy>', self.destroyed, add='+')
        self.worker = Thread(target=self.observe, name='ff11-observer', daemon=True)
        self.worker.start()
        self.job = self.app.after(interval, self.poll)

    def observe(self):
        while not self.stop.is_set():
            try:
                with self.lock:observation = self.observer.sample()
            except Exception as exc:observation = Observation('error', message=str(exc))
            self.messages.put(observation)
            self.stop.wait(self.interval / 1000)

    def destroyed(self, event):
        if event.widget is self.app:
            self.stop.set()
            if self.job:self.app.after_cancel(self.job)

    def block(self, message):
        operations(self.app).set_game_blocked(True)
        if self.screen is None:
            self.screen = TaskScreen(self.app, message, on_close=self.close_window)
        else:self.screen.label.configure(text=message)

    def close_window(self):
        self.unblock()
        self.view.close()

    def unblock(self):
        if self.screen:self.screen.close();self.screen = None
        operations(self.app).set_game_blocked(False)

    def poll(self):
        self.job = None
        try:
            if not self.busy and not is_running(self.app):
                latest = None
                try:
                    while True:latest = self.messages.get_nowait()
                except Empty:pass
                if latest:self.accept(latest)
        finally:
            if not self.stop.is_set():self.job = self.app.after(self.interval, self.poll)

    def accept(self, observation):
        if getattr(self.view, 'closing', False):return
        if observation.state == 'running':
            self.block('ゲームの終了を待っています。\nFF11とPlayOnlineの終了後に自動で読み込みます。')
        elif observation.state != 'ready':
            message = ('保存データの更新完了を確認しています…' if observation.state == 'settling'
                       else 'ゲームと保存データを確認できません。自動で再確認します。\n' + observation.message)
            self.block(message)
        else:self.refresh(observation)

    def validate(self, observation):
        with self.lock:self.observer.validate(observation)

    def refresh(self, observation):
        if self.conflict == observation and self.view.editor.blocked:
            self.unblock();return
        if self.applied == observation:
            self.unblock();return
        self.busy = True
        self.unblock()
        operations(self.app).set_game_blocked(True)
        try:
            self.update(observation)
            self.applied = observation
            self.conflict = None
            operations(self.app).set_game_blocked(False)
        except SyncConflict as exc:
            self.conflict = observation
            self.view.editor.blocked = str(exc)
            self.view.update_edit_status()
            self.view.footer.configure(text=str(exc) + '「ゲームデータを再読み込み」で編集を破棄して切り替えられます。')
            operations(self.app).set_game_blocked(False)
        except (OSError, ValueError, RuntimeError) as exc:
            self.block('保存データを再確認しています…\n' + str(exc))
        finally:self.busy = False

    def update(self, observation):
        folder = self.view.character.folder_id if self.view.character else None
        known = {s['path']:s['sha256'] for s in self.view.snapshot.sources}
        data_changed = (self.applied.data != observation.data if self.applied else
                        any(dict(observation.data).get(p) != digest for p,digest in known.items()))
        if data_changed:
            background(self.app, self.view.editor.synchronize,
                       pending_input=self.view.macro_panel.has_pending(),
                       validate=lambda:self.validate(observation), message='最新のゲームデータを読み込んでいます…')
            self.view.snapshot = background(self.app, self.view.editor.snapshot)
            self.view.photos.clear()
            if self.conflict:self.view.editor.blocked = None
        else:background(self.app, self.validate, observation, message='保存データを確認しています…')
        errors = self.view.restore_augments(notify=False)
        background(self.app, self.validate, observation, message='更新後の保存データを確認しています…')
        self.view.character_choice.configure(values=self.view.character_labels())
        if self.view.snapshot.characters:
            index = next((i for i,c in enumerate(self.view.snapshot.characters) if c.folder_id == folder), 0)
            self.view.character_choice.current(index)
        else:
            self.view.character_choice.set('');self.view.clear_cards();self.view.nav.delete(0,'end')
            self.view.macro_tree.delete(*self.view.macro_tree.get_children())
            self.view.show_detail('キャラクターなし','読み取れたキャラクターフォルダはありません。')
        self.view.change_mode()
        self.view.update_edit_status()
        if not errors:self.view.footer.configure(text='ゲームの保存データを自動で確認しました。')
