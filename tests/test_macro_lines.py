"""Token-aware clipboard and whole-line UI operations on synthetic files."""
import os
import tkinter as tk
import unittest
from ff11reader.phrase_ui import PhraseEntry
from ff11reader.phrases import PhraseCatalog
from ff11reader.domain import Text
from ff11reader.text_editing import replace_range
from ff11reader.macro_text import patch_text
from tests.test_equipment_moves import MoveFixture

@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Enable synthetic Tk checks')
class ClipboardTests(unittest.TestCase):
    def test_reported_phrases_copy_cut_paste_and_external_replacement(self):
        app=tk.Tk()
        names={0x1B70:'イレース',0x1BC0:'オーラ',0x1FAB:'簡素清貧の章'}
        try:
            for identity,name in names.items():
                a=tk.Entry(app);a.pack();b=tk.Entry(app);b.pack()
                source=replace_range(Text('/ma ','','draft',()),4,4,'【'+name+'】',f'0201{identity:04X}')
                ca=PhraseEntry(a,source,PhraseCatalog(names));ca.set_value(source,0)
                cb=PhraseEntry(b,Text('','00'*61,'cp932',()),PhraseCatalog(names));app.update()
                a.selection_range(0,'end');a.event_generate('<<Cut>>');b.event_generate('<<Paste>>');app.update()
                self.assertEqual(ca.value.display,'');self.assertEqual(cb.value.tokens,source.tokens)
                raw=patch_text(bytes(61),'',cb.value.display,lambda p:names.get(int.from_bytes(p[2:],'big')),tokens=cb.value.tokens)
                self.assertIn(bytes.fromhex(f'FD0201{identity:04X}FD'),raw)
                b.selection_range(0,'end');b.event_generate('<<Copy>>')
                app.clipboard_clear();app.clipboard_append('external')
                cb.paste(whole=True);self.assertEqual(cb.value.display,'external');self.assertEqual(cb.value.tokens,())
                a.destroy();b.destroy()
        finally:app.destroy()

@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Enable synthetic Tk checks')
class LineTests(MoveFixture):
    def test_line_copy_swap_save_and_undo_preserves_unknown_tokens(self):
        from ff11reader.ui import ReaderWindow
        from ff11reader.edit_application import Editor
        from tests.test_saving import checksum
        path=self.folder/'mcr.dat';raw=bytearray(path.read_bytes())
        raw[28:89]=(b'/echo '+bytes.fromhex('FD00000001FD')).ljust(61,b'\0')
        path.write_bytes(checksum(raw));self.source=self.load();self.editor=Editor(self.source,self.base/'draft.json')
        app=tk.Tk()
        try:
            view=ReaderWindow(app,self.source,editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            view.commands.select('macro',(1,1,'ctrl',1));app.update()
            panel=view.macro_panel;original=panel.controllers[0].value
            panel.focus_line(1);panel.line_buttons['copy'].invoke()
            panel.focus_line(2);panel.line_buttons['paste'].invoke()
            self.assertEqual(panel.controllers[1].value.tokens,original.tokens)
            panel.line_buttons['down'].invoke()
            self.assertEqual(panel.controllers[2].value.tokens,original.tokens)
            panel.apply_pending()
            self.editor.save_combined(self.editor.prepare_combined_save('abc'),self.base/'backups')
            loaded=self.load().characters[0].macros[0]
            self.assertEqual(loaded.lines[2].tokens,original.tokens)
            self.editor.undo()
            self.assertEqual(self.editor.snapshot().characters[0].macros[0].lines[1].tokens,original.tokens)
            self.editor.undo()
            self.assertEqual(self.editor.snapshot().characters[0].macros[0].lines,self.source.characters[0].macros[0].lines)
        finally:app.destroy()

    def test_row_mode_enter_escape_and_clipboard(self):
        from unittest.mock import patch
        from ff11reader.ui import ReaderWindow
        app=tk.Tk()
        try:
            view=ReaderWindow(app,self.source,editor=self.editor)
            view.mode.set('マクロ');view.change_mode();app.update()
            view.commands.select('macro',(1,1,'ctrl',1));app.update()
            panel=view.macro_panel;entry=panel.entries[1];original=panel.controllers[0].value
            entry.focus_force();app.update()
            for key,target in [('Down',2),('Right',3),('Left',2),('Up',1),('Up',0),('Down',1)]:
                app.focus_get().event_generate('<'+key+'>');app.update()
                self.assertIs(app.focus_get(),panel.entries[target])
                self.assertEqual(panel.active_line,target)
            self.assertEqual(str(entry.cget('state')),'readonly')
            entry.insert('end','ignored');self.assertEqual(entry.get(),original.display)
            with patch('ff11reader.macro_editor_ui.ime_composing',return_value=False):
                panel.toggle_line(1)
                entry.insert('end',' changed')
                self.assertEqual(str(panel.line_buttons['copy'].cget('state')),'disabled')
                with patch('ff11reader.macro_editor_ui.ime_composing',return_value=True):
                    panel.toggle_line(1);self.assertEqual(panel.editing_line,1)
                panel.cancel_line(1)
                self.assertEqual(panel.controllers[0].value,original)
                panel.toggle_line(1);entry.insert('end',' accepted');panel.toggle_line(1)
            self.assertIsNone(panel.editing_line)
            self.assertEqual(entry.get(),original.display+' accepted')
            entry.event_generate('<<Copy>>')
            panel.entries[2].event_generate('<<Paste>>')
            self.assertEqual(panel.controllers[1].value.display,entry.get())
        finally:app.destroy()
