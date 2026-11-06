# 開発時の参照順

1. 要件・採用設計の正本は構造化データで管理する。`python -X utf8 -m spec_manager search "対象語"`と`get ID`で対象の要件・設計を確認してから実装する。同じ要件を満たす別の設計へ変更できる。
2. 文書の役割と更新手順は [docs/README.md](docs/README.md) に従う。要件・設計の調査・保守は [maintain-specs](.agents/skills/maintain-specs/SKILL.md) を使う。
3. `tests/specs/` は正本から導いた検証仕様、`docs/requirements-traceability.md` は既存コード・テストへの索引として使う。
4. バイナリ処理は `docs/reference/local-formats.md` と `docs/reference/sources.json` を確認する。
5. 実データと合成テストの取扱いは SAFE-001 に従う。
6. UI変更時はD-10・D-15を確認する。時間のかかる処理は共通ワーカーへ渡し、UIスレッドで入力取得・画面更新を行う。変更した操作の実行スレッドと、長時間処理中の応答・入力排他・失敗後の復帰を合成GUIテストで確認する。
7. UIの設計・変更時は`search --kind policy`と`get DP-ID`で対象DPと採用理由を確認する。モックでの確認範囲はDP-06に従う。

日本語は対象と処理を具体的に書く。不要な否定文や仮説による注意を付け足さない。
