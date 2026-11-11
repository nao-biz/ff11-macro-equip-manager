import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from lupa.lua51 import LuaRuntime
from ff11reader.augment_import import parse, MAX_BYTES
from ff11reader.augment_observation import reconcile
from ff11reader.domain import Character, InventoryRow

ROOT=Path(__file__).resolve().parents[1]

def fixture():
    return dict(format='ff11-inventory-export',version=1,captured_at='2026-11-03T00:00:00Z',
        character=dict(id=123,name='Test',server=1),bags=[dict(id=b,state='ready',items=[
        dict(index=i,item_id=21581,count=1,extdata='00'*24,decode_state='decoded',augments=['Path: '+p],path=p,rank=25)
        for i,p in [(1,'B'),(62,'C')]] if b==12 else []) for b in range(17)])

def character():
    return Character('abc',inventory=[InventoryRow(12,i,21581) for i in (1,62)],inventory_coverage={b:'loaded' for b in range(17)})

def encoded(value):return json.dumps(value).encode()

class ImportTests(unittest.TestCase):
    def test_paths_and_purity(self):
        c=character();before=copy.deepcopy(c)
        result=reconcile(parse(encoded(fixture())),c)
        self.assertEqual(result.accepted_bags,frozenset(range(17)))
        self.assertEqual([result.item(r).path for r in c.inventory],['B','C'])
        self.assertEqual(c,before)
        self.assertEqual(result.export.bags[12].items[1].extdata,'00'*24)
    def test_mismatch_and_unavailable(self):
        c=character();c.inventory[0]=replace(c.inventory[0],index=2)
        result=reconcile(parse(encoded(fixture())),c)
        self.assertNotIn(12,result.accepted_bags)
        self.assertIsNone(result.item(c.inventory[1]))
        c=character();c.inventory_coverage[12]='missing'
        self.assertNotIn(12,reconcile(parse(encoded(fixture())),c).accepted_bags)
    def test_permutations_preserve_instance_mapping(self):
        import random
        for seed in range(40):
            rng=random.Random(seed);data=fixture()
            rng.shuffle(data['bags'])
            for bag in data['bags']:rng.shuffle(bag['items'])
            c=character();rng.shuffle(c.inventory)
            result=reconcile(parse(encoded(data)),c)
            self.assertEqual({r.index:result.item(r).path for r in c.inventory},{1:'B',62:'C'})
            self.assertEqual(result.accepted_bags,frozenset(range(17)))

    def test_reject_malformed(self):
        cases=[]
        for key,val in [('version',2),('version',True),('captured_at','yesterday'),('bags',[])]:
            d=fixture();d[key]=val;cases.append(encoded(d))
        d=fixture();d['bags'][0]['id']=12;cases.append(encoded(d))
        for key,val in [('index',0),('index',True),('item_id',65535),('extdata','00'),('rank',128),('path','X'),('decode_state','error')]:
            d=fixture();d['bags'][12]['items'][0][key]=val;cases.append(encoded(d))
        d=fixture();d['bags'][12]['items'][1]['index']=1;cases.append(encoded(d))
        d=fixture();d['bags'][12]['state']='incomplete';cases.append(encoded(d))
        cases += [b'{"version":1,"version":1}',b'[]',b'null',b'X'*(MAX_BYTES+1)]
        for data in cases:
            with self.subTest(data=data[:80]),self.assertRaises(ValueError):parse(data)

class AddonTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().core=self.lua.execute((ROOT/'addons/ff11export/export_core.lua').read_text(encoding='utf-8'))
        self.lua.globals().auto_module=self.lua.execute((ROOT/'addons/ff11export/auto_export.lua').read_text(encoding='utf-8'))
        self.lua.execute("""
        api={get_info=function() return {logged_in=true,server=1} end,
        get_player=function() return {id=123,name='Test'} end,
        get_bag_info=function(b) return {enabled=true,max=80,count=b==12 and 2 or 0} end,
        get_items=function(b)
          local rows={}
          for i=1,80 do rows[i]={id=0} end
          if b==12 then
            rows[1]={id=21581,count=1,slot=1,extdata=string.char(1)..string.rep(string.char(0),23)}
            rows[62]={id=21581,count=1,slot=62,extdata=string.char(2)..string.rep(string.char(0),23)}
          end
          return rows
        end}
        decode=function(item) local p=item.slot==1 and 'B' or 'C'; return {path=p,rank=25,augments={'Path: '..p}} end
        function run(ready) return core.capture(api,decode,'2026-11-03T00:00:00Z',ready,function(s) return s end) end
        """)
    def test_lua_to_python_roundtrip(self):
        export=parse(self.lua.eval('run(true)').encode())
        self.assertEqual([r.path for r in export.bags[12].items],['B','C'])
        self.assertEqual([r.index for r in export.bags[12].items],[1,62])
        self.assertEqual(export.bags[12].items[0].extdata,'01'+'00'*23)
    def test_incomplete_and_decode_error(self):
        with self.assertRaises(Exception):self.lua.eval('run(false)')
        self.lua.execute("decode=function() error('unsupported') end")
        export=parse(self.lua.eval('run(true)').encode())
        self.assertEqual(export.bags[12].items[0].decode_state,'error')
        self.lua.execute('api.get_bag_info=function() return {enabled=true,max=80,count=3} end')
        export=parse(self.lua.eval('run(true)').encode())
        self.assertTrue(all(b.state=='incomplete' and not b.items for b in export.bags))
    def test_json_escaping(self):
        self.lua.execute('decode=function() return {augments={[[quote " slash \\ 日本語]]}} end')
        export=parse(self.lua.eval('run(true)').encode())
        self.assertIn('日本語',export.bags[12].items[0].augments[0])
    def test_adapter_gates_and_no_game_mutations(self):
        self.lua.execute("""
        package.preload.export_core=function() return core end
        package.preload.extdata=function() return {decode=decode} end
        package.preload.auto_export=function() return auto_module end
        package.preload.resources=function()return {servers={[1]={en='Synthetic'}}}end
        package.preload.user_directory_win32=function()return {new=function()
          return function()return {method='ffxi-user-directory-v1',installation='C:/synthetic',folder_id='abc'}end
        end}end
        _addon={};events={};messages={};scheduled={};writes={}
        windower={ffxi=api,addon_path='synthetic/',from_shift_jis=function(s)return s end,
         register_event=function(n,f) events[n]=f end,
         add_to_chat=function(_,s) messages[#messages+1]=s end,
         create_dir=function()end,file_exists=function()return false end,
         get_dir=function()return {} end}
        coroutine.schedule=function(f) scheduled[#scheduled+1]=f end
        io.open=function(path,mode)
          assert(path:sub(1,10)=='synthetic/' and mode=='wb')
          return {write=function(_,s) writes[#writes+1]=s;return true end,close=function()return true end}
        end
        os.rename=function()return true end
        os.remove=function()end
        """)
        self.lua.execute((ROOT/'addons/ff11export/ff11export.lua').read_text(encoding='utf-8'))
        self.lua.execute("events['addon command']('export')")
        self.assertEqual(self.lua.eval('#writes'),0)
        self.lua.execute("events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); scheduled[1]();events['addon command']('export')")
        self.assertEqual(len(parse(self.lua.eval('writes[1]').encode()).bags),17)
        self.lua.execute("events['logout'](); events['addon command']('export')")
        self.assertEqual(self.lua.eval('#writes'),2)

    def test_pending_completion_cancelled_by_zone(self):
        # Run the adapter harness first, then schedule a completion invalidated by a zone.
        self.test_adapter_gates_and_no_game_mutations()
        self.lua.execute("events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); events['incoming chunk'](0x00B,''); scheduled[2](); events['addon command']('export')")
        self.assertEqual(self.lua.eval('#writes'),2)

    def test_module_load_failure_preserves_original_cause_across_retries(self):
        self.test_adapter_gates_and_no_game_mutations()
        self.lua.execute("""
            package.loaded.user_directory_win32=nil
            package.preload.user_directory_win32=function()error('original module failure')end
        """)
        self.lua.execute((ROOT/'addons/ff11export/ff11export.lua').read_text(encoding='utf-8'))
        self.lua.execute("events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); scheduled[#scheduled](); for i=1,5 do scheduled[#scheduled]() end")
        self.assertIn('original module failure',self.lua.eval('messages[#messages]'))
        self.assertNotIn('loop or previous',self.lua.eval('messages[#messages]'))

    def test_publish_failure_reports_error(self):
        self.test_adapter_gates_and_no_game_mutations()
        self.lua.execute("events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); scheduled[#scheduled](); os.rename=function() return nil,'rename failed' end; events['addon command']('export')")
        self.assertIn('rename failed',self.lua.eval('messages[#messages]'))

    def test_automatic_completion_is_once_and_publishes_parseable_export(self):
        self.test_adapter_gates_and_no_game_mutations()
        self.lua.execute("events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); scheduled[#scheduled](); scheduled[#scheduled]()")
        self.assertEqual(self.lua.eval('#writes'),3)
        self.assertEqual(parse(self.lua.eval('writes[3]').encode()).character_id,123)
        self.assertFalse(any('ff11export auto:' in value for value in self.lua.globals().messages.values()))
        self.lua.execute("events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); scheduled[#scheduled]()")
        self.assertEqual(self.lua.eval('#writes'),3)

    def test_last_item_update_flushed_before_logout_and_old_timer_cancelled(self):
        self.test_adapter_gates_and_no_game_mutations()
        self.lua.execute("events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); scheduled[#scheduled](); scheduled[#scheduled]()")
        self.lua.execute("events['incoming chunk'](0x020,''); old_items=api.get_items; api.get_items=function(b) local r=old_items(b); if b==12 then r[63]=r[62];r[63].slot=63;r[62]={id=0} end;return r end; events['outgoing chunk'](0x00D,''); events['logout'](); scheduled[#scheduled]()")
        self.assertEqual(self.lua.eval('#writes'),4)
        self.assertEqual([r.index for r in parse(self.lua.eval('writes[4]').encode()).bags[12].items], [1,63])

    def prepare_cleanup(self):
        self.test_adapter_gates_and_no_game_mutations()
        self.lua.execute('''
            now=os.time()+3600; os.time=function()return now end
            os.date=function()return '2026-11-11T00:00:00Z' end
            removed={}; listings=0; files={}
            for i=1,5 do files[#files+1]='auto-1-123-20261110T000000Z-00000'..i..'.json' end
            for _,name in ipairs({'auto-2-123-20261110T000000Z-000001.json',
                'auto-1-456-20261110T000000Z-000001.json',
                'inventory-20261110T000000Z-000001.json',
                'auto-1-123-20261110T000000Z-000001.json.tmp',
                '../auto-1-123-20261110T000000Z-000001.json',
                'auto-1-123-20261112T000000Z-000001.json', 'login-observation'}) do
                files[#files+1]=name
            end
            windower.get_dir=function()listings=listings+1;return files end
            os.remove=function(path)removed[#removed+1]=path;return true end
            function emit_auto()
                events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3))
                scheduled[#scheduled]();scheduled[#scheduled]()
                events['incoming chunk'](0x020,'');scheduled[#scheduled]()
            end
        ''')

    def test_cleanup_keeps_two_previous_exports_and_scopes_deletion(self):
        self.prepare_cleanup()
        self.lua.execute('emit_auto()')
        self.assertEqual(set(self.lua.globals().removed.values()), {
            f'synthetic/data/auto-1-123-20261110T000000Z-00000{i}.json' for i in (1,2,3)})
        self.assertEqual(self.lua.eval('listings'), 1)
        self.lua.execute('now=now+3599;emit_auto()')
        self.assertEqual(self.lua.eval('listings'), 1)
        self.lua.execute('now=now+1;emit_auto()')
        self.assertEqual(self.lua.eval('listings'), 2)

    def test_cleanup_failure_does_not_retry_successful_export(self):
        self.prepare_cleanup()
        self.lua.execute("os.remove=function()return nil,'denied' end;emit_auto()")
        self.assertIn('ff11export cleanup:', self.lua.eval('messages[#messages]'))
        self.assertEqual(self.lua.eval('listings'), 1)
        self.assertEqual(self.lua.eval('#writes'), 4)

    def test_failed_publication_never_cleans_previous_exports(self):
        self.prepare_cleanup()
        self.lua.execute("os.rename=function()return nil,'rename failed' end;emit_auto()")
        self.assertEqual(self.lua.eval('listings'), 0)
        self.assertTrue(all(path.endswith('.tmp') for path in self.lua.globals().removed.values()))

    def test_debounce_exports_latest_value_and_flushes_pending_change(self):
        self.lua.execute('''
            timers={};outputs={};current=1
            local w={ffxi=api,add_to_chat=function()end}
            a=auto_module.new(w,function(f,d)timers[#timers+1]=f end,
                             function()outputs[#outputs+1]=current end)
            a.ready();timers[1]();current=2;a.changed();current=3;a.changed()
            timers[2]();timers[3]();current=4;a.changed();a.flush();timers[4]();a.flush()
        ''')
        self.assertEqual([self.lua.eval('outputs[%d]'%i) for i in (1,2,3)], [1,3,4])
        self.assertEqual(self.lua.eval('#outputs'),3)

    def test_capture_rejects_server_change_and_auto_incomplete(self):
        self.lua.execute('calls=0; api.get_info=function() calls=calls+1; return {logged_in=true,server=calls} end')
        with self.assertRaises(Exception):self.lua.eval('run(true)')
        self.lua.execute('api.get_info=function() return {logged_in=true,server=1} end; api.get_items=function() return {} end')
        with self.assertRaises(Exception):
            self.lua.eval("core.capture(api,decode,'2026-11-03T00:00:00Z',true,function(s)return s end,true)")

    def test_capture_rejects_storage_change_before_publication(self):
        self.lua.execute('''
            origin_calls=0
            function unstable_origin()
                origin_calls=origin_calls+1
                return {method='ffxi-user-directory-v1',installation='C:/synthetic',
                        folder_id=origin_calls==1 and 'abc' or 'def'}
            end
        ''')
        with self.assertRaises(Exception):
            self.lua.eval("core.capture(api,decode,'2026-11-03T00:00:00Z',true,function(s)return s end,true,unstable_origin)")

    def test_auto_waits_for_stable_server_and_cancels_old_generation(self):
        self.lua.execute('''
            timers={}; emitted=0; server=31; notices={}
            w={ffxi={get_info=function()return {logged_in=true,server=server,zone=1}end,
                     get_player=function()return {id=123,name='Test'}end},
               add_to_chat=function(_,s)notices[#notices+1]=s end}
            a=auto_module.new(w,function(f)timers[#timers+1]=f end,function()emitted=emitted+1 end)
            a.ready(); server=5; timers[#timers]();
        ''')
        self.assertEqual(self.lua.eval('emitted'),0)
        self.lua.execute('timers[#timers](); a.ready()')
        self.assertEqual(self.lua.eval('emitted'),1)
        self.lua.execute('a.invalidate(); a.ready(); a.invalidate(); timers[#timers]()')
        self.assertEqual(self.lua.eval('emitted'),1)

    def test_auto_retries_are_bounded_and_previous_export_survives(self):
        self.test_adapter_gates_and_no_game_mutations()
        self.lua.execute("os.rename=function()return nil,'rename failed' end; events['incoming chunk'](0x01D,string.rep('x',4)..string.char(1)..string.rep('x',3)); scheduled[#scheduled](); for i=1,5 do scheduled[#scheduled]() end")
        self.assertIn('ff11export auto:',self.lua.eval('messages[#messages]'))
        self.assertIn('rename failed',self.lua.eval('messages[#messages]'))
        self.assertEqual(parse(self.lua.eval('writes[1]').encode()).character_id,123)
