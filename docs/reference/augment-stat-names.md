# オーグメントの能力名と単位

VIEW-005 / D-17。対応表は`ff11reader/equipment_stat_names.py`に集約する。

出力元は[Windower extdata.lua](https://github.com/Windower/Lua/blob/live/addons/libs/extdata.lua)。2026-11-06取得時のblob SHAは`b2744e791b7779a49167411cc4a8c27dc3052088`。`augment_values`と`tools.aug.string_augment`で、引用符を含む名前がそのまま出力され、`percent`指定時だけ`%`が付くことを確認した。

| 出力例 | 集計先 | 単位の扱い |
|---|---|---|
| `"Mag. Acc."+10`、`"Mag.Atk.Bns."+5` | 魔命、魔攻 | 固定値 |
| `"Store TP"+5`、`"Subtle Blow"+3` | ストアTP、モクシャ | 表示値 |
| `Haste+2`、`"Dbl.Atk."+3`、`"Fast Cast"+4` | ヘイスト、ダブルアタック、ファストキャスト | 割合。出力の単位省略を補う |
| `Phys. dmg. taken -2`、`Magic burst dmg.+5%` | 被物理ダメージ、MBダメージ | 割合 |

英語・日本語の能力名は対応表で照合する。表記ゆれの処理はUnicode正規化、大小文字、空白、ピリオド、引用符に限定する。IIなどの識別情報は保持する。HP/MPなどに明示された`%`は固定値と区別する。詠唱中断率の「ダウン」は負の値へ揃える。

原文は集計内訳に保持する。対応不明の英語、条件・対象付きの行、解釈できない末尾は集計外へ残す。既知の能力値を上限で打ち切らず、キャラ特性や支援を含む実効値は計算しない。合成入力の対応・単位・内訳の検証は`tests/test_equipment_stat_names.py`、日本語説明文と英語個体情報を組み合わせた本番画面の検証は`tests/test_equipment_review_ui.py`。
