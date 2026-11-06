"""Equipment bonus panel; domain owns arithmetic and eligibility."""
import tkinter as tk
from tkinter import ttk
from .equipment_stats import summarize, BASE
from .equipment_stats_presentation import compact_properties

class EquipmentSummary:
    def __init__(self,parent):
        self.frame=ttk.Frame(parent)
        ttk.Label(self.frame,text='装備の加算値',font=('MS Gothic',13,'bold')).pack(anchor='w',pady=(0,6))
        values=ttk.Frame(self.frame);values.pack(fill='both',expand=True)
        self.body=tk.Text(values,height=18,width=44,bg='#101b38',fg='#edf1fa',
                          font=('MS Gothic',10),wrap='word',relief='flat',padx=10,pady=8,state='disabled')
        bar=ttk.Scrollbar(values,command=self.body.yview);self.body.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y');self.body.pack(fill='both',expand=True)
        self.note=ttk.Label(self.frame,text='',wraplength=340)
        self.note.pack(anchor='w',pady=4)
        ttk.Button(self.frame,text='集計の内訳…',command=self.details).pack(anchor='e',pady=(0,8))
        self.result=None
    def show(self,equipset,items,observation,before):
        self.result=summarize(equipset,items,observation)
        totals={(name,unit):value for name,unit,value in self.result.totals}
        lines=[]
        for name in BASE:
            fields=[f'{value:+}{unit}' for (key,unit),value in totals.items() if key==name]
            lines.append(name+'  '+(' / '.join(fields) if fields else '—'))
        basics=['   '.join(lines[:2]),'   '.join(lines[2:5]),'   '.join(lines[5:8]),lines[8]]
        props=compact_properties(self.result.totals)
        text='\n'.join(basics)+('\n'+'\n'.join(props) if props else '')
        self.body.configure(state='normal');self.body.delete('1.0','end');self.body.insert('1.0',text);self.body.configure(state='disabled')
        self.note.configure(text=f'集計できた加算値（上限適用前） / 集計外 {len(self.result.excluded)}件')
        self.frame.pack(before=before,fill='x')
    def hide(self):self.frame.pack_forget()
    def details(self):
        if self.result is None:return
        window=tk.Toplevel(self.frame,background='#080f22');window.title('装備加算値の内訳');window.geometry('650x500')
        text=tk.Text(window,bg='#101b38',fg='#edf1fa',wrap='word',padx=12,pady=12)
        bar=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('end','集計対象\n'+('\n'.join(f'{source}: {line}' for source,line in self.result.included) or 'なし'))
        text.insert('end','\n\n集計外\n'+('\n'.join(f'{source}: {line}' for source,line in self.result.excluded) or 'なし'))
        text.configure(state='disabled')


def operation_menu(parent,buttons):
    """Menu delegates to existing ActionButtons, preserving state and busy behavior."""
    menu=tk.Menu(parent,tearoff=False,bg='#101b38',fg='#edf1fa',activebackground='#354b7a')
    groups={name:tk.Menu(menu,tearoff=False,bg='#101b38',fg='#edf1fa',activebackground='#354b7a') for name in ('編集','確認・補正','個体情報','作業')}
    entries=[]
    for button in buttons:
        label=button.cget('text')
        group='個体情報' if '個体情報' in label else '作業' if 'リセット' in label else '確認・補正' if any(x in label for x in ('確認','補正','未参照')) else '編集'
        child=groups[group];index=child.index('end');index=0 if index is None else index+1
        child.add_command(label=label,command=button.invoke)
        entries.append((child,index,button))
        button.pack_forget()
    def sync():
        for child,index,button in entries:child.entryconfigure(index,state='disabled' if button.instate(['disabled']) else 'normal')
    for name,child in groups.items():
        child.configure(postcommand=sync);menu.add_cascade(label=name,menu=child)
    menu.configure(postcommand=sync)
    control=ttk.Menubutton(parent,text='操作 ▾',menu=menu);control.pack(side='left',padx=8)
    return control,menu
