# Issue #1: 保存処理の循環依存

2026-11-13、`a03b95f`を変更前として、Issue #1の優先項目1を実施した。

## 責務と依存

D-05の「保存処理の依存境界」を採用した。`file_io`が指紋・ロック・検証付き置換を所有し、`file_transaction`と形式別保存が利用する。`save_plan`が権限要求で運ぶ計画型を保持する。親プロセスの`elevation`は権限要求と結果照合、補助プロセスの`elevated_saving`は要求検証と保存実行への振分けを担当する。

共通ファイル処理から装備保存への依存と、権限要求から形式別保存への依存を解消した。型名・フィールド・既定値、JSON version 1、保存の判定・ロック・バックアップ・復旧順序を維持する。移動した4共通関数と補助実行関数は、変更前後のAST一致を確認した。

## 静的解析

固定版の`measure.py`を変更前後に実行。元出力・依存辺・全複雑度・集計はそれぞれ`work/issue-1-before/`、`work/architecture-baseline/`に保存した。

| 項目 | 変更前 | 変更後 |
| --- | ---: | ---: |
| モジュール | 95 | 97 |
| 直接依存辺 | 308 | 312 |
| 合否対象の依存契約 | 12適合 | 15適合 |
| Pylint循環import警告 | 4 | 3 |
| Pylint警告合計 | 105 | 102 |
| protected-access | 28 | 28 |
| 重複コード警告 | 4 | 2 |
| 関数数 | 688 | 688 |
| 複雑度D以上 | 42 | 42 |

Issue本文の過去値ではなく、今回の変更前の値と比較した。追加した3依存契約は間接依存を含め適合し、既存12契約も維持した。`save_state.py`のprotected-access禁止ゲートも成功した。

Import Linterの全体循環検査は既存不適合が残る。変更後の循環解消候補は`equipment_moves → editing`、`ui_tasks → ui_actions`、`workspace_ui → macro_editor_ui`、`workspace_ui → ui`の4辺で、保存処理の辺は含まれない。これは循環の個数ではない。重複コードの残り2件は既存のマクロ・装備復元処理であり、Issueの優先項目3の対象。関数本体の複雑度は維持し、計測の除外やしきい値を変更していない。

## 振る舞いの検証

SAVE-002〜006、EX-UAC-01〜03、PT-21〜27を対象に合成データで検証する。移動後のゲーム終了確認へテストの差し替え先を更新し、ファイルアクセス隔離と禁止操作の監査は維持した。実ゲームの書込みと実際のUAC承認操作は実施していない。

- 対象4モジュール（`test_saving`、`test_elevation`、`test_macro_saving`、`test_equipment_saving`）: 42件実行、失敗なし、3件スキップ。
- 既存JSONの互換ケース追加後の`test_elevation`: 9件成功。
- `python -B -m unittest discover -s tests -q`: 577件実行、450件成功、127件スキップ、1064.083秒。ログは`work/issue-1-tests.log`。
- `spec_manager validate`: 75レコード、問題0件。`git diff --check`成功。

初回の対象テストでは、移動前の`require_game_closed`を差し替えていたテスト7ケースが失敗した。差し替え先を実際の呼出し先へ更新し、隔離監査を保った再実行と全体実行で成功を確認した。
