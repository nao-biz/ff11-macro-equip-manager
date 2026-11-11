import json
import unittest
from pathlib import Path
from lupa.lua51 import LuaRuntime

SOURCE = Path(__file__).resolve().parents[1] / 'addons/ff11export/login_observation.lua'


class LoginObservationTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().observer = self.lua.execute(SOURCE.read_text(encoding='utf-8'))
        self.lua.execute('''
            events={}; timers={}; writes={}; messages={}; enabled=true; fail=false
            info={logged_in=true,server=1}; player={id=123,name='Test'}
            w={addon_path='synthetic/',ffxi={
                get_info=function() return info end,
                get_player=function() return player end},
                file_exists=function(p) return enabled and p=='synthetic/observe-login.enabled' end,
                create_dir=function(p) assert(p=='synthetic/data/login-observation/') end,
                from_shift_jis=function(s) return s end,
                register_event=function(n,f) events[n]=f end,
                add_to_chat=function(_,s) messages[#messages+1]=s end}
            schedule=function(f,t) timers[#timers+1]={f=f,t=t} end
            io.open=function(p,m)
                assert(p:sub(1,33)=='synthetic/data/login-observation/' and m=='wb')
                if fail then return nil,'synthetic error' end
                return {write=function(_,s) writes[#writes+1]=s;return true end,
                        close=function() return true end}
            end
        ''')

    def test_opt_in(self):
        self.lua.execute('enabled=false; observer.start(w,schedule)')
        self.assertTrue(self.lua.eval('next(events)==nil'))

    def test_identity_and_delayed_samples(self):
        self.lua.execute("observer.start(w,schedule); events.login(); timers[1].f()")
        rows = [json.loads(self.lua.eval(f'writes[{i}]')) for i in (1, 2)]
        self.assertEqual(rows[0]['character_id'], 123)
        self.assertEqual(rows[0]['server'], 1)
        self.assertEqual(rows[1]['event'], 'login+2s')

    def test_logout_cancels_old_samples(self):
        self.lua.execute('observer.start(w,schedule); events.login(); player=nil; info={}; events.logout(); timers[1].f()')
        self.assertEqual(self.lua.eval('#writes'), 2)
        row = json.loads(self.lua.eval('writes[2]'))
        self.assertIsNone(row['character_id'])
        self.assertFalse(row['logged_in'])

    def test_io_failure_is_reported_without_interrupting_game(self):
        self.lua.execute('observer.start(w,schedule); fail=true; events.login()')
        self.assertEqual(self.lua.eval('#writes'), 0)
        self.assertEqual(self.lua.eval('#messages'), 1)
