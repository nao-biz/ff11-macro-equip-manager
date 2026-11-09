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

`architecture.yml`で毎回集計とレポート保存を実行する。現時点で適合しているdomain-ui契約は違反時にCIを失敗させる。循環・内部アクセス・複雑度など既存の警告は報告対象で、まだ全件を合否条件にしない。今後、責務単位の許可境界と改善対象を明確にして契約を追加する。今回の設定だけでD-01全体の適合を保証しない。

凝集性の意味（同じ理由で変更される処理か）は静的な点数から確定できない。属性数・メソッド数・複雑度・重複を責務分散や肥大化の候補として扱い、具体的な責務と照合する。依存数の多い共有ドメインや連携役を、数だけで不良としない。動的import、実行時の属性差替えや外部状態の共有には別の契約テストが必要。

文書: [Import Linter](https://import-linter.readthedocs.io/en/v1.10.0/contract_types.html)、[Pylint protected-access](https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/protected-access.html)、[Radon](https://radon.readthedocs.io/en/stable/api.html)。使用版の詳細はrequirements.txtと各ツールの出力を参照する。
