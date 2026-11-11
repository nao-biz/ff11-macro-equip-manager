"""Folder selection using the shared application modal and worker boundary."""
from tkinter import filedialog, ttk
from . import dialogs
from .ui_tasks import background


class FolderDialog(dialogs.Modal):
    def __init__(self, parent, initial='', *, first=False):
        super().__init__(parent, '設定 — Windowerフォルダ',
                         'Windower.exeがあるフォルダを選択してください。\n'
                         'その中の addons\\ff11export\\data からExportを自動で取り込みます。\n'
                         '保存するとアドオンを配置し、Windower起動時の自動ロードを設定します。\n'
                         '配置済みの同じ版は再配置せず、更新する既存ファイルはバックアップします。', 'input', str(initial))
        self.ok_button.configure(text='保存')
        self.cancel_button.configure(text='あとで設定' if first else '取消')
        self.browse_button = ttk.Button(self.bar, text='フォルダを選択…', command=self.browse)
        self.browse_button.pack(side='left', padx=8)
        self.focusables.append(self.browse_button)
        self.browse_button.bind('<Return>', lambda e: (self.browse(), 'break')[1])
        self.browse_button.bind('<Escape>', self.cancel)
        self.browse_button.bind('<Tab>', lambda e: self.cycle(1))
        self.browse_button.bind('<Shift-Tab>', lambda e: self.cycle(-1))

    def browse(self):
        folder = filedialog.askdirectory(parent=self.parent, title='Windowerフォルダを選択',
                                         initialdir=self.entry.get() or None, mustexist=True)
        if folder:
            self.entry.delete(0, 'end')
            self.entry.insert(0, folder)
        self.entry.focus_set()


def configure(parent, settings, *, first=False):
    try:
        initial = background(parent, settings.read) or ''
    except (OSError, ValueError) as exc:
        dialogs.showerror('Windower設定', str(exc), parent=parent)
        initial = ''
    if first and initial:
        return False
    while True:
        folder = FolderDialog(parent, initial, first=first).wait()
        if folder is None:
            return False
        try:
            background(parent, settings.save, folder, message='アドオンと自動ロードを設定しています…')
            return True
        except (OSError, ValueError) as exc:
            dialogs.showerror('Windower設定を保存できませんでした', str(exc), parent=parent)
            initial = folder
