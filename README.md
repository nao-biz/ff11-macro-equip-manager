# ff11-macro-equip-manager

FF11のローカルファイルを扱うWindowsデスクトップアプリ。

## できること

- マクロの名前・行の編集、コピー・貼り付け・移動、定型文の選択。
- キャラクター間で、ブック名・全マクロ・参照装備セットをまとめてコピー。
- 装備セットの名前・部位の編集、移動と参照マクロの更新。
- マクロと装備セットの参照確認、収納番号・参照位置の補正、ワードローブの未参照アイテム確認。
- Windowerの所持品更新・ログアウト直前の自動Export、ゲーム終了後の自動取り込みと、オーグメントを含む装備能力の表示・集計。

実装・検証の範囲と残っている確認事項は[対応表](docs/requirements-traceability.md)を参照してください。

## 開発資料

要件・採用設計・UI方針は[maintain-specs](.agents/skills/maintain-specs/SKILL.md)を入口に参照・更新します。[開発資料の案内](docs/README.md)に資料の役割と、要件・設計の分類・更新方針を記載しています。

## 起動

Python 3.12とTkinterを使用します。リポジトリ直下で実行します。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python reader.py
```

インストール先を指定する場合:

```powershell
.venv\Scripts\python reader.py --root "C:\path\to\FINAL FANTASY XI"
```

起動時は毎回ゲームデータを読み込みます。初回はWindower.exeがあるフォルダを選択して保存すると、Export先設定・アドオン配置・自動ロード設定が完了します。配置済みの版を記録し、同じ版の再配置を省略します。あとから画面右上の「設定」で変更できます。編集とUndo/Redoは起動中だけ保持し、「ゲームへ書き戻す…」から任意に保存できます。未保存の変更があるまま終了すると、書き戻し・破棄・編集継続を選べます。

## 基本操作と再読み込み

1. キャラクターを選び、マクロ・装備セットの対象を選択して編集します。
2. 変更を確認し、必要に応じてUndo/Redoで調整します。チェック・取り込みは共通操作から実行でき、対象キャラは画面の「チェック・取り込み対象」で確認できます。
3. FF11を終了し、「ゲームへ書き戻す…」で保存内容を確認して書き戻します。変更したページを保存し、依存資料の照合とバックアップを行います。

「ゲームデータを再読み込み」は、全キャラの未保存変更と入力中のマクロを破棄し、所持品・マクロ・装備セットを読み直します。実行前に確認画面が出ます。

キャラ間コピーは、コピー元のキャラクターを選び、「編集」→「別キャラへブックをコピー…」から元ブック・先キャラ・先ブックを指定します。参照する装備セットは同じ番号へコピーし、上書き内容と、そのセットを使うコピー先の別ブックを確認できます。適用後は一括でUndoできます。コピー先で装備の参照位置が一致しない枠は、参照位置の補正または枠編集を行ってから書き戻します。

アイテム名・定型文・能力表などのマスターは起動時に取得し、起動中は共有します。ゲームの更新後に最新マスターを取り込むには、アプリを起動し直してください。保存時にマスターの変更を検出すると、編集を画面に保持したまま保存を中止します。再起動すると未保存の編集は失われます。

## テスト

```powershell
.venv\Scripts\python -m pip install -r requirements-test.txt
.venv\Scripts\python -m unittest discover -s tests -v
```

通常は合成データを使います。インストール済みFF11を読み取る統合テストは明示的な有効化が必要です。`FF11_RUN_INTEGRATION=1` は合成GUIテストを有効にします。実ゲームを読むUIテストは別途 `FF11_RUN_GAME_INTEGRATION=1` が必要です。実機検証の取扱いはSAFE-001に従います。

依存関係・複雑度などの機械検査は[アーキテクチャ検査の手順](tools/architecture/README.md)、性能測定の経緯は[計測資料の案内](experiments/stack-evaluation/README.md)を参照してください。

2026-11-09時点の[最終検証記録](experiments/stack-evaluation/MASTER-LIFECYCLE.md)には、通常463テストの実行成功（104スキップ）、GUI35テスト、依存契約8件の成功を記録しています。隔離実データ3回の中央値は、直前の版に対して保存2.62秒→1.97秒、再ロード6.15秒→4.37秒でした。計測条件と、復旧試験で断続的に発生したWindowsアクセス拒否の未解決事項も同記録にまとめています。

## Property Test

編集・保存の生成テストだけを実行する場合:

```powershell
$env:FF11_RUN_INTEGRATION = "0"
.venv\Scripts\python -B -m unittest tests.test_editing_properties tests.test_saving_properties tests.test_property_support -q
```

seedを指定して再現する場合は、実行前に設定します。

```powershell
$env:FF11_PROPERTY_SEEDS = "42"
```

既定seedに戻す場合は `Remove-Item Env:FF11_PROPERTY_SEEDS` を実行します。失敗した操作列の縮小結果は `work/property-tests/` に保存されます。検証範囲は[対応表](docs/requirements-traceability.md)を参照してください。

## データ

ゲーム資産・実マクロ・持ち物・キャラ情報・作業ファイル・バックアップはGitへ登録しません。

本プロジェクトは有志による非公式ツールです。ゲームの名称・リソースの権利は各権利者に帰属します。

## 個体のオーグメント情報

Windower用アドオンは所持品の読込み完了とキャラ情報の安定を待って自動Exportします。初回にログイン観測でキャラとUSERフォルダの対応・出力先を登録すると、アプリがゲーム終了後に最新の情報とキャラ名を自動反映します。ゲーム起動中は操作を停止し、終了後は変更のあったデータだけを自動で読み込みます。[設定・操作手順](docs/reference/augment-export.md)と[検証状況](docs/requirements-traceability.md)を参照してください。
