"""Graphical workspace with explicit, guarded equipment reference saving."""
from .theme import ACCENT, BG, BORDER, DANGER, FG, MUTED, PANEL, REVIEW, SELECT, SUCCESS, WARNING
from collections import Counter
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog
from . import dialogs
from .ui_actions import ActionButton
from .ui_tasks import background
from .application import preview_reference_fixes
from .presentation import present_slot, format_token_ids
from .macro_links import is_empty
from .edit_application import Editor
from .editing import plan_macro_fixes, macro_key
from .macro_inventory import assess_macro_inventory, LABELS as MACRO_ITEM_LABELS
from .application import inspect_macro_set_links, inspect_wardrobe_usage
from pathlib import Path
from .tracing import configure, traced
from .augment_names import apply_names


ACTION_STYLE = {
 'match': ('一致', PANEL, SUCCESS),
 'fixable': ('Fix可能', PANEL, ACCENT),
 'multiple': ('候補が複数', PANEL, WARNING),
 'missing': ('候補なし', PANEL, DANGER),
 'needs_review': ('要確認', PANEL, REVIEW),
 'not_applicable': ('', BG, MUTED),
}
OBSERVATIONS = {'cache_match':'登録した位置と種類IDが持ち物データと一致',
 'cache_item_mismatch':'登録した位置にあるアイテムの種類IDが異なる',
 'cache_position_empty':'登録した位置にアイテムが見つからない',
 'cache_unavailable':'対象の収納データを読み取れていない',
 'invalid_reference':'保存された参照値が想定範囲外',
 'unknown_action':'装備枠の動作を判別できない',
 'ambiguous_position':'同じ収納・位置のデータが重複', 'unassessed':'未評価', 'not_applicable':'対象外'}
BAGS={0:'マイバッグ',1:'モグ金庫',2:'収納家具',3:'一時アイテム',4:'ロッカー',5:'サッチェル',6:'サック',7:'ケース',8:'ワードローブ1',9:'モグ金庫2',**{i+8:f'ワードローブ{i}' for i in range(2,9)}}
# 収納IDとは独立した、ゲームのストレージメニューに沿う表示順。
INVENTORY_BAG_ORDER=(0,1,9,2,4,5,6,7,8,10,11,12,13,14,15,16,3)
SLOTS={'main':'メイン','sub':'サブ','range':'遠隔','ammo':'矢弾','head':'頭','neck':'首','ear1':'左耳','ear2':'右耳','body':'胴','hands':'両手','ring1':'左指','ring2':'右指','back':'背','waist':'腰','legs':'両脚','feet':'両足'}
GRID='main sub range ammo head neck ear1 ear2 body hands ring1 ring2 back waist legs feet'.split()


class ReaderWindow:
 def __init__(self, app, snapshot, *, editor=None):
  self.app=app;self.snapshot=snapshot;self.photos={};self.card_widgets={};self.navigation=[];self.selected=None
  self.augment_observations={}
  self.editor=editor if editor is not None else Editor(snapshot)
  if editor is None:self.snapshot=self.editor.snapshot()
  self.active_macro=None
  from .workspace_ui import build
  build(self)
  from .selection_ui import SelectionCommands
  self.commands=SelectionCommands(self)
  from .augment_store import AugmentStore
  self.augment_store=AugmentStore(self.editor.state_path.parent/'augment-observations')
  self.restore_augments()
  if snapshot.characters:
   self.character_choice.current(next((i for i,c in enumerate(snapshot.characters) if c.equipment_references),0));self.change_character()
  else:self.show_detail('キャラクターなし','読み取れたキャラクターフォルダはありません。')
  self.update_edit_status()
  if self.editor.blocked:dialogs.when_visible(self.app,lambda:dialogs.showwarning('ゲーム保存の復旧確認',self.editor.blocked,parent=self.app))

 def close(self):
  from .ui_tasks import is_running
  if is_running(self.app) or getattr(self,'closing',False):return
  if not self.editor.edit_status()[2] and not self.macro_panel.has_pending():
   self.app.destroy();return
  self.closing=True
  try:
   choice=dialogs.ask_save_changes(parent=self.app)
   if choice=='discard':self.app.destroy()
   elif choice=='save':self.preview_combined_save(after_save=self.app.destroy)
  finally:self.closing=False

 @property
 def character(self):
  i=self.character_choice.current();return self.snapshot.characters[i] if i>=0 else None

 def character_labels(self):return [(c.display_name or '名前未確認')+f' [{c.folder_id}]' for c in self.snapshot.characters]
 def equipset_label(self,number,character=None):
  c=character or self.character
  equipset=next((e for e in c.equipsets if e.number==number),None) if c else None
  title=equipset.title.display if equipset else ''
  return f'{number:03}  {title or "（名称なし）"}'
 def item_name(self,item):return self.snapshot.items.get(item,{}).get('name') or (f'ID {item}' if item is not None else '—')
 def icon(self,item):
  if item not in self.photos:
   raw=self.snapshot.items.get(item,{}).get('icon_png')
   try:self.photos[item]=tk.PhotoImage(master=self.app,data=raw).zoom(2,2) if raw else None
   except tk.TclError:self.photos[item]=None
  return self.photos[item]
 def preview_fixes(self):
  c=self.character
  if not c:return
  plan=background(self.app,preview_reference_fixes,self.snapshot,c)
  window=tk.Toplevel(self.app,background=BG);window.title('装備セットの参照位置チェック');window.geometry('950x650')
  dialogs.fit_to_screen(window)
  ttk.Label(window,text=f'{c.folder_id}  ·  更新案 {len(plan.changes)}枠  ·  保留 {len(plan.issues)}枠',padding=12).pack(anchor='w')
  ttk.Label(window,text='チェック結果です。「補正を適用」で作業データの参照位置を変更できます。適用後はUndoで戻せます。',padding=8).pack(anchor='w')
  text=tk.Text(window,wrap='word',bg=PANEL,fg=FG,font=('MS Gothic',11),padx=12,pady=12)
  text.pack(fill='both',expand=True,padx=12)
  for x in plan.changes:
   text.insert('end',f'{self.equipset_label(x.equipset,c)} / {SLOTS[x.slot]}  {self.item_name(x.item_id)} (ID {x.item_id})\n  {BAGS.get(x.before[0],x.before[0])} / {x.before[1]} → {BAGS[x.after[0]]} / {x.after[1]}\n\n')
  reasons={'invalid_reference':'参照値不正','incomplete_inventory':'取得不足','not_observed':'候補なし','multiple_candidates':'同IDが複数','ambiguous_target':'候補位置が不正・重複','quantity_not_one':'数量が1ではない'}
  if plan.issues:
   text.insert('end','保留\n')
   for x in plan.issues:text.insert('end',f'{self.equipset_label(x.equipset,c)} / {SLOTS[x.slot]}: {reasons[x.reason]}\n')
  if not plan.changes:text.insert('end','適用できるFix案はありません。')
  text.configure(state='disabled')
  def apply():
   try:self.run_edit(lambda:self.editor.equipment_fixes(c.folder_id,plan))
   except (ValueError,OSError) as e:dialogs.showerror('適用できません',str(e),parent=window);return
   window.destroy()
   self.footer.configure(text=f'アプリ内の作業データに {len(plan.changes)}枠のFixを適用しました。')
  dialogs.confirm_buttons(window,apply,enabled=bool(plan.changes) and not self.editor.blocked)
  window.accept_button.configure(text='補正を適用')
  window.cancel_button.configure(text='閉じる')
 @traced('ui.update_edit_status')
 def update_edit_status(self):
  character=getattr(self,'character',None)
  name=(character.display_name or character.folder_id) if character else '未選択'
  self.common_scope.configure(text=f'チェック・取り込み対象: {name}')
  for button in (self.fix_button,self.macro_fix_button,self.links_button,self.unused_button,self.import_button):
   button.configure(state='normal' if character else 'disabled')
  cursor,history_length,dirty=self.editor.edit_status()
  pending=self.macro_panel.has_pending()
  self.copy_book_button.configure(state='normal' if character and len(self.snapshot.characters)>1 and not self.editor.blocked else 'disabled')
  self.clear_character_button.configure(state='normal' if character and not self.editor.blocked else 'disabled')
  self.undo_button.configure(state='normal' if cursor and not self.editor.blocked else 'disabled')
  self.redo_button.configure(state='normal' if cursor<history_length and not self.editor.blocked else 'disabled')
  self.save_button.configure(state='normal' if (dirty or pending) and not self.editor.blocked else 'disabled')
  self.draft_label.configure(text='ゲームデータとの確認が必要' if self.editor.blocked else ('未保存の変更あり' if dirty or pending else 'ゲームデータと同じ'))
 @traced('ui.refresh_edits')
 def refresh_edits(self,snapshot=None):
  self.snapshot=snapshot if snapshot is not None else background(self.app,self.editor.snapshot,self.snapshot)
  apply_names(self.snapshot,self.augment_observations)
  self.change_mode()
  self.update_edit_status()
  self.commands.schedule_focus_restore()
 @traced('ui.run_edit')
 def run_edit(self,operation):
  previous=self.snapshot
  def apply_and_snapshot():
   operation()
   return self.editor.snapshot(previous)
  self.refresh_edits(background(self.app,apply_and_snapshot))
 def undo_fix(self):
  try:self.run_edit(self.editor.undo)
  except (OSError,ValueError) as e:dialogs.showerror('Undo',str(e),parent=self.app);return
 def redo_edit(self):
  try:self.run_edit(self.editor.redo)
  except (OSError,ValueError) as e:dialogs.showerror('Redo',str(e),parent=self.app);return
 def import_augments(self):
  if not self.character:return
  path=filedialog.askopenfilename(parent=self.app,title='個体情報JSONを選択',filetypes=[('個体情報','*.json')])
  if not path:return
  from .augment_import import load_observation
  character=self.character
  try:observation=background(self.app,load_observation,path,character,self.snapshot.rank_augments,message='個体情報を読み込んでいます…')
  except (OSError,ValueError) as e:
   dialogs.showerror('個体情報の取り込み',str(e),parent=self.app);return
  source=observation.export
  message=f'出力元: {source.character_name} / ID {source.character_id} / サーバー {source.server}\n取得日時: {source.captured_at}\n取り込み先: {character.display_name or character.folder_id}\n\n位置と種類IDが一致した収納: {len(observation.accepted_bags)} / 17\n'
  if observation.issues:message+='\n再取得が必要: '+', '.join(BAGS[b] for b,_ in observation.issues)+'\n'
  message+='\n出力後に移動・強化した場合、情報が古くなります。同種類同士の入れ替えは照合で検出できません。\nこの取得結果を、選択したキャラクターの個体情報として使用してよいですか？'
  if not dialogs.askyesno('出力元キャラを確認',message,parent=self.app,accept_label='取り込む'):return
  try:background(self.app,self.augment_store.save,self.snapshot.installation_key,character.folder_id,observation.export,message='個体情報を保存しています…')
  except (OSError,ValueError) as e:
   dialogs.showerror('個体情報を保存できませんでした',str(e),parent=self.app);return
  self.augment_observations[character.folder_id]=observation
  apply_names(self.snapshot,self.augment_observations)
  i=self.character_choice.current();self.character_choice.configure(values=self.character_labels());self.character_choice.current(i)
  self.update_edit_status()
  self.footer.configure(text=f'{source.character_name} の個体情報を取り込みました（{source.captured_at}）。')
  self.change_mode()
 def restore_augments(self, *, notify=True):
  from .augment_inbox import ExportPending, EXPORT_PENDING
  observations,errors=background(self.app,self.augment_store.restore,self.snapshot,message='最新の個体情報を取り込んでいます…')
  self.augment_observations=observations
  apply_names(self.snapshot,observations)
  self.character_choice.configure(values=self.character_labels())
  failures={folder:error for folder,error in errors.items() if not isinstance(error,ExportPending)}
  if not notify:
   if errors:self.footer.configure(text=' / '.join(str(error) for error in errors.values()))
   return errors
  if failures:
   message='\n'.join(f'{folder}: {error}' for folder,error in failures.items())
   dialogs.when_visible(self.app,lambda:dialogs.showwarning('個体情報の自動取り込み・復元',message,parent=self.app))
  elif errors:
   dialogs.when_visible(self.app,lambda:dialogs.showinfo('個体情報の自動取得',EXPORT_PENDING,parent=self.app))
 def augment_text(self,row):
  from .augment_presentation import describe
  return describe(self.augment_observations.get(self.character.folder_id),row)
 def configure_windower(self, *, first=False):
  from .windower_settings_ui import configure
  if configure(self.app,self.augment_store.settings,first=first):
   index=self.character_choice.current()
   self.restore_augments()
   if index>=0:self.character_choice.current(index)
   self.change_mode()
   self.footer.configure(text='ゲームにログインすると自動取得されます。ゲーム終了後に自動で反映されます。')
 def reload_data(self):
  if not dialogs.askyesno('ゲームデータを再読み込み','全キャラの未保存の変更と入力中のマクロを破棄し、最新のゲームデータを読み込みます。\n再読み込みしてよいですか？',parent=self.app,accept_label='再読み込み'):return
  folder=self.character.folder_id if self.character else None
  try:background(self.app,self.editor.reload,message='ゲームデータを読み込んでいます…')
  except (OSError,ValueError,RuntimeError) as e:
   dialogs.showerror('再読み込みできませんでした',str(e),parent=self.app);return
  self.macro_panel.discard();self.view_states.clear();self.view_key=None
  self.snapshot=background(self.app,self.editor.snapshot);self.photos.clear();self.selected=None;self.active_macro=None
  self.restore_augments()
  self.character_choice.configure(values=self.character_labels())
  if self.snapshot.characters:
   self.character_choice.current(next((i for i,c in enumerate(self.snapshot.characters) if c.folder_id==folder),0));self.change_character()
  else:
   self.character_choice.set('');self.commands.reset();self.clear_cards();self.nav.delete(0,'end');self.macro_tree.delete(*self.macro_tree.get_children());self.navigation=[]
   self.heading.configure(text='キャラクターがありません');self.subtitle.configure(text='');self.show_detail('データなし','読み取れたキャラクターがありません。')
   for button in (self.edit_button,self.equipment_name_button,self.move_button,self.slot_edit_button):button.configure(state='disabled')
  self.update_edit_status()
  self.footer.configure(text='最新のゲームデータを読み込みました。')

 def reset_edits(self):
  if not dialogs.askyesno('編集をリセット','全キャラの未保存の変更と入力中のマクロを破棄し、最後に読み込んだ、または書き戻した内容へ戻します。\n変更を破棄してよいですか？',parent=self.app,accept_label='変更を破棄'):return
  try:background(self.app,self.editor.start_fresh)
  except (OSError,ValueError) as e:dialogs.showerror('リセット',str(e),parent=self.app);return
  self.macro_panel.discard();self.refresh_edits()
 def clear_character_data(self):
  from .character_clear_ui import clear_character
  return clear_character(self)
 def preview_game_save(self,scope='storage-fix'):
  if not self.character:return
  if self.editor.has_pending_move(self.character.folder_id):return self.preview_combined_save()
  try:plan=background(self.app,self.editor.prepare_macro_save,self.character.folder_id,scope)
  except (OSError,ValueError,RuntimeError) as e:dialogs.showerror('保存プレビュー',str(e),parent=self.app);return
  window=tk.Toplevel(self.app,background=BG);window.title('マクロの編集 / ゲームへの保存' if scope=='all' else 'マクロ収納番号Fix / ゲームへの保存');window.geometry('980x680')
  dialogs.fit_to_screen(window)
  count=sum(len(f.changes) for f in plan.files)
  ttk.Label(window,text=f'{self.character.display_name or self.character.folder_id} · {count}項目 / {len(plan.files)}ファイル · 保留 {plan.deferred}件（詳細は下記）',padding=10).pack(anchor='w')
  ttk.Label(window,text='表示したゲームファイルを上書きします。変更前のファイルをバックアップし、失敗時は復元します。\nFF11とPlayOnlineが終了している状態で、この変更を保存してよいですか？',padding=10).pack(anchor='w')
  text=tk.Text(window,bg=PANEL,fg=FG,wrap='word',padx=12,pady=12)
  bar=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
  for file in plan.files:
   text.insert('end',file.target+'\n')
   for change in file.changes:
    b,p,bank,key=change.address
    field='名前' if change.line==0 else f'{change.line}行目'
    text.insert('end',f'ブック {b:02} / パレット {p} / {bank.upper()} {key if key<10 else 0} / {field}\n  前: {change.before}\n  後: {change.after}\n\n')
    if change.before==change.after:text.insert('end',f'定型文ID: {format_token_ids(change.original_tokens)} → {format_token_ids(change.tokens)}\n\n')
  if plan.deferred_changes:
   text.insert('end','作業データに残す変更\n')
   for change in plan.deferred_changes:text.insert('end',f'{change.target}: {change.reason}\n')
  text.configure(state='disabled')
  def save():
   button.configure(state='disabled');window.update_idletasks()
   try:backup=background(self.app,self.editor.save_macros,plan,Path(__file__).resolve().parent.parent/'backups'/'macros',message='マクロを保存しています…')
   except (OSError,ValueError,RuntimeError) as e:
    self.update_edit_status();dialogs.showerror('ゲームへの保存',str(e),parent=window);button.configure(state='normal');return
   window.destroy();self.refresh_edits();self.footer.configure(text=f'{count}項目を保存・検証しました。バックアップ: {backup}')
  button=dialogs.confirm_buttons(window,save,enabled=bool(count))
 def preview_equipment_save(self):
  from .equipment_saving import EquipmentNameChange, EquipmentSlotChange
  if not self.character:return
  if self.editor.has_pending_move(self.character.folder_id):return self.preview_combined_save()
  try:plan=background(self.app,self.editor.prepare_equipment_save,self.character.folder_id,'all')
  except (OSError,ValueError,RuntimeError) as e:dialogs.showerror('保存プレビュー',str(e),parent=self.app);return
  window=tk.Toplevel(self.app,background=BG);window.title('装備セットの編集 / ゲームへの保存');window.geometry('980x680')
  dialogs.fit_to_screen(window)
  count=sum(len(f.changes) for f in plan.files)
  ttk.Label(window,text=f'{self.character.display_name or self.character.folder_id} · {count}項目 / {len(plan.files)}ファイル · 保留 {plan.deferred}件（詳細は下記）',padding=10).pack(anchor='w')
  ttk.Label(window,text='表示したゲームファイルを上書きします。変更前のファイルをバックアップし、失敗時は復元します。\nFF11とPlayOnlineが終了している状態で、この変更を保存してよいですか？',padding=10).pack(anchor='w')
  text=tk.Text(window,bg=PANEL,fg=FG,wrap='word',padx=12,pady=12)
  bar=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
  for file in plan.files:
   text.insert('end',file.target+'\n')
   for change in file.changes:
    if isinstance(change,EquipmentSlotChange):
     text.insert('end',f'{self.equipset_label(change.equipset,self.character)} / {SLOTS[change.slot]}\n  前: {self.slot_description(change.before)}\n  後: {self.slot_description(change.after)}\n\n');continue
    if isinstance(change,EquipmentNameChange):
     text.insert('end',f'装備セット {change.equipset:03} / 名前\n  前: {change.before}\n  後: {change.after}\n\n');continue
    text.insert('end',f'{self.equipset_label(change.equipset,self.character)} / {SLOTS[change.slot]} / {self.item_name(change.item_id)} (ID {change.item_id})\n  前: {BAGS.get(change.before[0],change.before[0])} / 位置 {change.before[1]}\n  後: {BAGS[change.after[0]]} / 位置 {change.after[1]}\n\n')
  if plan.deferred_changes:
   text.insert('end','作業データに残す変更\n')
   for change in plan.deferred_changes:text.insert('end',f'{change.target}: {change.reason}\n')
  text.configure(state='disabled')
  def save():
   button.configure(state='disabled');window.update_idletasks()
   try:backup=background(self.app,self.editor.save_equipment,plan,Path(__file__).resolve().parent.parent/'backups'/'equipment',message='装備セットを保存しています…')
   except (OSError,ValueError,RuntimeError) as e:
    self.update_edit_status();dialogs.showerror('ゲームへの保存',str(e),parent=window);button.configure(state='normal');return
   window.destroy();self.refresh_edits();self.footer.configure(text=f'{count}項目を保存・検証しました。バックアップ: {backup}')
  button=dialogs.confirm_buttons(window,save,enabled=bool(count))
 def change_character(self,event=None):
  self.editor.clear_transfer()
  self.change_mode()
  self.update_edit_status()
 @traced('ui.change_mode')
 def change_mode(self):
  if not self.character:return
  from .workspace_state import remember,restore,layout
  remember(self)
  self.view_key=(self.character.folder_id,self.mode.get())
  saved=self.view_states.get(self.view_key,{})
  self.clear_cards();self.selected=None
  layout(self)
  self.active_macro=None;self.edit_button.configure(state='disabled');self.equipment_name_button.configure(state='disabled');self.move_button.configure(state='disabled');self.active_slot=None;self.slot_edit_button.configure(state='disabled')
  if hasattr(self,'commands'):
   self.commands.kind=None;self.commands.selection.clear();self.commands.anchor=None;self.commands.focus=None;self.commands.cards={}
  self.nav.delete(0,'end');c=self.character;mode=self.mode.get();self.navigation=[]
  self.macro_tree.delete(*self.macro_tree.get_children())
  self.macro_tree.pack_forget();self.nav.pack_forget()
  active=self.macro_tree if mode=='マクロ' else self.nav
  active.pack(fill='both',expand=True);self.nav_scroll.configure(command=active.yview)
  self.fix_plan=preview_reference_fixes(self.snapshot,c)
  self.macro_links=inspect_macro_set_links(self.snapshot,c)
  self.macro_item_refs=assess_macro_inventory(c,self.snapshot.items)
  if mode=='装備セット':
   self.nav_title.configure(text='装備セット')
   self.navigation=c.equipsets
   for e in self.navigation:
    self.nav.insert('end',self.equipset_label(e.number)+('  [マクロ参照なし]' if e.number in self.macro_links.unreferenced else ''))
    if is_empty(e):self.nav.itemconfigure(self.nav.size()-1,foreground=MUTED,selectforeground=MUTED)
  elif mode=='マクロ':
   self.nav_title.configure(text='ブック / パレット')
   self.navigation=sorted({(m.book,m.palette) for m in c.macros})
   for book in sorted({b for b,_ in self.navigation}):
    title=c.books.get(book)
    self.macro_tree.insert('','end',iid=f'book-{book}',text=f'{book:02}  '+((title.display.strip() if title else '') or '（名前なし）'),open=False)
   for book,palette in self.navigation:
    macros=[m for m in c.macros if (m.book,m.palette)==(book,palette)]
    empty=all(not m.title.display.strip() and all(not line.display.strip() for line in m.lines) for m in macros)
    self.macro_tree.insert(f'book-{book}','end',iid=f'palette-{book}-{palette}',text=f'パレット {palette}',tags=('empty',) if empty else ())
   for book in self.macro_tree.get_children():
    if all('empty' in self.macro_tree.item(palette,'tags') for palette in self.macro_tree.get_children(book)):
     self.macro_tree.item(book,tags=('empty',))
  else:
   self.nav_title.configure(text='収納')
   self.navigation=list(INVENTORY_BAG_ORDER)
   counts=Counter(r.container for r in c.inventory)
   for bag in self.navigation:self.nav.insert('end',f'{BAGS[bag]}  ·  {counts[bag]}')
  if self.navigation:
   if mode=='マクロ':
    book,palette=saved.get('selected') if saved.get('selected') in self.navigation else self.navigation[0]
    self.macro_tree.selection_set(f'palette-{book}-{palette}');self.select_macro_palette()
   else:
    index=next((i for i,x in enumerate(self.navigation) if (x.number if mode=='装備セット' else x)==saved.get('selected')),0)
    self.nav.selection_set(index);self.nav.activate(index);self.select_navigation()
  else:
   self.clear_cards();self.heading.configure(text=mode);self.subtitle.configure(text='読み取れたデータがありません。');self.show_detail('データなし','インベントリ保存情報や設定ファイルが未取得の場合もあります。')
  if hasattr(self,'commands'):self.commands.paint()
  restore(self,saved)
 def clear_cards(self):
  self.macro_panel.hide()
  self.close_slot_editor()
  self.active_inventory=None
  from .item_properties import ItemProperties
  self.inventory_properties.show(ItemProperties())
  self.inventory_compare_button.configure(state='disabled')
  self.inventory_details_button.configure(state='disabled')
  if hasattr(self,'commands'):self.commands.cards={}
  for w in self.cards.winfo_children():w.destroy()
  self.inventory_switch.pack_forget()
  self.equipment_summary.hide()
  self.card_widgets={};self.active_card=None
  for column in range(10):self.cards.columnconfigure(column,weight=0,minsize=0)
  self.canvas.yview_moveto(0)
 def expand_macro_book(self,item):
  book=self.macro_tree.parent(item) or item
  for sibling in self.macro_tree.get_children():
   self.macro_tree.item(sibling,open=sibling==book)
 def open_macro_book(self,event=None):
  item=self.macro_tree.focus()
  if item:self.expand_macro_book(item)
 def select_macro_palette(self,event=None):
  if self.mode.get()!='マクロ':return
  if event is not None and self.app.focus_get() is self.macro_tree:self.commands.sync_palette_selection()
  selection=self.macro_tree.selection()
  if not selection:return
  focused=self.macro_tree.focus()
  selection=(focused if focused in selection else selection[0],)
  self.expand_macro_book(selection[0])
  parts=selection[0].split('-')
  if parts[0]=='book':
   self.active_macro=None;self.edit_button.configure(state='disabled');self.equipment_name_button.configure(state='disabled');self.move_button.configure(state='disabled');self.active_slot=None;self.slot_edit_button.configure(state='disabled')
   self.clear_cards();self.selected=None
   self.heading.configure(text=self.macro_tree.item(selection[0],'text'))
   self.subtitle.configure(text='パレットを選択してください。')
   self.show_detail('ブック','左のツリーからパレットを選択してください。');return
  value=(int(parts[1]),int(parts[2]))
  if event is not None and self.selected==value:return
  self.clear_cards();self.selected=value;self.render_macros(value)
 def enter_navigation(self):
  if self.mode.get()=='マクロ':
   self.select_macro_palette()
   if self.commands.cards:
    address=next(iter(self.commands.cards));self.commands.select('macro',address)
    self.commands.cards[address].focus_set()
  elif self.mode.get()=='装備セット':
   self.select_navigation()
   if self.card_widgets:self.card_widgets[self.active_slot or 'main'].focus_set()
  else:
   self.select_navigation()
   if self.card_widgets:
    index=next(iter(self.card_widgets))
    row=next(r for r in self.character.inventory if r.container==self.selected and r.index==index)
    self.activate_card(self.card_widgets[index],lambda:self.inspect_inventory(row))
  return 'break'

 def select_navigation(self,event=None):
  selection=self.nav.curselection()
  if not selection:return
  active=self.nav.index('active')
  value=self.navigation[active if active in selection else selection[0]];self.clear_cards();self.selected=value
  mode=self.mode.get()
  if mode=='装備セット':
   self.render_equipment(value);self.equipment_name_button.configure(state='disabled' if self.editor.blocked else 'normal');self.move_button.configure(state='disabled' if self.editor.blocked else 'normal')
  elif mode=='マクロ':self.render_macros(value)
  else:self.render_inventory(value)
 def show_evidence(self):
  if not self.evidence:return
  previous=self.app.focus_get()
  title,body=self.evidence
  window=tk.Toplevel(self.app,background=BG);window.title('詳細 / '+title);window.geometry('780x650')
  def close(event=None):
   window.destroy()
   if previous and previous.winfo_exists():previous.focus_set()
   return 'break'
  window.bind('<Escape>',close);window.protocol('WM_DELETE_WINDOW',close)
  dialogs.after_idle_alive(window,window.focus_set)
  dialogs.fit_to_screen(window)
  text=tk.Text(window,wrap='word',bg=PANEL,fg=FG,font=('MS Gothic',11),padx=14,pady=14)
  bar=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
  text.insert('end',body);text.configure(state='disabled')
 def show_detail(self,title,text,actions=(),evidence=None):
  self.evidence=(title,evidence) if evidence else None
  self.details_button.configure(state='normal' if evidence else 'disabled')
  self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('end',title+'\n\n','title');self.detail.insert('end',text);self.detail.configure(state='disabled')
  self.candidate_menu.delete(0,'end')
  for label,command in actions:self.candidate_menu.add_command(label=label,command=command)
  self.candidate_button.configure(state='normal' if actions else 'disabled',text=f'候補の場所を見る ({len(actions)})' if actions else '候補の場所を見る')
 def card(self,index,title,caption,command,item=None,state=None,badge=None,compact=False,annotation=None,equipment=False):
  label,bg,fg=ACTION_STYLE[state] if state is not None else ('',PANEL,MUTED)
  from .theme import GEAR_HEIGHT
  height=48 if compact else 78 if equipment else GEAR_HEIGHT
  caption_y=32 if compact else 38 if equipment else 74
  badge_y=66 if equipment else 96
  frame=tk.Canvas(self.cards,bg=bg,highlightbackground=fg,highlightthickness=1,borderwidth=0,width=48 if compact else 142,height=height)
  frame.normal_border=fg
  columns=10 if compact else 4
  row=index//10*2+1 if compact else index//4
  frame.grid(row=row,column=index%columns,padx=2 if compact else 4,pady=4,sticky='nsew')
  self.cards.columnconfigure(index%columns,weight=1)
  border=frame.create_rectangle(2,2,140,height-3,outline=BORDER)
  title_id=frame.create_text(70,14,text=title,fill=fg,font=('MS Gothic',10,'bold'))
  photo=self.icon(item) if item is not None and not equipment else None
  if photo:photo=photo.subsample(2,2);frame.photo=photo
  image_id=None
  if not compact and not equipment:
   image_id=frame.create_image(70,40,image=photo) if photo else frame.create_text(70,40,text='—',fill=fg,font=('MS Gothic',16))
  annotation_id=None
  caption_id=frame.create_text(70,caption_y,text=caption,fill=FG,width=128,font=('MS Gothic',9))
  badge_text=annotation or (label if badge is None else badge)
  badge_id=frame.create_text(70,badge_y,text=badge_text,fill=ACCENT if badge is not None else fg,width=128,font=('MS Gothic',9)) if badge_text and not compact else None
  def resize(event):
   width=event.width
   frame.coords(border,2,2,width-3,height-3)
   for node,y in [(title_id,14),(image_id,40),(caption_id,caption_y),(badge_id,badge_y)]:
    if node is not None:frame.coords(node,width/2,y)
   frame.itemconfigure(caption_id,width=max(20,width-12))
   if badge_id is not None:frame.itemconfigure(badge_id,width=max(20,width-12))
  frame.bind('<Configure>',resize)
  frame.bind('<Button-1>',lambda e:self.activate_card(frame,command))
  frame.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(-int(e.delta/120),'units'))
  return frame
 def activate_card(self,frame,command):
  previous=getattr(self,'active_card',None)
  if previous is not None and previous.winfo_exists():previous.configure(highlightbackground=previous.normal_border,highlightthickness=1)
  frame.focus_set()
  self.active_card=frame;frame.configure(highlightbackground=ACCENT,highlightthickness=1);command()
 def render_equipment(self,equipset):
  self.selected=equipset
  self.equipment_summary.show(equipset,self.snapshot.items,self.augment_observations.get(self.character.folder_id),self.snapshot.augment_names)
  self.active_slot=None;self.slot_edit_button.configure(state='disabled')
  self.heading.configure(text=self.equipset_label(equipset.number))
  refs=self.macro_links.for_set(equipset.number)
  summary=f'マクロ参照: {len(refs)}行' if refs else 'マクロ参照なし'
  self.subtitle.configure(text=summary+' · 枠を選んで候補を比較')
  slots={s.name:s for s in equipset.slots}
  for i,key in enumerate(GRID):
   s=slots[key];caption=self.item_name(s.item_id) if s.action=='equip' else {'keep':'変更しない','remove':'装備を外す'}.get(s.action,'未知の動作')
   self.card_widgets[key]=self.card(i,SLOTS[key],caption,lambda slot=s:self.inspect_slot(slot),s.item_id if s.action=='equip' else None,present_slot(s,equipset.number,self.fix_plan).status,badge=self.augment_path(s) if s.action=='equip' else '',equipment=True)
   self.card_widgets[key].bind('<Double-Button-1>',lambda event,slot=s:self.open_slot_editor(slot))
   self.bind_card_navigation(self.card_widgets[key],key,'equipment')
  counts=Counter(ACTION_STYLE[present_slot(s,equipset.number,self.fix_plan).status][0] for s in equipset.slots if s.action=='equip')
  body='\n'.join(f'{k}: {v}枠' for k,v in counts.items())
  if not is_empty(equipset):
   body+='\n\n参照元マクロ\n'
   if refs:
    body+='\n\n'.join(f'ブック {r.book:02} / パレット {r.palette:02}\n{r.bank.upper()} {r.key if r.key<10 else 0} · {r.macro_title or "（空欄）"}\n{r.line}行目: /{r.command} {r.number:03}' for r in refs)
   else:body+='マクロ参照なし'
  body+='\n\n枠をダブルクリックして編集できます。補正は「操作」から変更案を確認できます。'
  self.show_detail('装備セット '+self.equipset_label(equipset.number),body)
  self.activate_card(self.card_widgets['main'],lambda:self.inspect_slot(slots['main']))
 def restore_card_focus(self,key):
  if self.commands.focus_job:
   self.app.after_cancel(self.commands.focus_job);self.commands.focus_job=None
  card=self.card_widgets.get(key)
  if card is not None:card.focus_set()

 def bind_card_navigation(self,widget,key,kind):
  widget.configure(takefocus=True)
  def select(target):
   if kind=='equipment':
    slot=next(s for s in self.selected.slots if s.name==target)
    self.inspect_slot(slot)
   else:
    row=next(r for r in self.character.inventory if r.container==self.selected and r.index==target)
    self.activate_card(self.card_widgets[target],lambda:self.inspect_inventory(row))
   self.card_widgets[target].focus_set()
  def navigate(event):
   keys=list(GRID) if kind=='equipment' else list(self.card_widgets)
   columns=4 if kind=='equipment' or self.inventory_layout.get()!='リスト' else 1
   index=keys.index(key);row,col=divmod(index,columns)
   dr,dc={'Up':(-1,0),'Down':(1,0),'Left':(0,-1),'Right':(0,1)}[event.keysym]
   nr,nc=row+dr,col+dc;target=nr*columns+nc
   if nr>=0 and 0<=nc<columns and 0<=target<len(keys):select(keys[target])
   return 'break'
  for direction in ('Up','Down','Left','Right'):widget.bind('<'+direction+'>',navigate)
  def decide(event):
   select(key)
   if kind=='equipment':self.open_slot_editor(next(s for s in self.selected.slots if s.name==key))
   else:self.show_evidence()
   return 'break'
  widget.bind('<Return>',decide)
  widget.bind('<Escape>',lambda e:(self.nav.focus_set(),'break')[1])

 def inspect_slot(self,slot):
  card=self.card_widgets.get(slot.name)
  if card is not None and card is not self.active_card:self.activate_card(card,lambda:None)
  if self.slot_editor is not None and self.active_slot!=slot.name:self.close_slot_editor()
  self.active_slot=slot.name;self.slot_edit_button.configure(state='disabled' if self.editor.blocked else 'normal')
  if self.slot_editor is not None:self.slot_editor.cancel()
  self.equipment_summary.show_selected(slot)
  a=slot.item_reference;view=present_slot(slot,self.selected.number,self.fix_plan)
  label=ACTION_STYLE[view.status][0]
  text=f'{label}\n{view.instruction}\n\n'
  if slot.action in ('keep','remove'):text+='動作: '+('変更しない' if slot.action=='keep' else '装備を外す')
  else:
   text+=f'登録アイテム\n{self.item_name(slot.item_id)}\n種類ID: {slot.item_id}\n収納: {BAGS.get(slot.container,slot.container)}\n内部スロット: {slot.index}\n\n持ち物データとの照合結果\n{OBSERVATIONS.get(a.observation,a.observation)}\n'
   for item in a.observed_item_ids:text+=f'指定位置のインベントリ保存情報: {item} {self.item_name(item)}\n'
   text+='\n同じ種類IDの候補\n'+('\n'.join(f'{BAGS.get(b,b)} / 内部スロット {i}' for b,i in a.candidates) or '持ち物データに候補なし')
   text+='\n\n照合対象: ローカルに保存されたインベントリ情報'
  if a.inventory_source:
   source=a.inventory_source;stamp=datetime.fromtimestamp(source['mtime_ns']/1e9).astimezone().isoformat()
   text+=f'\n\nインベントリファイル更新日時\n{stamp}\n\n取得元\n{source["path"]}\n\nSHA-256\n{source["sha256"]}'
  actions=[(f'{BAGS.get(b,b)} / {i} の候補を見る',lambda bag=b,index=i:self.open_inventory(bag,index)) for b,i in a.candidates]
  title=self.equipset_label(self.selected.number)+'\n'+SLOTS.get(slot.name,slot.name)+' / '+self.item_name(slot.item_id)
  primary=f'{label}\n\n{view.instruction}'
  if slot.action=='equip':
   primary+='\n\n装備本体\n'+(self.snapshot.items.get(slot.item_id,{}).get('description') or '説明が未取得')
   primary+='\n\n'+self.augment_text(slot)
  if view.change:
   x=view.change
   primary+=f'\n\n変更前\n{BAGS.get(x.before[0],x.before[0])} / {x.before[1]}\n\n変更案\n{BAGS[x.after[0]]} / {x.after[1]}'
  elif slot.action=='equip':
   primary+=f'\n\n登録先\n{BAGS.get(slot.container,slot.container)} / {slot.index}'
  if view.status in ('multiple','needs_review') and a.candidates:
   primary+='\n\n候補\n'+'\n'.join(f'{BAGS.get(b,b)} / {i}' for b,i in a.candidates)
  text+='\n\n補足\n照合条件: 収納・内部位置・種類ID。候補は読み取れたインベントリから検索します。保存情報の更新タイミングは調査中です。'
  self.show_detail(title,primary,actions[:8] if view.status in ('multiple','needs_review','fixable') else (),evidence=text)
  if not self.editor.blocked:self.edit_selected_slot()
 def render_macros(self,address):
  self.active_macro=None;self.edit_button.configure(state='disabled');self.equipment_name_button.configure(state='disabled');self.move_button.configure(state='disabled');self.active_slot=None;self.slot_edit_button.configure(state='disabled')
  book,palette=address;self.heading.configure(text=f'ブック {book} / パレット {palette}');self.subtitle.configure(text='マクロを選んで名前と6行を編集します。')
  macros=sorted((m for m in self.character.macros if (m.book,m.palette)==address),key=lambda m:(m.bank!='ctrl',m.key))
  for row,title in [(0,'Ctrl'),(2,'Alt')]:
   tk.Label(self.cards,text=title,fg=FG,bg=BG,font=('MS Gothic',11,'bold'),anchor='w').grid(row=row,column=0,columnspan=10,sticky='ew',padx=4,pady=(4,2))
  for i,m in enumerate(macros):
   key=f'{m.key if m.key<10 else 0}'
   empty=any(r.target_state=='empty' for r in self.macro_links.for_macro(m))
   frame=self.card((0 if m.bank=='ctrl' else 10)+m.key-1,key,(m.title.display or '（空欄）'),lambda macro=m:self.inspect_macro(macro),state='missing' if empty else None,compact=True)
   if hasattr(self,'commands'):self.commands.register_card(frame,m)
  if hasattr(self,'commands'):self.commands.paint()
  self.show_detail('マクロパレット',f'ブック {book} / パレット {palette}\n\nマクロをクリックしてタイトルと各行を確認してください。')
  if macros:self.inspect_macro(macros[0])
 def inspect_macro(self,macro):
  self.active_macro=macro_key(macro);self.edit_button.configure(state='disabled' if self.editor.blocked else 'normal')
  refs=self.macro_links.for_macro(macro)
  warning='\n'.join(f'⚠ {r.line}行目: {self.equipset_label(r.number)} は空です' for r in refs if r.target_state=='empty')
  body='\n\n'.join(f'{i+1}  {line.display or "（空欄）"}' for i,line in enumerate(macro.lines))
  if refs:body+='\n\n参照先\n'+'\n'.join(f'{r.line}行目 → {self.equipset_label(r.number)}'+('（未取得）' if r.target_state=='unavailable' else '') for r in refs)
  inventory=[r for r in self.macro_item_refs if r.address==macro_key(macro)]
  if inventory:body+='\n\nアイテム参照\n'+'\n'.join(f'{r.line}行目: {MACRO_ITEM_LABELS[r.state]}' for r in inventory)
  self.show_detail(macro.title.display or '（空欄マクロ）',(warning+'\n\n' if warning else '')+body)
  self.macro_panel.show(self.character.folder_id,macro)
  self.macro_panel.reference_text=(warning+'\n\n' if warning else '')+body
  self.update_edit_status()
 def copy_macro_book(self):
  from .book_copy_ui import open_book_copy
  return open_book_copy(self)
 def move_selected_equipment(self):
  if self.mode.get()!='装備セット' or not self.selected:return
  from .equipment_moves import vacant
  source=self.selected.number;folder=self.character.folder_id
  choices=[f'{e.number:03}' for e in self.character.equipsets if e.number!=source and vacant(e)]
  if not choices:dialogs.showwarning('移動先','名前が空または既定名で、全枠が「変更しない」の移動先がありません。',parent=self.app);return
  window=tk.Toplevel(self.app,background=BG);window.title('装備セットを移動');window.geometry('540x220')
  dialogs.child_navigation(window)
  dialogs.fit_to_screen(window)
  ttk.Label(window,text=f'移動元: {self.equipset_label(source)}',padding=12).pack(anchor='w')
  ttk.Label(window,text='移動先（空名または既定名・全枠が「変更しない」）',padding=12).pack(anchor='w')
  choice=ttk.Combobox(window,state='readonly',values=choices);choice.pack(padx=12,fill='x');choice.current(0);choice.focus_set()
  def preview():
   try:edit=background(self.app,self.editor.prepare_equipment_move,folder,source,int(choice.get()))
   except ValueError as e:dialogs.showerror('移動案',str(e),parent=window);return
   self.preview_edit(edit,lambda:self.editor.apply(edit),window)
  ActionButton(window,busy=True,text='移動と参照更新を確認',command=preview).pack(pady=12)
  self.move_dialog=(window,choice)
 def preview_combined_save(self,*,after_save=None):
  if not self.character:return
  try:
   self.macro_panel.apply_pending()
   plans=background(self.app,self.editor.prepare_writeback)
  except (OSError,ValueError,RuntimeError) as e:
   dialogs.showerror('書き戻しの確認',str(e),parent=self.app);return
  if not plans:
   if after_save:after_save()
   return
  window=tk.Toplevel(self.app,background=BG);window.title('ゲームへ書き戻す');window.geometry('980x700')
  dialogs.fit_to_screen(window)
  window.transient(self.app);window.grab_set();window.bind('<Escape>',lambda e:window.destroy());dialogs.after_idle_alive(window,window.focus_set)
  window.bind('<Destroy>',lambda e:self.commands.schedule_focus_restore() if e.widget==window else None)
  ttk.Label(window,text=f'{len(plans)}キャラの変更 · {sum(len(p.files) for p in plans)}ファイル',padding=12).pack(anchor='w')
  ttk.Label(window,text='表示した全キャラのゲームファイルを上書きします。変更前をバックアップし、失敗したキャラの書込みは復元します。\nFF11とPlayOnlineが終了している状態で、書き戻してよいですか？',padding=12,wraplength=900).pack(anchor='w')
  text=tk.Text(window,bg=PANEL,fg=FG,wrap='word',padx=12,pady=12)
  bar=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
  from .codecs import equipsets
  from .edit_values import value,slot_value
  for plan in plans:
   text.insert('end',self.character_labels()[next(i for i,c in enumerate(self.snapshot.characters) if c.folder_id==plan.character)]+'\n\n')
   if plan.books:
    for file in plan.books.files:
     text.insert('end',file.target+'\n')
     for change in file.changes:
      text.insert('end',f'ブック {change.number:02} の名前\n  前: {change.before}\n  後: {change.after}\n\n')
   for file in (plan.equipment.files if plan.equipment else ()):
    text.insert('end',file.target+'\n')
    for before,after in zip(equipsets(file.original,file.page),equipsets(file.replacement,file.page)):
     if value(before)==value(after):continue
     text.insert('end',f'装備セット {before.number:03}\n  名前: {before.title.display or "（空）"} → {after.title.display or "（空）"}\n')
     for a,b in zip(before.slots,after.slots):
      if slot_value(a)!=slot_value(b):text.insert('end',f'  {SLOTS[a.name]}\n    前: {self.slot_description(slot_value(a)[1:])}\n    後: {self.slot_description(slot_value(b)[1:])}\n')
     text.insert('end','\n')
   if plan.macro:
    for file in plan.macro.files:
     text.insert('end',file.target+'\n')
     for c in file.changes:
      b,p,bank,key=c.address;field='名前' if c.line==0 else f'{c.line}行目'
      text.insert('end',f'ブック {b:02} / パレット {p} / {bank.upper()} {key if key<10 else 0} / {field}\n  前: {c.before}\n  後: {c.after}\n\n')
  text.configure(state='disabled')
  def save():
   button.configure(state='disabled')
   try:backups=background(self.app,self.editor.writeback,plans,Path(__file__).resolve().parent.parent/'backups'/'moves',message='ゲームへ書き戻しています…')
   except (OSError,ValueError,RuntimeError) as e:
    self.refresh_edits();window.destroy()
    dialogs.showerror('書き戻しできませんでした',str(e)+'\n書き戻せた内容は保存済みです。残りの変更は画面に保持しています。',parent=self.app);return
   window.destroy();self.refresh_edits();self.footer.configure(text='ゲームへ書き戻しました。バックアップ: '+', '.join(map(str,backups)))
   if after_save and not self.editor.edit_status()[2] and not self.macro_panel.has_pending():after_save()
  button=dialogs.confirm_buttons(window,save,enabled=True)
 def slot_description(self,fields):
  action,item,bag,index=fields
  if action!='equip':return {'keep':'変更しない','remove':'外す'}.get(action,'未知の動作')
  return f'装備する: {self.item_name(item)} (ID {item}) / {BAGS.get(bag,bag)} / 内部位置 {index}'
 def edit_selected_slot(self):
  if self.mode.get()!='装備セット' or not self.selected or not self.active_slot:return
  if self.slot_editor is not None and self.slot_editor.slot_name==self.active_slot:return
  from .equipment_picker_ui import EquipmentPicker
  from .equipment_editing import preview_slot
  number=self.selected.number;name=self.active_slot;folder=self.character.folder_id
  slot=next(s for s in self.selected.slots if s.name==name)
  try:rows=background(self.app,self.editor.equipment_candidates,folder,name)
  except (ValueError,OSError) as e:
   dialogs.showerror('装備候補の取得',str(e),parent=self.app);return
  def preview(action,selection,parent):
   try:edit=background(self.app,self.editor.prepare_equipment_slot_edit,folder,number,name,action,selection)
   except ValueError as e:dialogs.showerror('入力内容',str(e),parent=parent);return
   try:background(self.app,self.editor.apply,edit)
   except (ValueError,OSError) as e:dialogs.showerror('装備の変更',str(e),parent=self.app);return
   self.close_slot_editor()
   self.refresh_edits()
   self.restore_card_focus(name)
  def compare(action,selection,label):
   candidate=preview_slot(self.selected,name,action,selection)
   self.equipment_summary.show_candidate(candidate,label,next(s for s in candidate.slots if s.name==name))
  self.close_slot_editor()
  self.slot_editor=EquipmentPicker(self.equipment_candidates_panel,SLOTS[name]+'の候補',slot,rows,self.snapshot.items,BAGS,preview,
   on_select=compare,on_cancel=self.equipment_summary.clear_candidate,on_details=self.show_equipment_detail,augment_path=self.augment_path)
  def back(event):
   self.slot_editor.cancel();self.card_widgets[name].focus_set();return 'break'
  self.slot_editor.listing.bind('<Escape>',back)
  self.slot_editor.entry.bind('<Escape>',back)
  self.slot_editor.listing.bind('<Return>',lambda e:(self.slot_editor.preview_button.invoke(),'break')[1])
 def open_slot_editor(self,slot):
  self.inspect_slot(slot)
  if self.slot_editor:self.slot_editor.listing.focus_set()
 def close_slot_editor(self):
  if self.slot_editor is not None:
   self.slot_editor.destroy();self.slot_editor=None
  self.equipment_summary.clear_candidate()
 def show_equipment_detail(self):
  window=tk.Toplevel(self.app,background=BG);window.title('装備・判定の詳細');window.geometry('780x650')
  dialogs.child_navigation(window)
  dialogs.fit_to_screen(window)
  if self.candidate_menu.index('end') is not None:
   ttk.Menubutton(window,text='候補の場所を見る',menu=self.candidate_menu).pack(anchor='e',padx=12,pady=6)
  text=tk.Text(window,wrap='word',bg=PANEL,fg=FG,padx=12,pady=12)
  scroll=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=scroll.set)
  scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
  text.insert('end',self.detail.get('1.0','end'))
  if self.evidence:text.insert('end','\n\n判定の詳細\n'+self.evidence[1])
  if self.slot_editor:
   action,identity=self.slot_editor.chosen()
   if action=='equip':
    row=next(r for r in self.character.inventory if (r.item_id,r.container,r.index)==identity)
    description=self.snapshot.items.get(row.item_id,{}).get('description') or '説明が未取得'
    text.insert('end','\n\n選択中の候補\n'+self.item_name(row.item_id)+'\n'+description+'\n'+self.augment_text(row))
  text.configure(state='disabled')
 def edit_selected_equipment_name(self):
  if self.mode.get()!='装備セット' or not self.selected:return
  number=self.selected.number;character=self.character.folder_id
  title=dialogs.askstring('装備セット名を編集',f'装備セット {number:03} の名前\n保存上限: 16バイト（CP932）',parent=self.app,initialvalue=self.selected.title.display)
  if title is None:return
  try:edit=background(self.app,self.editor.prepare_equipment_name_edit,character,number,title)
  except ValueError as e:dialogs.showerror('入力内容',str(e),parent=self.app);return
  try:self.run_edit(lambda:self.editor.apply(edit))
  except (ValueError,OSError) as e:dialogs.showerror('装備セット名の変更',str(e),parent=self.app)
 def edit_selected_macro(self):
  if self.active_macro:self.macro_panel.entries[0].focus_set()
 def preview_edit(self,edit,apply,parent=None,*,on_applied=None,after_close=None,summary=''):
  window=tk.Toplevel(self.app,background=BG);window.title(edit.label+' / 作業データ');window.geometry('900x600')
  dialogs.fit_to_screen(window)
  window.transient(self.app);window.grab_set();window.bind('<Escape>',lambda e:window.destroy());dialogs.after_idle_alive(window,window.focus_set)
  window.bind('<Destroy>',lambda e:self.commands.schedule_focus_restore() if e.widget==window else None)
  ttk.Label(window,text='表示した変更を作業データへ適用します。適用後はUndoで戻せます。\nゲームへは「ゲームへ書き戻す」から反映します。作業データを変更してよいですか？',padding=12,wraplength=820).pack(anchor='w')
  text=tk.Text(window,bg=PANEL,fg=FG,wrap='word',padx=12,pady=12)
  scrollbar=ttk.Scrollbar(window,command=text.yview);text.configure(yscrollcommand=scrollbar.set)
  scrollbar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
  if summary:text.insert('end',summary+'\n\n対象の変更\n\n')
  count=0
  from .edit_values import value
  for change in edit.changes:
   if value(change.before)==value(change.after):continue
   count+=1
   if change.kind=='books':
    text.insert('end',f'ブック {change.key[0]:02} の名前\n  前: {change.before.title.display}\n  後: {change.after.title.display}\n\n');continue
   if change.kind=='equipsets':
    from .edit_values import slot_value
    slot_fields=lambda s:slot_value(s)[1:]
    text.insert('end',f'装備セット {change.key[0]:03}  {change.before.title.display}\n')
    if change.before.title.display!=change.after.title.display:text.insert('end',f'名前\n  前: {change.before.title.display}\n  後: {change.after.title.display}\n')
    for before,after in zip(change.before.slots,change.after.slots):
     if slot_fields(before)!=slot_fields(after):text.insert('end',f'{SLOTS[before.name]}\n  前: {self.slot_description(slot_fields(before))}\n  後: {self.slot_description(slot_fields(after))}\n')
    text.insert('end','\n');continue
   b,p,bank,key=change.key
   text.insert('end',f'ブック {b:02} / パレット {p} / {bank.upper()} {key if key<10 else 0}  {change.before.title.display}\n')
   if change.before.title!=change.after.title:text.insert('end',f'名前: {change.before.title.display} → {change.after.title.display}\n')
   for n,(before,after) in enumerate(zip(change.before.lines,change.after.lines),1):
    if before!=after:
     text.insert('end',f'{n}行目\n  前: {before.display}\n  後: {after.display}\n')
     if before.display==after.display:text.insert('end',f'定型文ID: {format_token_ids(before.tokens)} → {format_token_ids(after.tokens)}\n')
   text.insert('end','\n')
  if not count:text.insert('end','変更対象なし')
  text.configure(state='disabled')
  def commit():
   try:background(self.app,apply)
   except (ValueError,OSError) as e:dialogs.showerror('変更の適用',str(e),parent=window);return
   if on_applied:on_applied()
   self.refresh_edits()
   window.destroy()
   if parent and parent.winfo_exists():parent.destroy()
   if after_close:after_close()
  dialogs.confirm_buttons(window,commit,enabled=bool(count) and not self.editor.blocked)
 def show_macro_inventory(self):
  c=self.character
  if not c:return
  all_refs=background(self.app,assess_macro_inventory,c,self.snapshot.items)
  refs=[]
  window=tk.Toplevel(self.app,background=BG);window.title('マクロの収納番号を確認・補正 / '+(c.display_name or c.folder_id));window.geometry('1050x700')
  dialogs.child_navigation(window)
  dialogs.fit_to_screen(window)
  ttk.Label(window,text='選択中のキャラクターの /equip を照合 · Fixは収納番号を追加・変更',padding=10).pack(anchor='w')
  filter_choice=ttk.Combobox(window,state='readonly',values=('Fix可能のみ','すべての参照'),width=24)
  filter_choice.current(0);filter_choice.pack(anchor='w',padx=10,pady=(0,8))
  listing=tk.Listbox(window,bg=PANEL,fg=FG,selectbackground=SELECT,height=14,exportselection=False)
  scrollbar=ttk.Scrollbar(window,command=listing.yview);listing.configure(yscrollcommand=scrollbar.set)
  scrollbar.pack(side='right',fill='y');listing.pack(fill='both',expand=True,padx=10)
  detail=tk.Text(window,height=9,bg=PANEL,fg=FG,wrap='word',padx=10,pady=10);detail.pack(fill='x',padx=10,pady=8)
  def select(event=None):
   if not listing.curselection():return
   r=refs[listing.curselection()[0]]
   selected_fix.configure(state='normal' if any(x.address==r.address and x.replacement is not None for x in all_refs) else 'disabled')
   detail.configure(state='normal');detail.delete('1.0','end')
   detail.insert('end',r.text+'\n'+MACRO_ITEM_LABELS[r.state]+'\n')
   for bag,index,item in r.candidates:detail.insert('end',f'{BAGS[bag]} / 内部位置 {index} / {self.item_name(item)}\n')
   if r.state=='same_storage_multiple':detail.insert('end','使い分けるには収納を分けてください。\n')
   if r.replacement:detail.insert('end','Fix案: '+r.replacement)
   detail.configure(state='disabled')
  listing.bind('<<ListboxSelect>>',select)
  def preview(selected=False):
   address=refs[listing.curselection()[0]].address if selected and listing.curselection() else None
   if selected and address is None:return
   edit=background(self.app,plan_macro_fixes,c,self.snapshot.items,address)
   self.preview_edit(edit,lambda:self.editor.macro_fixes(c.folder_id,edit,address),window)
  buttons=ttk.Frame(window);buttons.pack(fill='x',padx=10,pady=10)
  selected_fix=ActionButton(buttons,busy=True,text='選択マクロのFix案',command=lambda:preview(True),state='disabled');selected_fix.pack(side='left')
  ActionButton(buttons,busy=True,text='このキャラのFix案をまとめて確認',command=preview,state='normal' if any(r.replacement is not None for r in all_refs) else 'disabled').pack(side='left',padx=10)
  def open_macro():
   if not listing.curselection():return
   address=refs[listing.curselection()[0]].address
   self.character_choice.current(next(i for i,x in enumerate(self.snapshot.characters) if x.folder_id==c.folder_id))
   self.mode.set('マクロ');self.change_character();item=f'palette-{address[0]}-{address[1]}'
   self.macro_tree.selection_set(item);self.macro_tree.see(item);self.select_macro_palette()
   self.inspect_macro(next(m for m in self.character.macros if macro_key(m)==address));window.destroy();self.macro_panel.entries[1].focus_set()
  ttk.Button(buttons,text='マクロを開く',command=open_macro).pack(side='left')
  listing.bind('<Return>',lambda event:(open_macro(),'break')[1])
  def populate(event=None):
   nonlocal refs
   refs=[r for r in all_refs if filter_choice.current()==1 or r.replacement is not None]
   listing.delete(0,'end');selected_fix.configure(state='disabled')
   detail.configure(state='normal');detail.delete('1.0','end')
   if not refs:detail.insert('end','Fix可能な参照はありません。' if filter_choice.current()==0 else '参照はありません。')
   detail.configure(state='disabled')
   for r in refs:
    b,p,bank,key=r.address
    listing.insert('end',f'{b:02}-{p:02} {bank.upper()} {key if key<10 else 0} / {r.line}行目  [{MACRO_ITEM_LABELS[r.state]}]  {r.text}')
   if refs:listing.selection_set(0);select()
  filter_choice.bind('<<ComboboxSelected>>',populate)
  populate()
 def macro_reference_label(self,ref):
  return f'{ref.book:02}-{ref.palette:02} {ref.bank.upper()} {ref.key if ref.key<10 else 0} / {ref.macro_title or "（空欄）"} / {ref.line}行目'
 def show_macro_links(self):
  c=self.character
  if not c:return
  report=background(self.app,inspect_macro_set_links,self.snapshot,c)
  window=tk.Toplevel(self.app,background=BG);window.title('マクロと装備セットの参照確認 / '+(c.display_name or c.folder_id));window.geometry('950x620')
  dialogs.child_navigation(window)
  dialogs.fit_to_screen(window)
  ttk.Label(window,text='読み取ったマクロの /equipset・/lockstyleset を、同じキャラの装備セットと照合します。',padding=10).pack(anchor='w')
  ttk.Label(window,text='一覧で選択して「開く」を押すと、対象へ移動します。',padding=10).pack(anchor='w')
  notebook=ttk.Notebook(window);notebook.pack(fill='both',expand=True,padx=10,pady=10)
  sets={e.number:e for e in c.equipsets}
  entries=[('空セットへの参照',[(self.macro_reference_label(r)+' → '+self.equipset_label(r.number,c),r) for r in report.empty_references]),
           ('マクロ参照なし',[(self.equipset_label(n,c),n) for n in report.unreferenced])]
  for title,rows in entries:
   frame=ttk.Frame(notebook);notebook.add(frame,text=f'{title} ({len(rows)})')
   listing=tk.Listbox(frame,bg=PANEL,fg=FG,selectbackground=SELECT,exportselection=False)
   bar=ttk.Scrollbar(frame,command=listing.yview);listing.configure(yscrollcommand=bar.set)
   bar.pack(side='right',fill='y');listing.pack(fill='both',expand=True)
   for label,_ in rows:listing.insert('end',label)
   if not rows:listing.insert('end','該当なし')
   def open_selected(items=rows,box=listing):
    selected=box.curselection()
    if not selected or not items:return
    value=items[selected[0]][1]
    self.character_choice.current(next(i for i,x in enumerate(self.snapshot.characters) if x.folder_id==c.folder_id))
    self.mode.set('装備セット' if isinstance(value,int) else 'マクロ');self.change_character()
    index=next(i for i,x in enumerate(self.navigation) if (x.number==value if isinstance(value,int) else x==(value.book,value.palette)))
    if isinstance(value,int):
     self.nav.selection_clear(0,'end');self.nav.selection_set(index);self.nav.see(index);self.select_navigation()
    else:
     item=f'palette-{value.book}-{value.palette}'
     self.macro_tree.selection_set(item);self.macro_tree.see(item);self.select_macro_palette()
    if not isinstance(value,int):
     macro=next(m for m in self.character.macros if (m.book,m.palette,m.bank,m.key)==value.address)
     self.inspect_macro(macro)
    window.destroy()
    if isinstance(value,int):self.nav.focus_set()
    else:self.macro_panel.entries[1].focus_set()
   ttk.Button(frame,text='選択した対象を開く',command=open_selected,state='normal' if rows else 'disabled').pack(pady=8)
   listing.bind('<Double-Button-1>',lambda event,command=open_selected:command())
   listing.bind('<Return>',lambda event,command=open_selected:(command(),'break')[1])
 def show_unused_wardrobe(self):
  c=self.character
  if not c:return
  report=background(self.app,inspect_wardrobe_usage,self.snapshot,c)
  window=tk.Toplevel(self.app,background=BG);window.title('ワードローブの未参照アイテム / '+(c.display_name or c.folder_id));window.geometry('1000x680')
  dialogs.child_navigation(window)
  dialogs.fit_to_screen(window)
  counts=Counter(r.state for r in report)
  ttk.Label(window,text=f'{c.display_name or c.folder_id} · ワードローブ1〜8 · 未参照 {counts["unreferenced"]} / 参照候補あり {counts["possible"]} / 確認保留 {counts["incomplete"]}',padding=10).pack(anchor='w')
  ttk.Label(window,text='編集バッファの /equip と全装備セットを照合',padding=(10,0,10,8)).pack(anchor='w')
  choice=ttk.Combobox(window,state='readonly',values=('未参照','参照候補あり','確認保留'),width=22);choice.current(0);choice.pack(anchor='w',padx=10,pady=(0,8))
  frame=ttk.Frame(window);frame.pack(fill='both',expand=True,padx=10)
  listing=ttk.Treeview(frame,columns=('bag','slot','id','name'),show='headings',selectmode='extended',style='Macro.Treeview')
  for name,label,width in [('bag','収納',155),('slot','内部位置',85),('id','種類ID',85),('name','アイテム名',420)]:
   listing.heading(name,text=label);listing.column(name,width=width,anchor='w')
  bar=ttk.Scrollbar(frame,command=listing.yview);listing.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');listing.pack(fill='both',expand=True)
  detail=tk.Text(window,height=7,bg=PANEL,fg=FG,wrap='word',padx=12,pady=10);detail.pack(fill='x',padx=10,pady=8)
  visible=[]
  def select(event=None):
   selection=listing.selection()
   if not selection:return
   value=visible[int(selection[0])];row=value.item
   detail.configure(state='normal');detail.delete('1.0','end')
   detail.insert('end',self.item_name(row.item_id)+'\n'+BAGS[row.container]+f' / 内部位置 {row.index} / ID {row.item_id}\n')
   detail.insert('end','\n'.join(value.references) if value.references else '読み取れた /equip と全装備セットに参照がありません。')
   detail.configure(state='disabled')
  listing.bind('<<TreeviewSelect>>',select)
  def open_selected():
   selection=listing.selection()
   if not selection:return
   row=visible[int(selection[0])].item
   self.character_choice.current(next(i for i,x in enumerate(self.snapshot.characters) if x.folder_id==c.folder_id))
   self.open_inventory(row.container,row.index);window.destroy()
   self.update_edit_status();self.card_widgets[row.index].focus_set()
  open_button=ttk.Button(window,text='インベントリで開く',command=open_selected);open_button.pack(pady=(0,10))
  listing.bind('<Double-Button-1>',lambda event:open_selected())
  listing.bind('<Return>',lambda event:(open_selected(),'break')[1])
  def populate(event=None):
   nonlocal visible
   state=('unreferenced','possible','incomplete')[choice.current()]
   visible=[r for r in report if r.state==state]
   listing.delete(*listing.get_children())
   detail.configure(state='normal');detail.delete('1.0','end');detail.insert('end','該当なし' if not visible else '');detail.configure(state='disabled')
   open_button.configure(state='normal' if visible else 'disabled')
   for i,value in enumerate(visible):
    row=value.item;listing.insert('','end',iid=str(i),values=(BAGS[row.container],row.index,row.item_id,self.item_name(row.item_id)))
   if visible:listing.selection_set('0');select()
  choice.bind('<<ComboboxSelected>>',populate);populate()
 def augment_path(self,row):
  from .augment_presentation import path_label
  return path_label(self.augment_observations.get(self.character.folder_id),row)
 def switch_inventory_layout(self):
  if self.mode.get()=='インベントリ' and self.character and isinstance(self.selected,int):
   bag=self.selected;selected=self.active_inventory;self.clear_cards();self.render_inventory(bag)
   row=next((r for r in self.character.inventory if r.container==bag and r.index==selected and r.index in self.card_widgets),None)
   if row:self.activate_card(self.card_widgets[row.index],lambda:self.inspect_inventory(row))
 def inventory_row(self,ordinal,row):
  from .inventory_ui import item_row
  return item_row(self,ordinal,row,self.augment_path(row))
 def render_inventory(self,bag):
  from .equipment_editing import search_rows
  self.inventory_switch.pack(before=self.canvas_area,anchor='w',pady=(0,8))
  rows=search_rows([r for r in self.character.inventory if r.container==bag],self.snapshot.items,self.inventory_query.get());self.heading.configure(text=BAGS[bag])
  coverage={'loaded':'読込済み','missing':'未取得','unreadable':'読込不能'}.get(self.character.inventory_coverage.get(bag),'未取得')
  self.subtitle.configure(text=f'{len(rows)} アイテム · 収納の取得状態: {coverage}')
  if not rows:ttk.Label(self.cards,text='インベントリ保存情報に表示できるアイテム行がありません。').grid(row=0,column=0,pady=20)
  for i,row in enumerate(rows):
   self.card_widgets[row.index]=self.inventory_row(i,row) if self.inventory_layout.get()=='リスト' else self.card(i,f'スロット {row.index}',self.item_name(row.item_id),lambda r=row:self.inspect_inventory(r),row.item_id,badge=f'ID {row.item_id}',annotation=self.augment_path(row))
   self.bind_card_navigation(self.card_widgets[row.index],row.index,'inventory')
  self.show_detail(BAGS[bag],f'取得状態: {self.character.inventory_coverage.get(bag,"未取得")}\n\n{len(rows)}行を表示しています。\n内部スロット順で表示しています。\n個体情報は「個体情報を取り込む…」から追加できます。')
 def inspect_inventory(self,row):
  from .item_properties import describe_item
  self.active_inventory=row.index
  properties=describe_item(row,self.snapshot.items,self.augment_observations.get(self.character.folder_id),self.snapshot.augment_names,BAGS)
  self.inventory_properties.show(properties)
  can_compare=bool(self.character.equipsets and self.snapshot.items.get(row.item_id,{}).get('equip_slots')) and not self.editor.blocked
  self.inventory_compare_button.configure(state='normal' if can_compare else 'disabled')
  self.inventory_details_button.configure(state='normal')
  refs=[(e.number,s.name,s.item_reference) for e in self.character.equipsets for s in e.slots if s.action=='equip' and (s.container,s.index)==(row.container,row.index)]
  text=f'種類ID: {row.item_id}\n収納: {BAGS[row.container]}\n内部スロット: {row.index}\n\n{self.augment_text(row)}\n\nこの保存位置を指定する装備セット\n'
  text+='\n'.join(f'{self.equipset_label(n)} / {SLOTS[key]}\n  {OBSERVATIONS.get(a.observation,a.observation)}' for n,key,a in refs) or 'なし'
  summary='\n'.join(f'{self.equipset_label(n)} / {SLOTS[key]}' for n,key,a in refs) or 'なし'
  self.show_detail(self.item_name(row.item_id),f'{BAGS[row.container]} / {row.index}\n種類ID: {row.item_id}\n\n{self.augment_text(row)}\n\n参照している装備セット\n{summary}',evidence=text)
 def compare_inventory_item(self):
  if self.mode.get()!='インベントリ' or not self.character or self.editor.blocked:return
  row=next((r for r in self.character.inventory if r.container==self.selected and r.index==self.active_inventory),None)
  if row is None or not self.character.equipsets:return
  compatible=self.snapshot.items.get(row.item_id,{}).get('equip_slots',())
  if not compatible:return
  identity=(row.item_id,row.container,row.index)
  self.tabs.select('装備セット')
  if self.slot_editor is None:return
  name=self.active_slot if self.active_slot in compatible else next((s for s in GRID if s in compatible),None)
  if name is None:return
  self.inspect_slot(next(s for s in self.selected.slots if s.name==name))
  if self.slot_editor is not None and self.slot_editor.slot_name==name:
   self.slot_editor.query.set('')
   self.slot_editor.select_item(identity)
 def open_inventory(self,bag,index):
  self.inventory_query.set('')
  self.mode.set('インベントリ');self.change_mode();self.nav.selection_clear(0,'end');i=self.navigation.index(bag);self.nav.selection_set(i);self.nav.see(i);self.select_navigation()
  row=next((r for r in self.character.inventory if r.container==bag and r.index==index),None)
  if row:
   self.inspect_inventory(row);self.app.update_idletasks();card=self.card_widgets[index];height=self.cards.winfo_height();self.canvas.yview_moveto(max(0,card.winfo_y()/max(1,height)));card.configure(highlightbackground=ACCENT,highlightthickness=1)


def show(snapshot):
 configure(Path(__file__).resolve().parent.parent / 'work' / 'logs' / 'timings.jsonl')
 app=tk.Tk();app.view=ReaderWindow(app,snapshot);app.mainloop()
