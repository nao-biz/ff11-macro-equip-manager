# D-01の機械的な測定

対象は本番Pythonの`ff11reader`と`spec_manager`。テスト・実験・外部ライブラリを集計に含めない。

```powershell
.venv/Scripts/python.exe -m pip install --target work/architecture-tools -r tools/architecture/requirements.txt
.venv/Scripts/python.exe -X utf8 -B tools/architecture/measure.py
```

結果は`work/architecture-baseline/`。JSONで比較可能な集計・依存辺・複雑度と、ツールの元出力を残す。初回の集計を`baseline-20261109.json`へ保存した。バージョンは推移依存も含め固定する。

| ツール | 機械検査 |
| --- | --- |
| Import Linter / Grimp | 禁止依存・循環依存、直接の依存先数と依存元数 |
| Pylint | protected-access、循環import、属性・公開メソッド・分岐・文の多さ、重複コード |
| Radon | 関数・メソッドの循環的複雑度とランク |

Import Linterは間接依存も検査する。関数内importも静的依存として含む。循環依存は起動時の循環importエラーと同義ではない。Pylintは選択した警告だけを既定しきい値で実行する。protected-accessは所有者をまたぐ内部参照の候補であり、全件が設計違反と確定するわけではない。Radonのメソッドとクラス集計の重複を除き、関数のランク分布を集計する。

## 初回結果（2026-11-09）

- 75モジュール、直接importの辺234。
- 指定したドメイン4モジュールからUI2モジュールへの直接・間接依存禁止: 適合。
- 循環依存禁止: 不適合。Import Linterは循環解消の候補として8依存の除去を提示した。これは循環の個数や修正の推奨ではない。
- protected-access警告63件。save_state.pyに42件。
- 属性が多いクラス16件、公開メソッドが多いクラス4件、重複コード警告3件。
- 複雑度対象577関数・メソッド。Dランク以上40件（D27、E8、F5）。最大はprepare_macro_saveの85。

## CIと評価方法

### GitHub上のレポート

- **Summary**: 合否条件の結果、モジュール・依存辺・関数・警告・複雑度ランクの集計、前回値と差分、複雑度上位10件を表示する。
- **Annotations**: Pylintと複雑度D以上の指摘をファイル・行付きで最大10件表示する。新規指摘を優先し、残りは規則・パス・行の順。観測用の警告として扱う。
- **Artifacts / architecture-measurements**: `report.md`に全指摘、`findings.json`に位置と内容、`comparison.json`に比較元・比較可否・集計差分を保存する。既存の集計JSON、依存辺、全複雑度、ツール元出力も保持する。

`previous.py`がGitHub CLIで比較元のArtifactを取得し、`report.py`が計測結果から表示を生成する。本番パッケージへの依存を追加せず、既存の合否条件を維持する。pushでは同じブランチ、PRでは取り込み先ブランチの、現在の実行IDより前に成功した直近のpush計測を使う。再実行時も同じ実行IDは除外する。比較元の実行・コミットをSummaryに明示する。

前回がない場合、Artifact取得不可・必要ファイル不足・計測版や対象範囲の相違がある場合は「比較不可」とし、前回値や差分を0で埋めない。指摘の同一性はパス・規則・対象名・メッセージで比較し、行番号移動は新規扱いにしない。同じ指摘の複数出現は件数を比較する。CIゲート失敗時も公開ステップを実行し、計測自体が未完了ならその旨を表示する。

ローカルでは計測後に `.venv/Scripts/python.exe -X utf8 -B tools/architecture/report.py` を実行する。比較元は既定で`work/architecture-previous/`、取得情報は`work/architecture-previous.json`。`GITHUB_STEP_SUMMARY`が設定されていれば要約を追記する。詳細は毎回計測結果のフォルダへ出力する。

重複コード警告は、Pylintが最後に走査したモジュールへ一括付与するため、報告内の先頭の対象範囲からAnnotationsのファイル・行を得る。比較には重複に参加するモジュールと各範囲の長さを使う。抜粋元の選択や行移動による偽の増減を避けるためで、同じ組み合わせ・長さの範囲内での内容変更は件数の増減には含めない。内容と全対象範囲は詳細Artifactで確認できる。

マクロ再検証入力の生成部品にはmacro-proposal契約を適用する。ロード・保存実行・UI・編集ストレージへの直接依存を禁止し、独立した値の組み立てに責務を限定する。入出力の所有権と実行時I/Oは振る舞いのテストで補完する。

snapshot-loading契約は保存用読込・共通デコード部品から保存実行・編集状態・UIへの直接依存を禁止する。対象範囲・原本照合・通常ロードとの同値性は`test_validation_loading`で検証する。

reader-boundary契約は共通ローダーから保存用方針への逆依存を禁止し、read-descriptors契約は読込要求と資料カタログから実行部品への依存を禁止する。不要なデコードを呼ばずに依存資料を検証できることと、偶然の読込が依存に混入しないことは`test_read_boundaries`で確認する。

save-inputs契約は保存入力の辞書選出・コピーからストレージ実装、保存実行、UIへの依存を禁止する。辞書選出の網羅性・計画一致・独立性は`test_save_inputs`で検証する。

`architecture.yml`で毎回集計とレポート保存を実行する。適合済みのdomain-ui契約、保存コーディネーターからストレージ実装への直接依存禁止、save_state.pyのprotected-access警告0件は、違反時にCIを失敗させる。循環・内部アクセス・複雑度など既存の警告は報告対象で、まだ全件を合否条件にしない。今後、責務単位の許可境界と改善対象を明確にして契約を追加する。今回の設定だけでD-01全体の適合を保証しない。

凝集性の意味（同じ理由で変更される処理か）は静的な点数から確定できない。属性数・メソッド数・複雑度・重複を責務分散や肥大化の候補として扱い、具体的な責務と照合する。依存数の多い共有ドメインや連携役を、数だけで不良としない。動的import、実行時の属性差替えや外部状態の共有には別の契約テストが必要。

文書: [Import Linter](https://import-linter.readthedocs.io/en/v1.10.0/contract_types.html)、[Pylint protected-access](https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/protected-access.html)、[Radon](https://radon.readthedocs.io/en/stable/api.html)。使用版の詳細はrequirements.txtと各ツールの出力を参照する。


master-values契約は起動単位の読み取り専用マスター値からI/O・編集状態・アプリケーション・UIへの依存を禁止する。寿命とキャラクター情報更新の分離、保存時のハッシュ検証は`test_master_lifecycle`で確認する。

book-copy契約はキャラ間コピー計画からUI・保存実行・Editorへの直接依存を禁止する。コピー先の参照判定、元の保持、上書き確認、ブック名を含む保存と復元は`test_book_copy`で確認する。名前保存の計画値は`save_plan`に置き、管理者ヘルパーから名前保存実装への循環を作らない。

character-clear契約はD-22の全消去計画からUI・保存実行・Editorへの直接依存を禁止する。入力不変・一括Undo/Redo・既存保存への接続はtest_character_clearで確認する。

augment-import-boundary契約はD-16の対応設定・Export選択・保存・名前投影からUI・編集・ゲーム保存への逆依存を禁止する。自動取得の世代取消と情報安定待ち、自動取り込みの対応照合・失敗保持・名前反映はtest_augment_import、test_auto_augments、test_augment_uiで確認する。

Windowerフォルダの永続化もaugment-import-boundary契約に含め、設定UIへの逆依存を禁止する。設定変更・保存失敗・初回案内・入力保持とワーカー境界はtest_windower_settings、test_windower_settings_uiで合成検証する。

同梱アドオン配置と自動ロード設定を担当するaddon_installerも同契約へ含める。設定保存を最後に実行し、通常の失敗では配置を復旧する。完了記録による再実行省略、版更新、原文バックアップ、対象外保持、途中失敗と復旧失敗はtest_addon_installerで検証する。

game-observation契約はD-23のプロセス・ファイル観測からUI・編集・ゲーム書戻しへの直接・間接依存を禁止する。監視は読取専用で、状態キューを受けるsync_uiが既存の排他ワーカーへ更新を依頼する。入力停止・自動再開・編集保持はtest_auto_sync、test_sync_ui、test_startupで検証する。

save-file-boundary契約は共通ファイル操作・トランザクションから形式別保存と上位調整への逆依存、save-plan-boundary契約は保存計画の値から実行部品への依存、elevation-boundary契約は親プロセスの権限要求から保存実装・補助プロセス入口への依存を禁止する。いずれも間接依存を含めCIで検査する。補助プロセスの`elevated_saving`が要求の検証と保存実装への振分けを担当し、`save_helper.py`が呼ぶ。既存JSONの型名・既定値と昇格後の再検証は`test_elevation`で確認する。

macro-save-valuesは純粋なマクロ変更判定・バイト変換から保存実行とロードへの依存、backup-restore-boundaryは共通復元から形式別保存への逆依存を禁止する。ui-operation-ownerとui-action-task-boundaryは状態所有者への依存方向とUIアクションからタスク実行への逆依存を検査する。text-encoding-boundaryは文字列符号化の独立性、transfer-boundaryは貼付け計画からファイル・UI操作への直接依存を検査する。transfer-boundaryだけは既存の一時編集セッション経由の間接依存を対象外とし、他の5件は間接依存も検査する。責務と検証結果は[Issue #2〜#5の検証記録](issues-2-5.md)を参照する。
