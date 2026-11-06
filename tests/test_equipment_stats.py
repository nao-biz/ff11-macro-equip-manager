import unittest
import struct
from dataclasses import replace
from ff11reader.domain import Slot, Equipset, Text
from ff11reader.equipment_stats import summarize, parse_line
from ff11reader.augment_observation import reconcile
from ff11reader.augment_import import parse
from ff11reader import codecs
from tests.test_augment_import import fixture,encoded,character

class EquipmentStatsTests(unittest.TestCase):
    def test_units_conditional_and_keep(self):
        slots=(Slot('main','equip',100,12,1,''),Slot('sub','equip',101,12,62,''),Slot('head','keep',None,None,None,''),Slot('feet','remove',None,None,None,''))
        equipment=Equipset(1,Text('Test','','cp932'),slots)
        report=summarize(equipment,{100:{'description':'防75 HP+50 STR+5\nHP+5% ヘイスト+3%\n潜在能力:\nMP+100'},101:{'description':'HP+30 STR+2\nペット:命中+40'}})
        totals={(n,u):v for n,u,v in report.totals}
        self.assertEqual(totals['HP',''],80)
        self.assertEqual(totals['HP','%'],5)
        self.assertEqual(totals['STR',''],7)
        self.assertEqual(totals['防',''],75)
        self.assertNotIn(('MP',''),totals)
        self.assertNotIn(('命中',''),totals)
        self.assertTrue(any('未確定' in line for _,line in report.excluded))
    def test_exact_augment_reference_and_path_not_counted(self):
        data=fixture();data['bags'][12]['items'][0]['augments']=['HP+10','Path: B']
        observation=reconcile(parse(encoded(data)),character())
        slot=Slot('main','equip',21581,12,1,'')
        equip=Equipset(1,Text('Test','','cp932'),(slot,))
        report=summarize(equip,{21581:{'description':'HP+20'}},observation)
        self.assertIn(('HP','',30),report.totals)
        self.assertTrue(any('Path: B' in line for _,line in report.excluded))
        report=summarize(replace(equip,slots=(replace(slot,index=2),)),{21581:{'description':'HP+20'}},observation)
        self.assertIn(('HP','',20),report.totals)
    def test_unknown_suffix_is_not_added(self):
        for line in ['HP+50 時々発動','HP+50～100','HP+50 MPをHPに変換','セット:HP+50','HP+50%以下']:
            self.assertIsNone(parse_line(line))
    def test_all_named_numeric_properties_and_decimals(self):
        from decimal import Decimal
        slots=(Slot('main','equip',100,12,1,''),Slot('sub','equip',101,12,2,''))
        equipment=Equipset(1,Text('Test','','cp932'),slots)
        items={100:{'description':'短剣スキル+242 魔命スキル+215\nウェポンスキルのダメージ+10%\n詠唱中断率-10% 新能力+1.1'},
               101:{'description':'短剣スキル+20 魔命スキル+10\nウェポンスキルのダメージ+5%\n詠唱中断率-5% 新能力+2.2'}}
        totals={(n,u):v for n,u,v in summarize(equipment,items).totals}
        self.assertEqual(totals['短剣スキル',''],262)
        self.assertEqual(totals['魔命スキル',''],225)
        self.assertEqual(totals['ウェポンスキルのダメージ','%'],15)
        self.assertEqual(totals['詠唱中断率','%'],-15)
        self.assertEqual(totals['新能力',''],Decimal('3.3'))
        self.assertEqual(parse_line('Accuracy+10 "Mag.Atk.Bns."+5'),[('命中','',10),('魔攻','',5)])

    def test_japanese_description_record(self):
        raw=bytearray(0x1400);struct.pack_into('<H',raw,0,10276)
        struct.pack_into('<IIIII',raw,0x30,2,0x14,0,0x50,0)
        name='テスト装備'.encode('cp932');desc='防75 HP+50 MP+20'.encode('cp932')
        raw[0x60:0x60+len(name)]=name;raw[0x9c:0x9c+len(desc)]=desc
        inverse=bytes(codecs.ROTATE.index(i) for i in range(256))
        item=codecs.item_records(bytes(raw).translate(inverse))[10276]
        self.assertEqual(item['description'],'防75 HP+50 MP+20')
        struct.pack_into('<I',raw,0x3c,0xfffffff0)
        self.assertIsNone(codecs.item_records(bytes(raw).translate(inverse))[10276]['description'])
