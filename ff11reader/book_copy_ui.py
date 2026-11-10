"""Book-copy selection using shared dialogs and application operations."""
import tkinter as tk
from tkinter import ttk

from . import dialogs
from .theme import BG
from .ui_actions import ActionButton
from .ui_tasks import background


def summary(plan):
    lines = [f'コピー元: {plan.source} / ブック {plan.source_book:02}',
             f'コピー先: {plan.destination} / ブック {plan.destination_book:02}',
             'ブック名・全200マクロ・参照装備セットをコピーします。',
             f'内容のあるマクロの上書き: {plan.overwritten_macros}件',
             '同じ番号へコピーする装備セット: ' + (', '.join(f'{n:03}' for n in plan.equipment_numbers) or 'なし')]
    if plan.affected_references:
        lines.append('上書きする装備セットを使用するコピー先の別ブック:')
        lines.extend(f'  ブック {r.book:02} / パレット {r.palette} / {r.bank.upper()} {r.key} / セット {r.number:03}'
                     for r in plan.affected_references)
    if plan.warnings:
        lines.extend(('', 'コピー先の参照確認:', *plan.warnings,
                      '装備の位置が一致しない枠は、コピー後に参照位置の補正または枠編集を行ってから書き戻してください。'))
    return '\n'.join(lines)


def open_book_copy(view):
    source = view.character
    if source is None:return
    destinations = [c for c in view.snapshot.characters if c.folder_id != source.folder_id]
    if not destinations:
        dialogs.showwarning('キャラ間ブックコピー', 'コピー先のキャラクターを読み込んでください。', parent=view.app)
        return
    try:view.macro_panel.apply_pending()
    except ValueError as exc:
        dialogs.showerror('マクロ入力', str(exc), parent=view.app)
        return
    window = tk.Toplevel(view.app, background=BG)
    window.title('別キャラへブックをコピー')
    window.geometry('660x380')
    ttk.Label(window, text=f'コピー元: {source.display_name or source.folder_id} [{source.folder_id}]', padding=12).pack(anchor='w')
    choices = {}
    for name, label in (('source_book', 'コピー元ブック'), ('destination', 'コピー先キャラクター'),
                        ('destination_book', 'コピー先ブック')):
        row = ttk.Frame(window, padding=(12, 6));row.pack(fill='x')
        ttk.Label(row, text=label, width=22).pack(side='left')
        choice = ttk.Combobox(row, state='readonly', width=42);choice.pack(side='left', fill='x', expand=True)
        choices[name] = choice
    source_books = sorted({m.book for m in source.macros})
    choices['source_book'].configure(values=[f'{n:02}  {source.books[n].display if n in source.books else "（名前未取得）"}' for n in source_books])
    if source_books:choices['source_book'].current(0)
    choices['destination'].configure(values=[f'{c.display_name or "名前未確認"} [{c.folder_id}]' for c in destinations])
    choices['destination'].current(0)
    target_books = []
    def update_books(event=None):
        target = destinations[choices['destination'].current()]
        target_books[:] = sorted({m.book for m in target.macros})
        choices['destination_book'].configure(values=[f'{n:02}  {target.books[n].display if n in target.books else "（名前未取得）"}' for n in target_books])
        choices['destination_book'].set('')
        if target_books:choices['destination_book'].current(0)
    choices['destination'].bind('<<ComboboxSelected>>', update_books)
    update_books()
    ttk.Label(window, text='参照装備セットは同じ番号へコピーします。次の画面で上書き内容を確認できます。',
              wraplength=600, padding=12).pack(anchor='w')
    def preview():
        if choices['source_book'].current() < 0 or choices['destination_book'].current() < 0:return
        target = destinations[choices['destination'].current()]
        try:
            plan = background(view.app, view.editor.prepare_book_copy, source.folder_id, target.folder_id,
                              source_books[choices['source_book'].current()], target_books[choices['destination_book'].current()])
        except (ValueError, OSError) as exc:
            dialogs.showerror('コピー内容の確認', str(exc), parent=window)
            return
        view.preview_edit(plan.edit, lambda:view.editor.copy_book(plan), window, summary=summary(plan))
    ActionButton(window, text='コピー内容を確認', busy=True, command=preview).pack(pady=12)
    dialogs.child_navigation(window)
    dialogs.fit_to_screen(window)
    window.copy_choices = choices
    window.preview_copy = preview
    return window
