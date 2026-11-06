"""Remember view positions by character and tab, separate from edit history."""


def remember(view):
    view.macro_panel.capture()
    if view.view_key is None:
        return
    mode = view.view_key[1]
    selected = view.selected
    if mode == '装備セット':
        selected = getattr(selected, 'number', None)
    nav = view.macro_tree if mode == 'マクロ' else view.nav
    commands = view.commands
    view.view_states[view.view_key] = dict(
        selected=selected, macro=view.active_macro, slot=view.active_slot,
        inventory=getattr(view,'active_inventory',None),
        nav_y=nav.yview()[0], canvas_y=view.canvas.yview()[0],
        selection=(commands.kind, set(commands.selection), commands.anchor, commands.focus),
        candidate=view.slot_editor.input_state() if view.slot_editor is not None else None)


def restore(view, state):
    mode = view.mode.get()
    if mode == 'マクロ' and isinstance(view.selected, tuple):
        from .editing import macro_key
        macros = [m for m in view.character.macros if (m.book, m.palette) == view.selected]
        macro = next((m for m in macros if macro_key(m) == state.get('macro')), None)
        if macro is not None:
            view.inspect_macro(macro)
    elif mode == '装備セット' and view.selected is not None:
        slot = next((s for s in view.selected.slots if s.name == state.get('slot')), None)
        if slot is not None:
            view.inspect_slot(slot)
            if state.get('candidate'):
                view.edit_selected_slot()
                if view.slot_editor:view.slot_editor.restore_input(state['candidate'])
    elif mode=='インベントリ' and state.get('inventory') in view.card_widgets:
        row=next((r for r in view.character.inventory if r.container==view.selected and r.index==state['inventory']),None)
        if row:view.activate_card(view.card_widgets[row.index],lambda:view.inspect_inventory(row))
    if state.get('selection'):
        kind, selected, anchor, focus = state['selection']
        view.commands.kind, view.commands.selection = kind, set(selected)
        view.commands.anchor, view.commands.focus = anchor, focus
        view.commands.paint()
    view.app.update_idletasks()
    if mode != 'マクロ':
        # Panedwindow otherwise retains the previous tab's sash allocation.
        shift = view.right_panel.winfo_width() - view.right_panel.winfo_reqwidth()
        view.body.sashpos(1, view.body.sashpos(1) + shift)
    (view.macro_tree if mode == 'マクロ' else view.nav).yview_moveto(state.get('nav_y', 0))
    view.canvas.yview_moveto(state.get('canvas_y', 0))


def layout(view):
    """Keep the same outer workspace while giving macro input the full width."""
    macro=view.mode.get()=='マクロ'
    equipment=view.mode.get()=='装備セット'
    view.equipment_candidates_panel.pack_forget()
    view.slot_edit_button.pack_forget()
    view.selection_status.pack_forget()
    if not equipment:view.selection_status.pack(fill='x',after=view.tabs)
    right=str(view.right_panel)
    if macro:
        if right in view.body.panes():view.body.forget(view.right_panel)
        view.canvas.configure(height=170)
        view.canvas_area.pack_configure(fill='x',expand=False)
        view.legend.pack_forget()
    else:
        if right not in view.body.panes():view.body.add(view.right_panel,weight=1)
        view.right_panel.configure(width=650 if equipment else 330)
        view.body.pane(view.right_panel,weight=0)
        view.canvas.configure(width=490 if equipment else 560,height=352)
        view.canvas_area.pack_configure(fill='x' if equipment else 'both',expand=not equipment)
        view.legend.pack(side='bottom',fill='x',before=view.body)
        if equipment:
            view.side_content.pack_forget()
            view.equipment_candidates_panel.pack(fill='both',expand=True,pady=(4,0))
        else:view.side_content.pack(fill='both',expand=True)
    view.tabs.refresh()
