# 個体情報の出力形式 v1

DATA-003 / D-16。UTF-8 JSON、上限4 MiB。形式名 `ff11-inventory-export`、versionは1。

ルート: format, version, captured_at（UTC ISO8601、Z）, character（id: 1..4294967295, name, server:整数）, bags（17要素）。
収納: id（0..16、重複不可）, state（ready/unavailable/incomplete）, items（配列）。
個体: index（1..80、収納内重複不可）, item_id（1..65534）, count（1以上の整数）, extdata（24バイトの小文字hex）, decode_state（decoded/unsupported/error）, augments（文字列配列）, path（A..Dまたはnull）, rank（0..127またはnull）。
未取得収納のitemsは空配列。decodedはライブラリの解釈成功を意味する。能力の全文を得られる範囲はライブラリに従い、Pathだけの結果もある。生データは保持する。

取り込みは選択中キャラへの明示確認を必要とする。USERフォルダIDとサーバーのキャラIDの対応を推定しない。各収納のローカル取得状態が取得済みであり、全位置・種類IDが出力と一致する場合だけ補助情報を公開する。日時を常時付記し、同種類の入替と取得後の強化には再取得が必要なことを取り込み時に示す。

## 操作

`addons/ff11export` をWindowerのaddonsへコピーする。`//lua load ff11export` 後にエリア移動し、所持品読込完了後に `//ff11export export` を実行する。出力先は当該アドオンの `data` フォルダ。既存ファイルを上書きせず、連番で新規保存する。
アプリの「個体情報を取り込む…」でJSONを選び、出力元と選択中キャラを確認する。取り込んだ情報は再読み込み・アプリ再起動後も保持する。移動・強化後は再Exportして取り込む。

根拠: Windower FFXI Functionsのget_items/get_bag_info/get_info/get_player、Windower/Luaのextdata.lua、GearSwap/packet_parsing.lua、findAll/findAll.luaの0x01D読込完了通知。検証状況は[対応表のDATA-003](../requirements-traceability.md)を参照する。

## アプリ側の保存形式 v1

既定の保存先は `work/drafts/augment-observations/`。編集作業ファイルの親フォルダを基準とする。ファイル名はインストール識別子とキャラフォルダIDの組をSHA-256化した値。取り込みJSONの元ファイルは復元に必要ない。
JSONラッパーのformatは `ff11-augment-store`、versionは1。installation_key, folder_id, export（上記の出力形式v1）を持つ。読み出し時は対応キーと出力内容を検証する。サイズ上限は8 MiB。
起動・再読み込みのたびに収納を再照合する。不一致収納のデータも元の取得結果として保持し、新しいJSONの取り込みでキャラ単位に置換する。破損ファイルは保持して復元失敗を通知する。保存失敗時は一時ファイルを片付け、旧結果を維持する。
