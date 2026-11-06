# 要件・設計と参照資料

## 仕様を調べる

要件・採用設計・UI方針は構造化した正本を管理処理から参照する。保守手順は [maintain-specs](../.agents/skills/maintain-specs/SKILL.md) に従う。リポジトリのルートで実行する。

```sh
python -X utf8 -m spec_manager search "定型文"
python -X utf8 -m spec_manager get EDIT-007
python -X utf8 -m spec_manager related EDIT-007
python -X utf8 -m spec_manager overview
python -X utf8 -m spec_manager validate
```

Windowsでは`.venv/Scripts/python.exe`を使用できる。`search --kind requirement/design/policy`で種類を絞る。`overview`は文書全体の説明と未確定事項、`related`は明記された関係と、本文・検証仕様・対応表での参照箇所を返す。意味上の影響範囲は対象の内容から判断する。

| 情報 | 役割 |
|---|---|
| requirement | 保証する結果・業務上の判定条件・外部制約 |
| design | 要件を満たすために現在採用する方式・責務・更新経路 |
| policy | UIの判断理由・採用案・未確定事項。本体反映時にdesignも更新 |
| [Example Test仕様](../tests/specs/example-tests.md)・[Property Test仕様](../tests/specs/property-tests.md) | 要件と採用設計から導いた具体例・不変条件 |
| [対応表](requirements-traceability.md) | 既存コード・テスト・検証不足への索引 |
| [ローカル形式](reference/local-formats.md)・[調査根拠](reference/sources.json) | バイナリ処理の技術的根拠 |

[個体情報の出力形式](reference/augment-export.md)はDATA-003の取り込み契約。UI・バイナリ変更時の追加参照はAGENTS.mdに従う。

## 要件と設計の判別・更新

別の方式でも利用者に保証する結果は要件、複数の実現方法から選んだ方式は設計とする。「処理中も画面が応答する」はVIEW-003、「共通ワーカーで実行する」はD-15。画面配置・キー割当・検索アルゴリズム・永続化方式は採用設計として扱う。ゲーム由来の外部制約と、アプリが選んだ安全側の制限も区別する。

結果を変える場合は要件を、方式を変える場合は設計と採用理由を更新し、関連する検証仕様・コード・テスト・対応表を合わせる。同じ結果を満たす方式変更では要件を維持する。UI方針の採用、実装、検証の完了は区別し、未決定の動作は具体化してから実装する。検証仕様には要件IDと、方式を検証する設計IDを併記する。

同じ規則・進捗を転記せず、保持元のIDや資料を参照する。具体的な型・メソッドはコード、形式上の事実は参照資料で管理する。

## 保守処理の採用設計

正本はGit管理する`specs/catalog.json`（schema_version 2）。ID・種類・状態・関係・条件・結果・本文を分ける。[SpecService](../spec_manager/service.py)がJSON互換の検索・検証・変更案・適用を提供し、CLIと独立する。将来のMCPも同じ処理を呼ぶ。保存は[JsonStore](../spec_manager/storage.py)が担当する。

変更案は差分・変更理由・関連箇所を持ち、適用直前に正本と関連文書の内容ハッシュを照合する。同ツールの操作は排他し、複数IDの更新を一つのJSONファイルへまとめて置換する。書込み失敗は原文へ戻し、途中終了時は復旧記録を使う。外部編集との競合時は内容と記録を保持する。構造・参照は機械検査し、要件充足と更新範囲はレビューする。

Markdownは`python -X utf8 -m spec_manager render --out .spec-manager/view.md`で必要時に生成する。出力には生成元の版を付け、検索・更新の入力に使わない。既存出力を更新するときは新しい出力名を指定する。`.spec-manager/`はGit対象外。旧正本のMarkdownが戻った場合はCIの`validate`で検出する。

合成検証: `python -m unittest tests.test_spec_manager -v`。スキーマ・参照、変更案の非変更性、競合、失敗・途中終了・復旧、Markdown出力、CLI経由の保守を検証する。
