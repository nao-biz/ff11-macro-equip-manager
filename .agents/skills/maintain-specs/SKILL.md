---
name: maintain-specs
description: "このリポジトリの要件・採用設計・UI方針を調査・保守する。実装・テストの着手時にも使い、対象の正本・検証仕様・参照資料を確認する。"
---

# 要件・設計の保守

文書の役割・要件と設計の判別は [docs/README.md](../../../docs/README.md) に従う。利用者の要求を起点に、保証する結果の変更か、同じ結果を満たす方式の変更かを判断する。正本の参照・更新は以下の管理処理を使う。

## 調べる

リポジトリのルートで実行する。Windowsでは以下の`python`を`.venv/Scripts/python.exe`としてよい。

```sh
python -X utf8 -m spec_manager search "定型文"
python -X utf8 -m spec_manager get EDIT-007
python -X utf8 -m spec_manager related EDIT-007
python -X utf8 -m spec_manager overview
python -X utf8 -m spec_manager validate
```

検索結果から対象IDの`record`を取得し、関連ID・検証仕様・対応表の該当箇所を読む。`overview`には文書全体の説明と未確定事項がある。`related`の`relations`は明示的な関係、`occurrences`は本文などでの言及。どちらも一段の関連であり、意味上の影響範囲は内容から判断する。`truncated`なら`--limit`を増やす。`search --kind requirement/design/policy`で種類を絞れる。

対象に応じて次も参照する。IDの本文は`get`で取得し、関連する検証仕様まで確認する。

- 調査・実装・テスト: SAFE-001。
- UIの設計・変更: D-10・D-15と、`search --kind policy`で得た対象DP。モックの確認範囲はDP-06。
- ゲーム由来のデータ源の採用・更新: DATA-005。
- バイナリ処理: [ローカル形式](../../../docs/reference/local-formats.md)と[調査根拠](../../../docs/reference/sources.json)。

## 更新する

更新時は [データ形式](references/schema.md) を確認する。

1. 変更対象と理由を決め、関連する設計・検証仕様・実装の見直し範囲を特定する。採用理由は対象の設計の`content`へ記録する。採用済み・実装済み・検証済みを区別する。
2. `get`で得た`revision`と`record`から、UTF-8の変更要求JSONを作る。変更後のrecord全体を`changes`へ入れ、既存IDと種類を維持する。追加時も同じ形式を使う。廃止時はIDを残し、`status`に理由、`relations.replaced_by`に代替先を記録する。文書全体の説明・未確定事項を変える場合は`overview`から取得した対象種類の情報を`collections`へ入れる。
3. `plan`で差分と`issues`・`review`を確認する。機械検査は構造と参照を扱うため、要件の充足・分類・採用理由は本文で確認する。依頼済みの変更は、その範囲で適用まで進める。
4. `apply`で適用する。`conflict`なら最新の本文を取得し、変更意図を反映して案を作り直す。
5. 関連する検証仕様・対応表・コード・テストを更新し、`validate`と対象テストを実行する。検証仕様と対応表は直接編集する。実行・実機確認の記録は実際の根拠に合わせる。

変更要求の組み立て例（`record`を編集した後にJSONへ保存する）:

```python
from spec_manager import SpecService
result = SpecService(".").get("D-09")
record = result["record"]
# 必要なcontentやrelationsを変更する。
request = {"base_revision": result["revision"], "reason": "変更する理由", "changes": [record]}
```

```sh
python -X utf8 -m spec_manager plan work/spec-request.json --out work/spec-plan.json
python -X utf8 -m spec_manager apply work/spec-plan.json
```

`--out`には新しい保存先を指定する。出力JSONに差分と版を含む。全管理文書の版を照合するため、関連文書を先に直接編集した場合も変更案を作り直す。

人が一覧で読む場合は`python -X utf8 -m spec_manager render --out .spec-manager/view.md`でMarkdownを生成する。生成物には版が付く。以後の参照・更新も管理処理から最新のrecordを取得する。

`recovery_required`では`.spec-manager/pending.json`に原文と更新後が残る。`python -X utf8 -m spec_manager recover`で原文へ復旧する。`recovery_conflict`では該当ファイルの別の変更と復旧記録を比較し、保持すべき内容を確認してから整合させる。
