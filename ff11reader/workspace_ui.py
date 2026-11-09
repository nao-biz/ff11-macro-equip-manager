"""Workspace composition; actions delegate to ReaderWindow and Editor."""
import tkinter as tk
from tkinter import ttk
from .theme import BG, PANEL, FG, MUTED, SELECT, ACCENT, BORDER, WARNING, ModeTabs, install
from .ui_actions import ActionButton
from .equipment_summary_ui import EquipmentSummary
from .macro_editor_ui import MacroPanel
from .item_properties_ui import ItemPropertyPanel


def build(view):
    app = view.app
    app.title('FF11 ワークスペース')
    app.geometry('1440x900')
    app.minsize(1320, 840)
    install(app)
    header = ttk.Frame(app, padding=(18, 6))
    header.pack(fill='x')
    ttk.Label(header, text='FF11 Macro & Equip', font=('Yu Gothic UI', 14, 'bold')).pack(side='left')
    toolbar = header
    ttk.Label(toolbar, text='キャラクター').pack(side='left', padx=(20, 8))
    view.character_choice = ttk.Combobox(toolbar, state='readonly', width=22, values=view.character_labels())
    view.character_choice.pack(side='left')
    view.character_choice.bind('<<ComboboxSelected>>', view.change_character)
    ActionButton(toolbar, busy=True, text='表示名を登録', command=view.rename).pack(side='left', padx=8)
    view.reload_button = ActionButton(toolbar, busy=True, busy_message='ゲームデータを読み込んでいます…',
                                     text='ゲームデータを再読み込み', command=view.reload_data,
                                     state='normal' if view.editor.root is not None else 'disabled')
    view.common_actions = ttk.Frame(app, padding=(18, 3))
    view.common_actions.pack(fill='x')
    view.mode = tk.StringVar(value='装備セット')
    view.tabs = ModeTabs(app, view.mode, view.change_mode)
    view.tabs.pack(fill='x')
    view.selection_status = ttk.Label(app, text='対象を選択してください。', style='Muted.TLabel', padding=(18, 3))
    view.selection_status.pack(fill='x')
    view.body = ttk.Panedwindow(app, orient='horizontal')
    view.body.pack(fill='both', expand=True, padx=12, pady=4)
    left = ttk.Frame(view.body, padding=6, width=150)
    center = view.center = ttk.Frame(view.body, padding=8)
    view.right_panel = ttk.Frame(view.body, padding=6, width=650)
    view.right_panel.pack_propagate(False)
    for panel, weight in ((left, 0), (center, 1), (view.right_panel, 0)):
        view.body.add(panel, weight=weight)
    view.nav_title = ttk.Label(left, font=('Yu Gothic UI', 11, 'bold'))
    view.nav_title.pack(anchor='w', pady=(0, 8))
    view.nav = tk.Listbox(left, width=17, activestyle='none', exportselection=False,
                         borderwidth=0, font=('Yu Gothic UI', 10), bg=PANEL, fg=FG,
                         highlightthickness=0, selectbackground=SELECT, selectforeground=ACCENT)
    view.nav_scroll = ttk.Scrollbar(left, command=view.nav.yview)
    view.nav.configure(yscrollcommand=view.nav_scroll.set)
    view.nav_scroll.pack(side='right', fill='y')
    view.nav.pack(fill='both', expand=True)
    view.nav.bind('<<ListboxSelect>>', view.select_navigation)
    view.nav.bind('<Return>',lambda e:view.enter_navigation())
    view.macro_tree = ttk.Treeview(left, show='tree', selectmode='extended', style='Macro.Treeview')
    view.macro_tree.column('#0', width=200, minwidth=170, stretch=True)
    view.macro_tree.tag_configure('empty', foreground=MUTED)
    view.macro_tree.tag_configure('cut', foreground=WARNING)
    view.macro_tree.configure(yscrollcommand=view.nav_scroll.set)
    view.macro_tree.bind('<<TreeviewSelect>>', view.select_macro_palette)
    view.macro_tree.bind('<Return>',lambda e:view.enter_navigation())
    view.macro_tree.bind('<<TreeviewOpen>>', view.open_macro_book)
    heading = ttk.Frame(center)
    heading.pack(fill='x')
    view.heading = ttk.Label(heading, font=('Yu Gothic UI', 13, 'bold'))
    view.heading.pack(side='left')
    view.subtitle = ttk.Label(center, style='Muted.TLabel', wraplength=650)
    view.subtitle.pack(anchor='w', pady=(4, 4))
    view.inventory_layout = tk.StringVar(value='リスト')
    view.inventory_query = tk.StringVar()
    view.inventory_switch = ttk.Frame(center)
    ttk.Label(view.inventory_switch, text='名前・種類ID').pack(side='left')
    ttk.Entry(view.inventory_switch, textvariable=view.inventory_query, width=18).pack(side='left', padx=6)
    for layout in ('パネル', 'リスト'):
        ttk.Radiobutton(view.inventory_switch, text=layout, value=layout, variable=view.inventory_layout,
                        command=view.switch_inventory_layout).pack(side='left', padx=4)
    view.inventory_query.trace_add('write', lambda *_: view.switch_inventory_layout())
    view.canvas_area = ttk.Frame(center)
    view.canvas_area.pack(fill='both', expand=True)
    view.canvas = tk.Canvas(view.canvas_area, bg=BG, highlightthickness=0, width=560)
    scroll = ttk.Scrollbar(view.canvas_area, command=view.canvas.yview)
    view.canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    view.canvas.pack(fill='both', expand=True)
    view.cards = tk.Frame(view.canvas, bg=BG)
    view.canvas_window = view.canvas.create_window(0, 0, window=view.cards, anchor='nw')
    view.cards.bind('<Configure>', lambda e: view.canvas.configure(scrollregion=view.canvas.bbox('all')))
    view.canvas.bind('<Configure>', lambda e: view.canvas.itemconfigure(view.canvas_window, width=e.width))
    view.canvas.bind('<MouseWheel>', lambda e: view.canvas.yview_scroll(-int(e.delta / 120), 'units'))
    view.macro_panel = MacroPanel(center, view)
    view.slot_edit_button = ActionButton(center, busy=True, text='選択枠を編集',
                                        command=view.edit_selected_slot, state='disabled')
    view.slot_edit_button.pack(anchor='w', pady=8)
    view.equipment_candidates_panel = ttk.Frame(center)
    hidden = ttk.Frame(app)
    entries = [
        ('links_button', 'マクロと装備セットの参照確認', view.show_macro_links),
        ('fix_button', '装備セットの参照位置を補正', view.preview_fixes),
        ('macro_fix_button', 'マクロの収納番号を確認・補正', view.show_macro_inventory),
        ('unused_button', 'ワードローブの未参照アイテム', view.show_unused_wardrobe),
        ('import_button', '個体情報を取り込む…', view.import_augments),
        ('move_button', '選択した装備セットを移動…', view.move_selected_equipment),
        ('equipment_name_button', '選択した装備セットの名前を編集', view.edit_selected_equipment_name),
        ('edit_button', '選択マクロを編集', view.edit_selected_macro),
        ('undo_button', 'Undo', view.undo_fix), ('redo_button', 'Redo', view.redo_edit),
        ('reset_button', '未保存の変更を破棄', view.reset_edits)]
    for name, text, command in entries:
        button = ActionButton(hidden, busy=True, text=text, command=command)
        setattr(view, name, button)
    # Shared actions are composed after save_button exists.
    view.side_content = ttk.Frame(view.right_panel)
    view.side_content.pack(fill='both', expand=True)
    right = view.side_content
    from .ui import BAGS
    view.equipment_summary = EquipmentSummary(view.right_panel, BAGS)
    view.inventory_properties_area = ttk.Frame(view.right_panel)
    inventory_actions = ttk.Frame(view.inventory_properties_area)
    inventory_actions.pack(side='bottom', fill='x', pady=(8, 0))
    view.inventory_compare_button = ActionButton(inventory_actions, text='装備セットで比較', busy=True,
                                                command=view.compare_inventory_item, state='disabled',
                                                style='Primary.TButton')
    view.inventory_compare_button.pack(side='right')
    view.inventory_details_button = ActionButton(inventory_actions, text='個体情報・参照先',
                                                command=view.show_evidence, state='disabled')
    view.inventory_details_button.pack(side='left')
    view.inventory_properties = ItemPropertyPanel(view.inventory_properties_area)
    view.inventory_properties.pack(fill='both', expand=True)
    view.detail_heading = ttk.Label(right, text='アイテム / 詳細', font=('Yu Gothic UI', 12, 'bold'))
    view.detail_heading.pack(anchor='w', pady=(0, 8))
    view.detail = tk.Text(right, width=34, height=8, wrap='word', font=('Yu Gothic UI', 10),
                          bg=PANEL, fg=FG, insertbackground=FG, selectbackground=SELECT,
                          relief='flat', padx=10, pady=10, state='disabled')
    view.detail.pack(fill='both', expand=True)
    view.detail.tag_configure('title', font=('Yu Gothic UI', 11, 'bold'), foreground=ACCENT)
    view.evidence = None
    view.details_button = ttk.Button(right, text='判定の詳細', command=view.show_evidence, state='disabled')
    view.details_button.pack(fill='x', pady=(8, 0))
    view.actions = ttk.Frame(right)
    view.actions.pack(fill='x', pady=6)
    view.candidate_menu = tk.Menu(app, tearoff=False, bg=PANEL, fg=FG, activebackground=SELECT)
    view.candidate_button = ttk.Menubutton(view.actions, text='候補を見る', menu=view.candidate_menu, state='disabled')
    view.candidate_button.pack(fill='x')
    view.legend = ttk.Frame(app, padding=(18, 2))
    view.legend.pack(fill='x')
    from .ui import ACTION_STYLE
    for label, _, color in ACTION_STYLE.values():
        if label:
            tk.Label(view.legend, text='● ' + label, fg=color, bg=BG).pack(side='left', padx=(0, 18))
    bottom = ttk.Frame(app, padding=(18, 8))
    bottom.pack(side='bottom',fill='x')
    view.footer = ttk.Label(bottom, text='対象を選択して、内容を確認・編集できます。', style='Muted.TLabel')
    view.footer.pack(side='left', fill='x', expand=True)
    view.draft_label = ttk.Label(bottom, style='Muted.TLabel')
    view.draft_label.pack(side='left', padx=8)
    view.save_button = ActionButton(bottom, busy=True, text='ゲームへ書き戻す…', style='Primary.TButton',
                                   command=view.preview_combined_save)
    view.save_button.pack(side='right', padx=(10, 0))
    from .common_actions_ui import build_common_actions
    build_common_actions(view)
    view.body.pack_forget()
    view.legend.pack_forget()
    view.legend.pack(side='bottom',fill='x')
    view.body.pack(fill='both',expand=True,padx=12,pady=4)
    view.active_slot = None
    view.slot_editor = None
    view.view_states = {}
    view.view_key = None
    app.protocol('WM_DELETE_WINDOW', view.close)
