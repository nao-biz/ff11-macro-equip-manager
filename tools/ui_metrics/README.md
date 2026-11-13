# UI操作の処理回数

固定した合成ファイルと実際のTk画面で、操作に伴うアプリ側の処理回数を測る。OSの描画イベント・マウス移動の件数と所要時間は測定項目に含めない。性能低下を調べる入口として使い、一回の処理が重くなる変更や大規模データでの性能を保証するものではない。

```powershell
.venv/Scripts/python.exe -X utf8 -m tools.ui_metrics.measure
.venv/Scripts/python.exe -X utf8 -m tools.ui_metrics.report
```

測定結果は`work/ui-metrics/measurement.json`、前回比較は`comparison.json`、一覧は`report.md`。`--out`で測定先、reportの`--current`・`--previous`・`--metadata`で比較先を指定できる。測定は既定3回（`--repeats`で変更可能）。準備・終了後の画面破棄を除き、操作開始から最後のTkイベント処理までを数える。各回で新しい画面と一時フォルダを用意する。

| シナリオ | 計測する操作 |
|---|---|
| palette_transfer | パレット1を選択→コピー→パレット2を選択→上書き貼り付け |
| undo_redo | 準備で貼り付けを実施し、Undo→Redo |
| navigation | 装備セット→インベントリ→マクロのタブ切替→パレット2→1 |
| save_preview | 名前を変更済みのマクロの書き戻しプレビューを開いて閉じる |

合成データは`MoveFixture`の40マクロ・3ページの装備セットを使用。マクロ1の名前と本文を変更して、無変更の操作にならないようにする。実ゲームを読み書きせず、プレビュー後も合成ゲームファイルが不変であることを検証する。キャラ切替・装備候補検索は今後の追加対象。

| 項目 | 計測境界 |
|---|---|
| worker_calls | BackgroundTasks.call |
| selection_paints | SelectionCommands.paint（表示更新要求。実描画回数とは異なる） |
| workspace_rebuilds | ReaderWindow.change_mode（登録済みタブコールバックも含む） |
| macro_renders | ReaderWindow.render_macros |
| card_creations | ReaderWindow.card |
| snapshot_exports | Editor.snapshot（表示データ取得。内部のコピー数ではない） |
| widget_creations / widget_destructions | Tk BaseWidgetの生成・破棄呼出し。待機部品を含み、Tkルートを除く。既に破棄された部品への再呼出しも数える |

計測器はtoolsに置き、実行中だけクラスの入口を包む。本番コードは計測器へ依存しない。画面生成前に計測器を取り付け、登録時に保持されたコールバックも計測する。開始時にカウンターをゼロにし、UI・ワーカースレッドからの更新はロックで保護する。

## CIと比較

`ui-metrics.yml`はpush・pull_requestで独立実行する。Windows/Python 3.12、固定画面サイズ1440×900を使用。Summaryに各項目の最小〜最大・前回値・差分を表示し、`ui-operation-metrics` ArtifactへJSONとレポートを保存する。計測失敗時もレポートと失敗情報を残す。

比較元はpushでは同じブランチ、PRでは取り込み先ブランチの、現在より前に成功した直近のpush。アーキテクチャ計測と同じ取得処理を使い、workflow名とArtifact名を分ける。再実行時も同じrun IDを除外する。初回・取得失敗・期限切れは「比較不可」で、前回値と差分をゼロで埋めない。

計測器・合成フィクスチャの内容ハッシュ、測定形式、Python/OS/Tcl/Tkの版、シナリオと項目が一致する場合に比較する。計測器やシナリオを変更した直後は新しい基準を作る。本番コードの変更はハッシュに含めず、増減として観測する。環境差が残る可能性に備え、繰返しで揺れた項目は範囲のみ示し、差分を算出しない。

当初は回数の増加でCIを失敗させない。シナリオの操作結果不一致、Tkコールバックエラー、計測の失敗は失敗にする。安定した項目に上限を導入する場合は、採用理由と検証仕様を更新する。`test_ui_metrics`で比較可否・正負の差分・変動・取得失敗・計測を検証する。GitHub上の実行結果はpush後に確認する。
