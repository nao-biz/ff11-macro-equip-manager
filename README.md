# ff11-macro-equip-manager

FF11のローカルファイルを扱うWindowsデスクトップアプリ。

## 開発資料

要件・採用設計は構造化した正本を`python -m spec_manager`から参照・更新します。[開発資料の案内](docs/README.md)に検索方法と、検証仕様・既存実装との対応・ファイル形式への入口を記載しています。

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

## テスト

```powershell
.venv\Scripts\python -m pip install -r requirements-test.txt
.venv\Scripts\python -m unittest discover -s tests -v
```

通常は合成データを使います。インストール済みFF11を読み取る統合テストは明示的な有効化が必要です。`FF11_RUN_INTEGRATION=1` は合成GUIテストを有効にします。実ゲームを読むUIテストは別途 `FF11_RUN_GAME_INTEGRATION=1` が必要です。実機検証の取扱いはSAFE-001に従います。

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

Windower用の出力専用アドオンと取り込み操作は[出力形式・操作手順](docs/reference/augment-export.md)を参照してください。検証状況は[対応表のDATA-003](docs/requirements-traceability.md)を参照してください。
