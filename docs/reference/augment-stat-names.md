# オーグメントの能力名と単位

VIEW-005 / D-17。英日対応はインストール済みゲームの辞書から取得し、`ff11reader/equipment_stat_names.py`が集計用に解釈する。

## 日本語名称の取得元

[Windower Resourcesのaugments.lua](https://github.com/Windower/Resources/blob/master/resources_data/augments.lua)には、同じIDの`en`と`ja`が対で入っている。[ResourceExtractor](https://github.com/Windower/ResourceExtractor/blob/master/Program.cs)が示す元DATは英語`0xD98C`、日本語`0xD914`。FTABLEで解決し、既存の`dmsg_names`で読み、同じ辞書IDを結合する。このIDをextdataのオーグメントIDとして扱わない。

数値1個の書式から能力名・単位・ダウン表現を取り出す。複合書式、条件付きの書式、言語間の欠落・対応競合は採用しない。名前の対応は起動時に取得してSnapshotへ共有する。所持品の再読み込みでは保持し、ゲーム辞書の変更はアプリ再起動で反映する。辞書がない場合も日本語の説明は集計し、対応不能な英語を集計外へ残す。

2026-11-06にローカルDATを読み、英語・日本語各2,048件、集計用の英語キー202件を確認した。読取前後のファイルハッシュは一致。辞書データ自体はGitへ登録しない。ソースの版はsources.jsonのS-AUG-DICTに記録する。

## Exportの表記と集計

出力元は[Windower extdata.lua](https://github.com/Windower/Lua/blob/live/addons/libs/extdata.lua)。2026-11-06取得時のblob SHAは`b2744e791b7779a49167411cc4a8c27dc3052088`。`augment_values`と`tools.aug.string_augment`で、引用符を含む名前がそのまま出力され、`percent`指定時だけ`%`が付くことを確認した。

| 出力例 | 集計先 | 単位の扱い |
|---|---|---|
| `"Mag. Acc."+10`、`"Mag.Atk.Bns."+5` | 魔命、魔攻 | 固定値 |
| `"Store TP"+5`、`"Subtle Blow"+3` | ストアTP、モクシャ | 表示値 |
| `Haste+2`、`"Dbl.Atk."+3`、`"Fast Cast"+4` | ヘイスト、ダブルアタック、ファストキャスト | 割合。出力の単位省略を補う |
| `Phys. dmg. taken -2`、`Magic burst dmg.+5%` | 被物理ダメージ、MBダメージ | 割合 |

表記ゆれはUnicode正規化、大小文字、空白、ピリオド、引用符を扱う。`Dbl.Atk.`などのWindower固有の略称はゲーム辞書の英語名へ結び付ける。日本語の集計項目の別名・省略単位は加算規則として管理する。IIなどの識別情報は保持し、HP/MPなどに明示された`%`は固定値と区別する。詠唱中断率の「ダウン」は負の値へ揃える。

原文は集計内訳に保持する。対応不明の英語、条件・対象付きの行、解釈できない末尾は集計外へ残す。検証は`tests/test_augment_dictionary.py`（DAT読取・欠落・起動中の共有・再起動）、`tests/test_equipment_stat_names.py`（辞書由来の対応・単位・競合・原文）、`tests/test_equipment_review_ui.py`（合成辞書を使う本番画面）。

説明文の混在行は`equipment_stat_parser.py`で分ける。D・隔の後のHP等や、別の未解釈効果と同じ行にある加算値も取得する。対象外・解析未対応・取得不足は内訳で区別し、解析不足は特定できる能力だけに関連付ける（EX-EVAL08・09）。

2026-11-06、ローカルDATのロスタム本体説明からHP+150を含む8項目を取得し、D・隔と条件付きのファントムロール効果は対象外、解析未対応は0件だった。個体能力を含めない合成の空オグメ観測を組み合わせた読取検証で、ユーザーのB/C個体の取得状況は検証対象外。読取前後のDATハッシュは一致した。
