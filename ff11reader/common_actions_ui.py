"""Purpose-based shared actions, independent of the displayed workspace tab."""
import tkinter as tk
from tkinter import ttk
from .theme import PANEL, FG, SELECT


def build_common_actions(view):
    groups = {
        '編集': [('copy_book_button', '別キャラへブックをコピー…'),
               ('move_button', '選択した装備セットを移動…'),
               ('equipment_name_button', '選択した装備セットの名前を編集'),
               ('edit_button', '選択マクロを編集'), ('undo_button', 'Undo'),
               ('redo_button', 'Redo'),
               ('clear_character_button', '現在のキャラのマクロ・装備セットを全消去…'),
               ('reset_button', '全キャラの未保存変更を破棄…')],
        'チェック': [('fix_button', '装備セットの参照位置をチェック…'),
                 ('macro_fix_button', 'マクロの収納参照をチェック…'),
                 ('links_button', 'マクロと装備セットの参照をチェック…'),
                 ('unused_button', '未参照アイテムを確認…')],
        '取り込み・再読込': [('import_button', '現在のキャラへ個体情報を取り込む…'),
                         ('reload_button', '全キャラのゲームデータを再読み込み…')],
        '書き戻し': [('save_button', '全キャラの変更をゲームへ書き戻す…')],
    }
    view.common_menus = {}
    view.common_menu_buttons = {}
    for name, actions in groups.items():
        menu = tk.Menu(view.common_actions, tearoff=False, bg=PANEL, fg=FG, activebackground=SELECT)
        bindings = []
        for attribute, label in actions:
            button = getattr(view, attribute)
            menu.add_command(label=label, command=button.invoke)
            bindings.append((menu.index('end'), button))
        def sync(menu=menu, bindings=bindings):
            for index, button in bindings:
                menu.entryconfigure(index, state='disabled' if button.instate(['disabled']) else 'normal')
        menu.configure(postcommand=sync)
        control = ttk.Menubutton(view.common_actions, text=name+' ▾', menu=menu)
        control.pack(side='left', padx=(0, 12))
        view.common_menus[name] = menu
        view.common_menu_buttons[name] = control
    view.common_scope = ttk.Label(view.common_actions, style='Muted.TLabel')
    view.common_scope.pack(side='left', padx=10)
    ttk.Label(view.common_actions, text='対象編集はタブ内で選択', style='Muted.TLabel').pack(side='right')
