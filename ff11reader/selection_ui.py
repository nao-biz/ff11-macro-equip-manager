"""One selection/command controller shared by object views."""
import tkinter as tk
from . import dialogs
from .ui_actions import run_action
from .ui_tasks import background, is_running


class SelectionCommands:
    def __init__(self, view):
        self.view = view
        self.focus_job = None
        view.app.bind('<Destroy>', self.cancel_focus_restore, add='+')
        self.kind = None
        self.selection = set()
        self.anchor = None
        self.focus = None
        self.cards = {}
        self.menu = tk.Menu(view.app, tearoff=False, bg='#101b38', fg='#edf1fa', activebackground='#354b7a')
        self.actions = [('切り取り', 'Ctrl+X', 'cut'), ('コピー', 'Ctrl+C', 'copy'),
                        ('貼り付け…', 'Ctrl+V', 'paste'), ('削除…', 'Delete', 'delete'),
                        ('元に戻す', 'Ctrl+Z', 'undo'), ('やり直す', 'Ctrl+Y', 'redo')]
        for label, shortcut, command in self.actions:
            self.menu.add_command(label=label, accelerator=shortcut, command=lambda c=command:self.run(c))
        self.attach(view.nav, self._nav_address)
        self.attach(view.macro_tree, self._tree_address)

    def reset(self):
        self.kind = None;self.selection.clear();self.anchor = self.focus = None
        self.cards = {}
        self.paint()

    def cancel_focus_restore(self,event):
        if event.widget is self.view.app and self.focus_job:
            self.view.app.after_cancel(self.focus_job);self.focus_job=None

    def schedule_focus_restore(self):
        if self.focus_job:self.view.app.after_cancel(self.focus_job)
        self.focus_job=self.view.app.after_idle(self.restore_focus)

    def restore_focus(self):
        self.focus_job=None
        try:
            if self.view.app.grab_current() is not None:return
            widget=(self.cards.get(self.focus) if self.kind=='macro' else
                    self.view.macro_tree if self.kind=='palette' else self.view.nav)
            if widget is not None and widget.winfo_exists():widget.focus_set()
        except tk.TclError:pass

    def _nav_address(self, event):
        if self.view.mode.get() != '装備セット' or not self.view.navigation:return None
        index = self.view.nav.nearest(event.y)
        box = self.view.nav.bbox(index)
        if not box or not box[1] <= event.y < box[1]+box[3]:return None
        return 'equipment', (self.view.navigation[index].number,)

    def _tree_address(self, event):
        name = self.view.macro_tree.identify_row(event.y)
        if not name.startswith('palette-'):return None
        return 'palette', tuple(map(int, name.split('-')[1:]))

    def attach(self, widget, address):
        widget.bind('<Button-1>', lambda e:self.click(e, address(e)))
        widget.bind('<Button-3>', lambda e:self.context(e, address(e)))
        widget.bind('<Control-KeyPress>', self.keypress)
        widget.bind('<Delete>', lambda e:self.keypress(e))
        widget.bind('<Escape>', lambda e:self.keypress(e))
        for direction in ('Up','Down','Left','Right'):
            widget.bind(f'<{direction}>', self.navigate)

    def navigate(self, event):
        if self.focus is None or self.kind is None or self.view.app.grab_current() is not None:return None
        a=self.focus
        if self.kind=='macro':
            row=0 if a[2]=='ctrl' else 1;column=a[3]
            row+= {'Up':-1,'Down':1}.get(event.keysym,0)
            column+= {'Left':-1,'Right':1}.get(event.keysym,0)
            if not 0<=row<2 or not 1<=column<=10:return 'break'
            target=(*a[:2],('ctrl','alt')[row],column)
        else:
            if event.keysym not in ('Up','Down'):return None
            target=(*a[:-1],a[-1]+(-1 if event.keysym=='Up' else 1))
            available={(e.number,) for e in self.view.character.equipsets} if self.kind=='equipment' else {(m.book,m.palette) for m in self.view.character.macros}
            if target not in available:return 'break'
        self.select(self.kind,target,shift=bool(event.state&1),control=bool(event.state&4))
        if self.kind=='macro' and target in self.cards:self.cards[target].focus_set()
        return 'break'

    def register_card(self, widget, macro):
        address = (macro.book, macro.palette, macro.bank, macro.key)
        self.cards[address] = widget
        self.attach(widget, lambda e:('macro', address))
        self.paint()

    def click(self, event, target):
        if target is None:
            self.reset();return None
        if self.view.app.grab_current() not in (None, event.widget):return 'break'
        event.widget.focus_set()
        self.select(*target, shift=bool(event.state & 1), control=bool(event.state & 4))
        return 'break'

    def select(self, kind, address, shift=False, control=False):
        parent = lambda a:a[:2] if kind == 'macro' else a[:1] if kind == 'palette' else ()
        if self.kind != kind or self.anchor is None or parent(self.anchor) != parent(address):
            self.selection.clear();self.anchor = address;shift = control = False
        self.kind = kind;self.focus = address
        if shift:
            if kind == 'macro':
                banks = ('ctrl','alt');r1,r2=sorted((banks.index(self.anchor[2]),banks.index(address[2])))
                c1,c2=sorted((self.anchor[3],address[3]))
                selected = {(*address[:2],banks[r],c) for r in range(r1,r2+1) for c in range(c1,c2+1)}
            else:
                a,b = sorted((self.anchor[-1],address[-1]))
                selected = {(*address[:-1],n) for n in range(a,b+1)}
            self.selection = self.selection | selected if control else selected
        elif control:
            if address in self.selection:self.selection.remove(address)
            else:self.selection.add(address)
            self.anchor = address
        else:self.selection = {address};self.anchor = address
        v = self.view
        if kind == 'equipment':
            index=next(i for i,e in enumerate(v.navigation) if e.number==address[0])
            v.nav.selection_clear(0,'end');v.nav.selection_set(index);v.nav.activate(index);v.select_navigation()
        elif kind == 'palette':
            item=f'palette-{address[0]}-{address[1]}'
            v.macro_tree.selection_set(item);v.macro_tree.focus(item);v.select_macro_palette()
        else:
            macro=next(m for m in v.character.macros if (m.book,m.palette,m.bank,m.key)==address)
            v.inspect_macro(macro)
        self.paint()

    def paint(self):
        v=self.view
        transfer=v.editor.transfer
        cut=set(transfer.selection) if transfer and transfer.cut else set()
        cut_kind=transfer.kind if transfer and transfer.cut else None
        if v.mode.get()=='装備セット':
            v.nav.selection_clear(0,'end')
            for i,e in enumerate(v.navigation):
                if self.kind=='equipment' and (e.number,) in self.selection:v.nav.selection_set(i)
                v.nav.itemconfigure(i,foreground='#f3ce77' if cut_kind=='equipment' and (e.number,) in cut else ('#7e8ca9' if all(s.action=='keep' for s in e.slots) else '#edf1fa'))
        if v.mode.get()=='マクロ':
            if self.kind=='palette':
                items=[f'palette-{a[0]}-{a[1]}' for a in self.selection]
                v.macro_tree.selection_set([i for i in items if v.macro_tree.exists(i)])
            for book in v.macro_tree.get_children():
                for item in v.macro_tree.get_children(book):
                    a=tuple(map(int,item.split('-')[1:]));tags=tuple(t for t in v.macro_tree.item(item,'tags') if t!='cut')
                    v.macro_tree.item(item,tags=tags+(('cut',) if cut_kind=='palette' and a in cut else ()))
        for address,widget in list(self.cards.items()):
            if not widget.winfo_exists():continue
            selected=self.kind=='macro' and address in self.selection
            cutting=cut_kind=='macro' and address in cut
            widget.configure(highlightbackground='#f3ce77' if cutting else '#fff1bc' if selected else widget.normal_border,
                             background='#263b65' if selected else '#101e36')
        label={'macro':'マクロ','palette':'パレット','equipment':'装備セット'}.get(self.kind,'対象')
        message=f'{label} {len(self.selection)}件選択'
        if transfer:message+=f' · {"切り取り中" if transfer.cut else "コピー済み"} {len(transfer.selection)}件'
        v.selection_status.configure(text=message+'  |  Ctrl+X / C / V · Delete · Escで切り取り解除')

    def context(self, event, target):
        if target is None:return 'break'
        kind,address=target
        if self.kind!=kind or address not in self.selection:self.click(event,target)
        else:event.widget.focus_set()
        for i,(_,_,command) in enumerate(self.actions):
            self.menu.entryconfigure(i,state='disabled' if self.reason(command) else 'normal')
        reasons=[self.reason(command) for _,_,command in self.actions if self.reason(command)]
        if reasons:self.view.footer.configure(text=' / '.join(dict.fromkeys(reasons)))
        try:self.menu.tk_popup(event.x_root,event.y_root)
        finally:self.menu.grab_release()
        return 'break'

    def reason(self, command):
        if self.view.editor.blocked:return self.view.editor.blocked
        if command in ('undo','redo'):
            cursor,length,_=self.view.editor.edit_status()
            return '' if (cursor>0 if command=='undo' else cursor<length) else '対象の履歴がありません。'
        if not self.selection:return '対象を選択してください。'
        if command=='paste':
            transfer=self.view.editor.transfer
            if not transfer:return '先に切り取りまたはコピーをしてください。'
            if self.kind!=transfer.kind:return 'コピー元と同じ種類の貼り付け先を選択してください。'
            if len(self.selection)!=1:return '貼り付け基準を1か所選択してください。'
        return ''

    def keypress(self, event):
        if event.widget.winfo_toplevel()!=self.view.app or self.view.app.grab_current() is not None:return None
        symbol=event.keysym.lower() if len(event.keysym)==1 else event.keysym
        command={'x':'cut','c':'copy','v':'paste','z':'undo','y':'redo','Delete':'delete','Escape':'cancel'}.get(symbol)
        if command:self.run(command);return 'break'

    def run(self, command):
        if is_running(self.view.app):return
        heavy = {'cut', 'copy', 'paste', 'delete', 'undo', 'redo'}
        if command not in heavy or self.reason(command):return self._run(command)
        return run_action(self.view.app,lambda:self._run(command),busy=True)

    def _run(self, command):
        v=self.view
        if command=='cancel':
            if v.editor.transfer and v.editor.transfer.cut:v.editor.clear_transfer()
            self.paint();return
        reason=self.reason(command)
        if reason:v.footer.configure(text=reason);return
        try:
            folder=v.character.folder_id
            if command in ('copy','cut'):
                background(v.app,v.editor.capture_transfer,folder,self.kind,tuple(sorted(self.selection)),command=='cut');self.paint()
            elif command=='paste':
                anchor=next(iter(self.selection))
                edit=background(v.app,v.editor.prepare_paste,folder,anchor)
                v.preview_edit(edit,lambda:v.editor.paste(folder,anchor,edit))
            elif command=='delete':
                edit=background(v.app,v.editor.prepare_delete,folder,self.kind,tuple(sorted(self.selection)))
                v.preview_edit(edit,lambda:v.editor.apply(edit))
            else:v.undo_fix() if command=='undo' else v.redo_edit()
        except (ValueError,OSError) as exc:dialogs.showerror('編集操作',str(exc),parent=v.app)
