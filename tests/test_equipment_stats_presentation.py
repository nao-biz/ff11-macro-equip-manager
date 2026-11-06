import unittest
from ff11reader.equipment_stats_presentation import display_totals, compact_properties


class EquipmentStatsPresentationTests(unittest.TestCase):
    def test_order_is_stable_and_preserves_all_values(self):
        names=['HP','STR','命中','魔命','防','短剣スキル','回復魔法スキル','盾スキル',
               '移動速度','リジェネ','未知能力A','未知能力B']
        rows=[(name,'',index) for index,name in enumerate(names)]
        self.assertEqual(display_totals(list(reversed(rows))),rows)
        changed=[(name,'',100-index) for index,name in enumerate(names)]
        self.assertEqual(display_totals(list(reversed(changed))),changed)
        self.assertCountEqual(display_totals(rows),rows)

    def test_units_stay_adjacent(self):
        rows=[('HP','%',5),('命中','',20),('HP','',50)]
        self.assertEqual(display_totals(rows),[('HP','',50),('HP','%',5),('命中','',20)])

    def test_requested_order_and_compact_rows(self):
        names=['攻','命中','飛攻','飛命','魔攻','魔命','防','回避','魔防','魔回避',
               '被ダメージ','被物理ダメージ','被魔法ダメージ','ヘイスト','敵対心',
               'ダブルアタック','トリプルアタック','ストアTP','モクシャ',
               'ウェポンスキルのダメージ','連携ボーナス','マジックバーストダメージ']
        rows=[(name,'',-5 if name.startswith('被') else 10) for name in names]
        self.assertEqual(display_totals(rows[::-1]),rows)
        lines=compact_properties(rows[::-1])
        self.assertLess(len(lines),len(rows))
        self.assertEqual(lines[0].split(),['攻撃','+10','命中','+10'])
        self.assertIn('WSダメージ +10','\n'.join(lines))
        self.assertIn('MBダメージ +10','\n'.join(lines))
        self.assertIn('被物理ダメージ -5','\n'.join(lines))
        long='非常に長い名前の未知のプロパティ'
        self.assertIn(long+' +1',compact_properties([(long,'',1)]))
