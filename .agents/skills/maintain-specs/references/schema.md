# 変更要求とレコード

変更要求は`base_revision`（取得時の版）、`reason`、`changes`（変更後のrecord全体の配列）を持つ。文書全体の説明・未確定事項を更新する場合だけ、`collections`に`overview`で取得した種類ごとのオブジェクトを含める。recordの取得元を示す`source`や、計算結果の`mentions`は変更要求へ含めない。

recordの必須項目:

| 項目 | 内容 |
|---|---|
| id | 安定したID。既存IDは維持する |
| kind | `requirement` / `design` / `policy` |
| title | 対象を表す見出し |
| status | 記載がない場合はnull。記載する場合は`summary`と`note`の文字列。実装・検証の根拠に合わせる |
| relations | 関係の種類をキー、対象ID配列を値にする |
| content | 本文ブロックの配列 |

relationsの種類:

- `basis`: この設計の対応要件・依存する設計。
- `adopts`: この要件で現在採用する設計。
- `related`: UI方針などの関連。
- `replaced_by`: 廃止した判断の代替先。

本文ブロックは`type`・`label`・`text`を持つ。`type`は条件`condition`、期待結果`outcome`、確認例`example`、補足項目`detail`。要件にはconditionとoutcomeが必要。まとまった説明・採用理由・表は`{"type":"markdown","text":"説明"}`で保持する。markdownブロックにlabelは付けない。書式文字列は本文の表現であり、種類・関係・必須項目の判定は構造化したフィールドで行う。

本文中のリンクは、個別IDに`[D-15](spec:D-15)`、種類全体に`[設計](spec-kind:design)`、リポジトリ内資料に`[資料](repo:docs/reference/local-formats.md)`を使う。Markdown出力では通常のリンクへ変換される。本文でのID言及も検査対象だが、関係を指定するときはrelationsへ記録する。

更新APIは`SpecService.plan(changes, base_revision, reason, collections=None)`で差分を作り、`apply(plan)`で同じ内容・版を再検証して適用する。CLIと将来のMCPでこの処理を共有する。旧Markdown版の変更案は現行のgetから作り直す。
