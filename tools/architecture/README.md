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

マクロ再検証入力の生成部品にはmacro-proposal契約を適用する。ロード・保存実行・UI・編集ストレージへの直接依存を禁止し、独立した値の組み立てに責務を限定する。入出力の所有権と実行時I/Oは振る舞いのテストで補完する。

snapshot-loading契約は保存用読込・共通デコード部品から保存実行・編集状態・UIへの直接依存を禁止する。対象範囲・原本照合・通常ロードとの同値性は`test_validation_loading`で検証する。

reader-boundary契約は共通ローダーから保存用方針への逆依存を禁止し、read-descriptors契約は読込要求と資料カタログから実行部品への依存を禁止する。不要なデコードを呼ばずに依存資料を検証できることと、偶然の読込が依存に混入しないことは`test_read_boundaries`で確認する。

save-inputs契約は保存入力の辞書選出・コピーからストレージ実装、保存実行、UIへの依存を禁止する。辞書選出の網羅性・計画一致・独立性は`test_save_inputs`で検証する。

`architecture.yml`で毎回集計とレポート保存を実行する。適合済みのdomain-ui契約、保存コーディネーターからストレージ実装への直接依存禁止、save_state.pyのprotected-access警告0件は、違反時にCIを失敗させる。循環・内部アクセス・複雑度など既存の警告は報告対象で、まだ全件を合否条件にしない。今後、責務単位の許可境界と改善対象を明確にして契約を追加する。今回の設定だけでD-01全体の適合を保証しない。

凝集性の意味（同じ理由で変更される処理か）は静的な点数から確定できない。属性数・メソッド数・複雑度・重複を責務分散や肥大化の候補として扱い、具体的な責務と照合する。依存数の多い共有ドメインや連携役を、数だけで不良としない。動的import、実行時の属性差替えや外部状態の共有には別の契約テストが必要。

文書: [Import Linter](https://import-linter.readthedocs.io/en/v1.10.0/contract_types.html)、[Pylint protected-access](https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/protected-access.html)、[Radon](https://radon.readthedocs.io/en/stable/api.html)。使用版の詳細はrequirements.txtと各ツールの出力を参照する。


master-values契約は起動単位の読み取り専用マスター値からI/O・編集状態・アプリケーション・UIへの依存を禁止する。寿命とキャラクター情報更新の分離、保存時のハッシュ検証は`test_master_lifecycle`で確認する。

book-copy契約はキャラ間コピー計画からUI・保存実行・Editorへの直接依存を禁止する。コピー先の参照判定、元の保持、上書き確認、ブック名を含む保存と復元は`test_book_copy`で確認する。名前保存の計画値は`save_plan`に置き、管理者ヘルパーから名前保存実装への循環を作らない。
