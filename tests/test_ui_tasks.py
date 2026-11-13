"""Real Tk event-loop tests with synthetic work; no installed game access."""
from contextvars import ContextVar
import gc
import os
from threading import Event, get_ident
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch
from ff11reader.ui_tasks import background, tasks
from ff11reader.ui_actions import ActionButton


class TkThreadGuard:
    def __init__(self, tkapp):self.tkapp=tkapp;self.owner=get_ident()
    def __getattr__(self,name):
        value=getattr(self.tkapp,name)
        if not callable(value):return value
        def call(*args,**kwargs):
            if get_ident()!=self.owner:raise AssertionError('Tk access from worker')
            return value(*args,**kwargs)
        return call


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Synthetic Tk checks')
class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.app=tk.Tk();self.app.tk=TkThreadGuard(self.app.tk)
        self.app.geometry('480x240');self.errors=[]
        self.app.report_callback_exception=lambda *args:self.errors.append(args)
        self.entry=tk.Entry(self.app);self.entry.pack();self.app.update()

    def tearDown(self):
        self.app.destroy()
        del self.entry, self.app
        gc.collect()

    def test_work_thread_context_and_error_cleanup(self):
        owner=get_ident();marker=ContextVar('test_marker');token=marker.set('same-operation')
        try:
            result=background(self.app,lambda:(get_ident(),marker.get()))
            self.assertNotEqual(result[0],owner);self.assertEqual(result[1],'same-operation')
            def fail():raise ValueError('synthetic')
            with self.assertRaisesRegex(ValueError,'synthetic'):background(self.app,fail)
            self.assertFalse(tasks(self.app).running)
            self.assertIsNone(self.app.grab_current())
            self.assertEqual(background(self.app,lambda:42),42)
            self.assertFalse(self.errors)
        finally:marker.reset(token)

    def test_input_double_execution_close_and_animation(self):
        release=Event();runner=tasks(self.app);calls=[];samples=[]
        self.app.protocol('WM_DELETE_WINDOW',lambda:calls.append('closed'))
        protocol=self.app.protocol('WM_DELETE_WINDOW')
        button=ActionButton(self.app,busy=True,command=lambda:calls.append('edit'));button.pack()
        self.entry.bind('<KeyPress>',lambda e:calls.append('key'))
        def inspect():
            try:
                button.invoke()
                self.entry.event_generate('<KeyPress-a>')
                with self.assertRaisesRegex(RuntimeError,'実行中'):background(self.app,lambda:None)
                self.app.tk.call(self.app.protocol('WM_DELETE_WINDOW'))
                self.assertIn('完了してから',runner.screen.label.cget('text'))
                samples.append(float(runner.screen.progress[0]['value']))
            except Exception as exc:self.errors.append(exc)
        self.app.after(220,inspect)
        self.app.after(400,lambda:samples.append(float(runner.screen.progress[0]['value'])))
        self.app.after(500,release.set)
        background(self.app,lambda:release.wait(3))
        self.assertFalse(self.errors);self.assertFalse(calls)
        self.assertEqual(len(samples),2);self.assertNotEqual(*samples)
        self.assertEqual(self.app.protocol('WM_DELETE_WINDOW'),protocol)
        button.invoke();self.assertEqual(calls,['edit'])

    def test_previous_modal_grab_and_worker_start_failure_restore(self):
        window=tk.Toplevel(self.app);entry=tk.Entry(window);entry.pack()
        window.grab_set();entry.focus_force();self.app.update()
        tags=entry.bindtags()
        with patch('ff11reader.ui_tasks.Thread.start',side_effect=RuntimeError('start failed')):
            with self.assertRaisesRegex(RuntimeError,'start failed'):background(self.app,lambda:None)
        self.assertIs(self.app.grab_current(),window)
        self.assertEqual(entry.bindtags(),tags)
        self.assertFalse(tasks(self.app).running)
        self.assertEqual(background(self.app,lambda:17),17)
        self.assertIs(self.app.grab_current(),window)
        window.destroy()

    def test_only_resized_widgets_relayout_after_wait(self):
        configured=[]
        self.entry.bind('<Configure>',lambda event:configured.append((event.width,event.height)))
        background(self.app,lambda:None)
        self.app.update()
        self.assertEqual(configured,[])
        release=Event()
        def resize():
            self.entry.configure(width=40)
            self.app.after(40,release.set)
        self.app.after(10,resize)
        background(self.app,lambda:release.wait(2))
        self.app.update()
        self.assertEqual(configured,[(self.entry.winfo_width(),self.entry.winfo_height())])
        self.assertFalse(self.errors)

    def test_pointer_motion_during_work_does_not_cache_wait_cursor(self):
        tree=ttk.Treeview(self.app,columns=('value',),show='headings')
        tree.heading('value',text='Value');tree.column('value',width=180,stretch=False)
        tree.pack();self.app.update()
        separator=next((x,y) for y in range(30) for x in range(tree.winfo_width())
                       if tree.identify_region(x,y)=='separator')
        tree.event_generate('<Motion>',x=10,y=50)
        normal=tree.cget('cursor')
        tree.event_generate('<Motion>',x=separator[0],y=separator[1])
        self.assertNotEqual(tree.cget('cursor'),normal)
        release=Event()
        def move_and_click():
            tree.event_generate('<Motion>',x=separator[0],y=separator[1])
            tree.event_generate('<ButtonPress-1>',x=10,y=50)
            tree.event_generate('<ButtonRelease-1>',x=10,y=50)
            release.set()
        self.app.after(30,move_and_click)
        background(self.app,lambda:release.wait(2))
        tree.event_generate('<Motion>',x=10,y=50)
        self.assertEqual(tree.cget('cursor'),normal)
        self.assertFalse(self.errors)

    def test_leaving_sash_during_work_does_not_restore_wait_on_next_motion(self):
        pane=ttk.Panedwindow(self.app,orient='horizontal')
        pane.pack(fill='both',expand=True)
        pane.add(ttk.Frame(pane,width=100,height=100))
        pane.add(ttk.Frame(pane,width=100,height=100))
        self.app.update()
        pane.event_generate('<Enter>',x=10,y=10)
        normal=pane.cget('cursor')
        pane.event_generate('<Motion>',x=pane.sashpos(0),y=20)
        self.assertNotEqual(pane.cget('cursor'),normal)
        for fail in (False,True):
            with self.subTest(fail=fail):
                release=Event()
                def leave():
                    pane.event_generate('<Leave>',x=10,y=20)
                    release.set()
                def work():
                    release.wait(2)
                    if fail:raise ValueError('synthetic')
                self.app.after(220 if fail else 30,leave)
                if fail:
                    with self.assertRaisesRegex(ValueError,'synthetic'):background(self.app,work)
                else:background(self.app,work)
                pane.event_generate('<Enter>',x=10,y=20)
                pane.event_generate('<Motion>',x=10,y=20)
                self.assertEqual(pane.cget('cursor'),normal)
                pane.event_generate('<Motion>',x=pane.sashpos(0),y=20)
                self.assertNotEqual(pane.cget('cursor'),normal)
        self.assertFalse(self.errors)
