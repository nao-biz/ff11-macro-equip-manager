"""Equipment slot input; selection rules live in the domain."""
from .theme import BG, PANEL, FG
import tkinter as tk
from tkinter import ttk
from . import dialogs
from .ui_actions import ActionButton


class SlotEditor:
    def __init__(self,parent,title,slot,rows,items,bags,on_preview,augment_text=None,*,embedded=False,on_cancel=None,augment_path=None):
        self.embedded=embedded
        if embedded:
            self.window=ttk.Frame(parent);self.window.pack(fill='both',expand=True)
        else:
            self.window=tk.Toplevel(parent,background=BG);self.window.title(title);self.window.geometry('820x560')
            dialogs.fit_to_screen(self.window)
        self.cancel=on_cancel or self.window.destroy
        self.augment_path=augment_path or (lambda row:'')
        self.augment_text=augment_text or (lambda row: "個体情報: 未取り込み")
        self.rows=rows;self.visible=[];self.items=items;self.bags=bags;self.on_preview=on_preview
        ttk.Label(self.window,text=title,padding=8,wraplength=290 if embedded else 760).pack(anchor='w')
        actions=ttk.Frame(self.window);actions.pack(fill='x',padx=12)
        self.action=tk.StringVar(value=slot.action if slot.action in ('keep','remove','equip') else 'keep')
        for value,label in [('keep','変更しない'),('remove','外す'),('equip','装備する')]:
            ttk.Radiobutton(actions,text=label,variable=self.action,value=value,command=self.toggle).pack(side='left',padx=2 if embedded else 10)
        ttk.Label(self.window,text='「変更しない」は、セット実行時の装備を維持します。',padding=8,wraplength=290 if embedded else 760).pack(anchor='w')
        search=ttk.Frame(self.window);search.pack(fill='x',padx=12)
        ttk.Label(search,text='名前・種類ID').pack(side='left')
        self.query=tk.StringVar();entry=ttk.Entry(search,textvariable=self.query,width=12 if embedded else 20);entry.pack(side='left',fill='x',expand=True,padx=8)
        ttk.Button(search,text='検索',command=self.filter).pack(side='left');entry.bind('<Return>',lambda e:self.filter())
        frame=ttk.Frame(self.window);frame.pack(fill='both',expand=True,padx=12,pady=8)
        self.listing=ttk.Treeview(frame,columns=('name','id','bag','index','augment'),show='headings',selectmode='browse',style='Macro.Treeview')
        for key,label,width in [('name','アイテム名',190),('id','種類ID',80),('bag','収納',115),('index','内部位置',80),('augment','取得した個体情報',260)]:
            self.listing.heading(key,text=label);self.listing.column(key,width=width,anchor='w')
        if embedded:
            self.listing.configure(displaycolumns=('name','augment'),height=8)
            self.listing.column('name',width=150,minwidth=80)
            self.listing.column('augment',width=65,minwidth=65,stretch=False)
            self.listing.heading('augment',text='Path')
        bar=ttk.Scrollbar(frame,command=self.listing.yview);self.listing.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');self.listing.pack(fill='both',expand=True)
        guidance=ttk.Label(self.window,text='全収納から、この部位に対応する装備を表示しています。',padding=8,wraplength=290 if embedded else 760)
        guidance.pack(anchor='w')
        self.info_frame=ttk.Frame(self.window);self.info_frame.pack(fill='x',padx=12,pady=4)
        if embedded:
            self.augment_detail=tk.Text(self.info_frame,height=4,width=1,bg=PANEL,fg=FG,wrap='word',relief='flat',state='disabled')
            detail_scroll=ttk.Scrollbar(self.info_frame,command=self.augment_detail.yview)
            self.augment_detail.configure(yscrollcommand=detail_scroll.set)
            detail_scroll.pack(side='right',fill='y')
        else:self.augment_detail=ttk.Label(self.info_frame,text='',wraplength=760)
        self.augment_detail.pack(fill='x')
        self.listing.bind('<<TreeviewSelect>>',self.show_augment)
        self.count=ttk.Label(self.window);self.count.pack(anchor='w',padx=12)
        controls=ttk.Frame(self.window);controls.pack(fill='x',padx=12,pady=12)
        ttk.Button(controls,text='キャンセル',command=self.cancel).pack(side='right')
        self.preview_button=ActionButton(controls,busy=True,text='変更案を確認',command=self.preview);self.preview_button.pack(side='right',padx=8)
        # Reserve actions and details before letting the candidate list fill the rest.
        for widget in (controls,self.count,self.info_frame,guidance):
            widget.pack_configure(side='bottom',before=frame)
        self.filter()
        for i,row in enumerate(self.visible):
            if (row.item_id,row.container,row.index)==(slot.item_id,slot.container,slot.index):self.listing.selection_set(str(i));self.listing.see(str(i));break
        self.toggle();self.window.bind('<Escape>',lambda e:self.cancel())

    def filter(self):
        from .equipment_editing import search_rows
        self.visible=list(search_rows(self.rows,self.items,self.query.get()))
        self.listing.delete(*self.listing.get_children())
        for i,row in enumerate(self.visible):self.listing.insert('','end',iid=str(i),values=(self.items.get(row.item_id,{}).get('name') or f'ID {row.item_id}',row.item_id,self.bags[row.container],row.index,self.augment_path(row) if self.embedded else self.augment_text(row).replace("\n", " / ")))
        self.count.configure(text=f'候補 {len(self.visible)}件')

    def show_augment(self,event=None):
        selected=self.listing.selection()
        if selected:
            row=self.visible[int(selected[0])]
            text=f'{self.bags[row.container]} / {row.index} · ID {row.item_id}\n'+self.augment_text(row)
            if self.embedded:
                self.augment_detail.configure(state='normal');self.augment_detail.delete('1.0','end')
                self.augment_detail.insert('1.0',text);self.augment_detail.configure(state='disabled')
            else:self.augment_detail.configure(text=text)

    def input_state(self):
        selected=self.listing.selection()
        row=self.visible[int(selected[0])] if selected else None
        return dict(action=self.action.get(),query=self.query.get(),selected=(row.item_id,row.container,row.index) if row else None)

    def restore_input(self,state):
        self.action.set(state['action']);self.query.set(state['query']);self.filter()
        for i,row in enumerate(self.visible):
            if (row.item_id,row.container,row.index)==state['selected']:
                self.listing.selection_set(str(i));self.listing.see(str(i));break
        self.toggle();self.show_augment()

    def toggle(self):
        self.listing.state(['!disabled'] if self.action.get()=='equip' else ['disabled'])

    def preview(self):
        selection=None
        if self.action.get()=='equip':
            selected=self.listing.selection()
            if not selected:
                dialogs.showwarning('アイテムを選択','装備するアイテムの行を選んでください。',parent=self.window);return
            row=self.visible[int(selected[0])];selection=(row.item_id,row.container,row.index)
        self.on_preview(self.action.get(),selection,self.window)
