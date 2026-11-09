# 要件と実装・検証の対応

要件IDから既存コード・テスト・確認記録へ進むための索引。確認時期と範囲は各項目に記載する。保証する結果は[要件](README.md#仕様を調べる)、採用中の方式は[設計条件](README.md#仕様を調べる)。将来要件のコード欄は関連する既存基盤を示す。

実装状態・合成テスト・実機確認を分けて記載する。過去の実行結果は記録時点の証拠として扱い、変更対象の検証状況を確認する。キー・配置・内部方式の検証は当時の採用設計に対する結果であり、設計変更時は対応するD項目と検証仕様を見直す。

## 要件からコード・テストへの索引

| 要件 | 関連コード | 代表テスト | 確認範囲・不足 |
|---|---|---|---|
| SAFE-001 | [.gitignore](../.gitignore)、[file_transaction.py](../ff11reader/file_transaction.py) | [test_game_running_blocks_before_backup](../tests/test_macro_saving.py) | ゲーム終了条件を検証。Git除外と実機試験の承認は運用確認 |
| DATA-001 | [adapters.py](../ff11reader/adapters.py)、[codecs.py](../ff11reader/codecs.py)、[domain.py](../ff11reader/domain.py)、[ui.py](../ff11reader/ui.py) | [DecodingTests.test_macro_addresses_and_raw_lines](../tests/test_reader.py) | デコードの部分検証。アカウント単位の整理は未実装 |
| DATA-002 | [codecs.py](../ff11reader/codecs.py)、[dictionaries.py](../ff11reader/dictionaries.py)、[icons.py](../ff11reader/icons.py) | [DecodingTests.test_resolved_token_preserves_bytes_and_unknown_fallback](../tests/test_reader.py) | 文字解決を検証。アイコンは別の形式テストも参照 |
| DATA-003 | [出力アドオン](../addons/ff11export/ff11export.lua)、[取り込み](../ff11reader/augment_import.py)、[照合](../ff11reader/augment_observation.py) | [合成出力・取り込み](../tests/test_augment_import.py)、[合成GUI](../tests/test_augment_ui.py)、[個体情報の永続化](../tests/test_augment_store.py) | Lua 5.1で合成APIのJSON出力をPythonへ取り込み。2026-11-06、ユーザーがロスタムB/Cの出力・取り込みの実機確認完了を報告。個別の日本語・Rank・読込タイミングの検証記録は未記載 |
| DATA-004 | [adapters.py](../ff11reader/adapters.py)、[references.py](../ff11reader/references.py) | [ReferenceTests.test_loaded_empty_and_missing_and_unreadable_are_distinct](../tests/test_references.py) | 参照判定を検証 |
| DATA-005 | [adapters.py](../ff11reader/adapters.py)、[equipment_stat_names.py](../ff11reader/equipment_stat_names.py)、[データ源の根拠](reference/sources.json) | [辞書の更新・再読込](../tests/test_augment_dictionary.py)、[名称追加・変更](../tests/test_equipment_stat_names.py)、EX-D08・09／EX-EVAL07 | 本体辞書への追従は合成検証済み。第三者の継続保守・無償更新は採用時レビューの対象で、既存採用元全体の確認は未実施 |
| EQ-001 | [references.py](../ff11reader/references.py)、[domain.py](../ff11reader/domain.py) | [SlotStateTests.test_augments_do_not_affect_reference_state](../tests/test_slot_state.py) | 一致・優先順位はSlotStateTestsにも検証あり |
| EQ-002 | [fixes.py](../ff11reader/fixes.py)、[references.py](../ff11reader/references.py) | [FixTests.test_unique_target_in_every_storage_is_fixable](../tests/test_fixes.py) | 全収納の候補を検証 |
| EQ-003 | [fixes.py](../ff11reader/fixes.py)、[references.py](../ff11reader/references.py) | [FixTests.test_no_candidate_and_repeated_position_are_blocked](../tests/test_fixes.py) | 不足資料・キャラ分離は関連テストでも検証 |
| EQ-004 | [domain.py](../ff11reader/domain.py)、[references.py](../ff11reader/references.py)、[editing.py](../ff11reader/editing.py) | [FoundationTests.test_equipment_validation_and_derived_state_undo](../tests/test_edit_foundation.py) | 状態の再評価を検証 |
| LINK-001 | [macro_links.py](../ff11reader/macro_links.py) | [MacroLinksTests.test_reference_with_trailing_options](../tests/test_macro_links.py) | 空・remove・未知は同モジュールの別テストで検証 |
| LINK-002 | [macro_links.py](../ff11reader/macro_links.py)、[ui.py](../ff11reader/ui.py) | [MacroLinksTests.test_reverse_references_keep_addresses_and_lines](../tests/test_macro_links.py) | 参照位置を検証。画面上の読みやすさは手動確認 |
| LINK-003 | [macro_links.py](../ff11reader/macro_links.py) | [MacroLinksTests.test_isolation_and_no_mutation](../tests/test_macro_links.py) | キャラ分離と非変更を検証 |
| MAC-001 | [macro_inventory.py](../ff11reader/macro_inventory.py) | [MacroInventoryTests.test_storage_mapping_and_suffix_preservation](../tests/test_editing.py) | 番号対応と後続部分を検証 |
| MAC-002 | [macro_inventory.py](../ff11reader/macro_inventory.py)、[presentation.py](../ff11reader/presentation.py) | [MacroInventoryTests.test_state_matrix](../tests/test_editing.py) | 状態の組合せを検証 |
| MAC-003 | [macro_inventory.py](../ff11reader/macro_inventory.py)、[editing.py](../ff11reader/editing.py) | [EditingTests.test_batch_undo_redo_branch_and_raw_preservation](../tests/test_editing.py) | 履歴と元表現を検証。番号生成はMAC-001も参照 |
| MAC-004 | [ui.py](../ff11reader/ui.py)、[edit_application.py](../ff11reader/edit_application.py) | [EditingUITests.test_edit_preview_undo_redo_fix_and_reopen](../tests/test_editing_ui.py) | 合成GUIの操作を検証。初期フィルターの専用検証は不足 |
| EDIT-001 | [editing.py](../ff11reader/editing.py)、[edit_application.py](../ff11reader/edit_application.py) | [EditingTests.test_fix_recomputed_and_no_game_save_dependency](../tests/test_editing.py) | 保存処理への非依存を検証 |
| EDIT-002 | [editing.py](../ff11reader/editing.py)、[edit_values.py](../ff11reader/edit_values.py) | [FoundationTests.test_invalid_batch_is_atomic_even_through_generic_apply](../tests/test_edit_foundation.py) | 汎用変更案を含めて検証 |
| EDIT-003 | [editing.py](../ff11reader/editing.py) | [EditingTests.test_batch_undo_redo_branch_and_raw_preservation](../tests/test_editing.py) | 共通履歴・無変更は関連テストでも検証 |
| EDIT-004 | [edit_application.py](../ff11reader/edit_application.py)、[ui.py](../ff11reader/ui.py) | [test_editing_properties.py](../tests/test_editing_properties.py)、[test_session_ui.py](../tests/test_session_ui.py) | 起動ごとの新規編集、旧作業無視、終了時の書き戻し・破棄・継続、全キャラと入力、失敗時保持を合成検証 |
| EDIT-005 | [edit_application.py](../ff11reader/edit_application.py) | [test_reload.py](../tests/test_reload.py) | 再読込成功時の履歴初期化、取消・読込失敗時の保持、復旧未完了時の停止 |
| EDIT-006 | [editing.py](../ff11reader/editing.py)、[edit_application.py](../ff11reader/edit_application.py)、[ui.py](../ff11reader/ui.py) | [EditingUITests.test_edit_preview_undo_redo_fix_and_reopen](../tests/test_editing_ui.py) | マクロ編集と[装備セット名の編集・履歴・保存](../tests/test_equipment_names.py)を合成データで検証。[装備枠の個別編集・部位別選択・履歴・保存](../tests/test_equipment_slots.py)も合成データで検証。2026-10-29にユーザーが各枠編集の保存後、ゲーム内で認識されることを確認済み。2026-10-29にユーザーが名前編集・Undo/Redoと保存後のゲーム内反映を確認済み |
| EDIT-007 | [phrases.py](../ff11reader/phrases.py)、[text_editing.py](../ff11reader/text_editing.py)、[phrase_ui.py](../ff11reader/phrase_ui.py)、[macro_text.py](../ff11reader/macro_text.py) | [test_phrase_editing.py](../tests/test_phrase_editing.py) | 通常定型文・アイテム名の検索、読み、カテゴリ階層、初期フォーカス、ID保持を実装。2026-10-29に実機確認まで完了。詳細は下記「定型文入力」を参照 |
| SAVE-001 | [save_plan.py](../ff11reader/save_plan.py)、[macro_saving.py](../ff11reader/macro_saving.py)、[equipment_saving.py](../ff11reader/equipment_saving.py)、[ui.py](../ff11reader/ui.py) | [MacroSavingTests.test_unrelated_manual_edits_are_retained](../tests/test_macro_saving.py) | Fix限定保存と保留に加え、[test_manual_macro_saving.py](../tests/test_manual_macro_saving.py)で名前・各行の一般保存を検証。[test_equipment_names.py](../tests/test_equipment_names.py)で装備セット名の単独保存・Fixとの混在・保留を検証 |
| SAVE-002 | [macro_saving.py](../ff11reader/macro_saving.py)、[equipment_saving.py](../ff11reader/equipment_saving.py)、[file_transaction.py](../ff11reader/file_transaction.py) | [MacroSavingTests.test_stale_macro_inventory_and_plan_tamper_rejected](../tests/test_macro_saving.py) | マクロの競合を検証。装備保存にも同等テストあり |
| SAVE-003 | [file_transaction.py](../ff11reader/file_transaction.py) | [EquipmentSavingTests.test_candidate_changes_and_staging_failure](../tests/test_equipment_saving.py) | 装備保存の準備失敗を検証 |
| SAVE-004 | [macro_saving.py](../ff11reader/macro_saving.py)、[saving.py](../ff11reader/saving.py)、[codecs.py](../ff11reader/codecs.py) | [MacroSavingTests.test_token_zero_bytes_japanese_padding_and_length_limit](../tests/test_macro_saving.py) | [macro_text.py](../ff11reader/macro_text.py)で手編集のCP932・上限・既存定型文保持も検証。通常定型文・アイテム名の新規挿入とID保持は合成保存で検証。通常定型文とアイテム名のゲーム内表示・使用はユーザー確認済み |
| SAVE-005 | [file_transaction.py](../ff11reader/file_transaction.py)、[edit_application.py](../ff11reader/edit_application.py) | [EquipmentSavingTests.test_failed_rollback_keeps_pending_and_blocks_edits](../tests/test_equipment_saving.py) | 復旧待ちを検証。外部更新は復元テストも参照 |
| SAVE-006 | [edit_application.py](../ff11reader/edit_application.py)、[save_journal.py](../ff11reader/save_journal.py) | [test_save_journal.py](../tests/test_save_journal.py)、[test_saving_properties.py](../tests/test_saving_properties.py) | 起動中の保存後Undo、保存中断・記録削除失敗、前後指紋の照合、新規起動と履歴初期化 |
| VIEW-001 | [ui.py](../ff11reader/ui.py) | — | 収納順と全17収納の選択を合成GUIで確認。2026-11-02、ユーザー確認済み。専用自動テストなし |
| VIEW-002 | [ui.py](../ff11reader/ui.py)、[presentation.py](../ff11reader/presentation.py) | [PresentationTests.test_four_main_actions](../tests/test_presentation.py) | 状態表示の分類を検証。視覚品質は手動確認 |
| VIEW-003 | [ui.py](../ff11reader/ui.py)、[dialogs.py](../ff11reader/dialogs.py) | [test_dialogs.py](../tests/test_dialogs.py) | 親画面内モーダル、取消・入力、フォーカスとgrabの復帰、長文、起動時の表示を合成Tkで検証。実機で起動通知・再読込操作・本文量に応じたサイズをユーザーが確認済み |
| VIEW-004 | [paste_placement.py](../ff11reader/paste_placement.py)、[transfer_editing.py](../ff11reader/transfer_editing.py)、[selection_ui.py](../ff11reader/selection_ui.py)、[ui.py](../ff11reader/ui.py) | [test_paste_placement.py](../tests/test_paste_placement.py)、[test_selection_commands.py](../tests/test_selection_commands.py) | 配置判定、確認なしの貼り付け・削除、Undo/Redo、右クリック、入力欄との分離、共通保存を合成データで検証。2026-11-02、ユーザーが今回の変更のゲーム内動作を確認済み |
| VIEW-007 | [item_properties.py](../ff11reader/item_properties.py)・[item_properties_ui.py](../ff11reader/item_properties_ui.py)、[equipment_summary_ui.py](../ff11reader/equipment_summary_ui.py)、[ui.py](../ff11reader/ui.py) | [test_item_properties.py](../tests/test_item_properties.py)、[test_item_properties_ui.py](../tests/test_item_properties_ui.py)、EX-PROP01〜07 | 本体で選択追従・両表示・比較への受渡し・収納/キャラ切替・取得不足・列/色/ゼロ差分・改行・最小サイズ・6秒処理中の入力排他と失敗復帰を合成検証。採用方式はD-18。実データでの操作確認は未実施 |
| WARD-001 | [wardrobe_usage.py](../ff11reader/wardrobe_usage.py) | [WardrobeUsageTests.test_scope_and_both_reference_sources](../tests/test_wardrobe_usage.py) | 参照元と対象収納を検証 |
| WARD-002 | [wardrobe_usage.py](../ff11reader/wardrobe_usage.py) | [WardrobeUsageTests.test_edit_and_undo_recompute_without_cross_character_references](../tests/test_wardrobe_usage.py) | 再計算とキャラ分離を検証 |
| FUT-001 | [equipment_moves.py](../ff11reader/equipment_moves.py)、[editing.py](../ff11reader/editing.py)、[combined_saving.py](../ff11reader/combined_saving.py)、[edit_application.py](../ff11reader/edit_application.py)、[ui.py](../ff11reader/ui.py) | [test_equipment_moves.py](../tests/test_equipment_moves.py): EX-MOVE01〜06、PT-32初期範囲 | 装備セット移動・参照更新・Undo/Redo・一括保存を合成データで確認。2026-11-02、ユーザーが保存後のゲーム内動作を確認済み。パレット・マクロのブック間移動と同一キャラ内コピー、複数選択は合成データで検証。2026-11-02、今回の追加範囲もユーザーがゲーム内動作を確認済み |
| FUT-002 | — | — | 未実装。参照セットの同時コピーと番号衝突の扱いは未決定 |
| FUT-003 | [macro_inventory.py](../ff11reader/macro_inventory.py) | — | /equipの参照判定は実装済み。定型文候補の名前検索は実装済み。種類IDによる参照調査と誤記検出は未実装で、範囲・判定規則は未決定 |
| OBS-001 | [tracing.py](../ff11reader/tracing.py)、[edit_application.py](../ff11reader/edit_application.py) | [test_tracing.py](../tests/test_tracing.py) | 親子の操作ID・所要時間・失敗・個人データ非記録を検証。ゲーム保存内部の詳細区間は未実装 |
| PERF-001 | [edit_state.py](../ff11reader/edit_state.py)、[ui.py](../ff11reader/ui.py) | [test_persistent_edit_state.py](../tests/test_persistent_edit_state.py)、[benchmark_editor.py](../experiments/benchmark_editor.py) | 所有権・共有・編集検証失敗を検証。実機の応答はユーザー確認済み。数値基準は未確定 |

## 現在の未完了項目

| 要件 | 現在できること | 残件 |
|---|---|---|
| DATA-001 | キャラ別の閲覧・表示名・切替 | アカウント単位の整理 |
| FUT-002 | キャラ別の参照判定 | キャラ間コピー。参照セットの同時コピーと番号衝突の扱いの確定 |
| FUT-003 | /equipの参照判定、定型文候補の名前検索 | 種類IDによる参照調査、誤記検出。辞書未解決と未所持の区別・候補規則の確定 |
| OBS-001 | 編集・画面更新・ゲーム保存入口の区間計測 | ゲーム保存内部の詳細区間 |
| PERF-001 | 永続Mapによる編集高速化、待機カーソル。実機の応答をユーザー確認済み | 数値の合格基準。初期読込・全体取得・表示データの取得量依存 |

## 定型文入力（EDIT-007、D-09、SAVE-004）

| 対応 | 実装 | 検証 |
|---|---|---|
| 読み・名前の全体検索 | `dictionaries.auto_translate` → `LocalReader.phrase_readings` → `Snapshot.phrase_readings` → `PhraseCatalog` | [test_phrase_readings.py](../tests/test_phrase_readings.py)。ひらがな・カタカナ・漢字、読みの保持、かな名の検索 |
| カテゴリ階層・順序・名称 | [phrase_categories.py](../ff11reader/phrase_categories.py)、[phrases.py](../ff11reader/phrases.py) | 同テスト。魔法→アビリティ→アイテム→装備関連→その他、辞書カテゴリの統合、未知カテゴリ・同名別IDの保持 |
| キーボード操作 | [phrase_ui.py](../ff11reader/phrase_ui.py)。Tab直後は大分類へフォーカス。「すべて」でEnterなら全体検索欄へ移動 | 同テストと[test_phrase_editing.py](../tests/test_phrase_editing.py)。選択・検索・挿入・取消・フォーカス遷移 |
| アイテム候補 | [item_tokens.py](../ff11reader/item_tokens.py)、`PhraseCatalog` | [test_item_phrases.py](../tests/test_item_phrases.py)。ID逆変換、同名別ID、空名除外、Tabからの挿入。読みは補完しない |
| 編集値・履歴・保存 | `TextToken`、[text_editing.py](../ff11reader/text_editing.py)、[edit_values.py](../ff11reader/edit_values.py)、[macro_text.py](../ff11reader/macro_text.py) | test_phrase_editing.py、test_item_phrases.py。同表示のID変更、原子的置換・削除、Undo/Redo、旧作業無視、合成保存・再読込 |

ユーザー確認済み: カテゴリ階層での選択、アイテム名の検索・挿入、Tab直後の大分類フォーカス。2026-10-29、ユーザーがIME変換の確定ではマクロへ挿入されず、候補選択で挿入されることを確認。さらにユーザー自身が保存し、通常定型文とアイテム名の両方がゲーム内で正しく表示され使用できることを確認した。EDIT-007は実装・実機確認ともに完了。今回の完了更新ではアシスタントはゲームデータにアクセスしていない。漢字のあるアイテム名は表示名で検索し、読みデータを持つ通常定型文は読みでも検索する。

## 編集・保存の現行経路

マクロ名と6行の一般保存、およびマクロ収納番号Fix・装備位置Fixを実装。`macro_saving.py`と`equipment_saving.py`はプレビューと保存前の再検証を行い、`file_transaction.py`へバックアップ・置換・検証・復旧を委譲する。旧CLIも同じ実行処理を使用する。装備セット名・各枠の個別編集と保存も実装し、ゲーム内反映をユーザー確認済み。移動に伴う依存グループ保存は残件。

`macro_text.py`はCP932、名前8バイト・行60バイト、選択した定型文ID、元バイトを検証する。定型文を含む変更は辞書を依存資料として確認する。通常文字による名前変更へFix専用の持ち物一意性条件を要求しない。関連検証は[test_manual_macro_saving.py](../tests/test_manual_macro_saving.py)、[test_macro_saving.py](../tests/test_macro_saving.py)、[test_equipment_saving.py](../tests/test_equipment_saving.py)、定型文テスト群。

ユーザーはマクロ収納番号Fix、マクロ手編集、装備位置Fixのゲーム反映を以前に確認済み。今回追加した定型文のゲーム反映確認とは区別する。

編集ストアは`immutables.Map`で未変更部分を共有し、外部へは独立値を返す。編集・履歴は起動中だけ保持する。`test_editing_properties.py`の状態モデルは再起動時にゲーム値へ戻し、履歴を空にする。旧v1〜v4ファイルと破損ファイルは読まずに保持する。

## 解消済みの参照・保存の不整合

| 差分 | 修正 | 回帰テスト |
|---|---|---|
| GAP-01 | 明示収納の一意参照をその収納の資料で判定。全収納の完全性は番号追加・変更案で要求 | [test_reference_regressions.py](../tests/test_reference_regressions.py): test_explicit_storage_match_is_local、test_unrelated_invalid_candidate_does_not_hide_explicit_match（MAC-002、PT-09） |
| GAP-02 | ItemReferenceへreason/fix_targetを追加。assess_equipmentが評価し、Fix計画と表示が利用 | 同ファイル: test_slot_and_plan_share_blocking_reason、test_slot_owns_unique_target_and_exact_match_priority（EQ-004、D-01、EX-E08〜10、PT-03〜06） |
| GAP-03 | [inventory_observation.py](../ff11reader/inventory_observation.py)で収納読込・有効位置・重複検査を共有。使用状況は不正観測を先に保留 | 同ファイル: test_usage_never_confirms_invalid_observation（WARD-001、PT-30） |
| GAP-04 | Fix指紋をキー順の意味上の値で構築し、raw_hexを除外。変更案と保留一覧の順序も固定 | 同ファイル: test_fix_preview_ignores_order_and_raw_metadata（D-02、PT-02）。候補変更時の拒否も検証 |
| GAP-05 | 旧CLIのexecute_saveもexecute_batchへ委譲。original.datと旧receipt形式を維持し、検証失敗の復元・外部更新保護を共通化 | [test_saving.py](../tests/test_saving.py): test_legacy_save_delegates_to_shared_transaction、test_post_write_decode_failure_rolls_back_legacy_save、test_legacy_rollback_preserves_external_update（D-05、SAVE-003〜005） |

## 生成テストの実装範囲

| 仕様 | 実装 | 検証範囲 |
|---|---|---|
| PT-13 | [test_editing_properties.py](../tests/test_editing_properties.py) | 異なる対象を含む変更案に、古い前提・欠落対象・不正構造・重複を混ぜ、順序を変えて全体拒否と編集状態不変を確認 |
| PT-14/15/17 | 同ファイル | 複数キャラの編集、一括Fix、Undo/Redo、無変更、分岐、検証失敗、任意位置の再起動。独立モデルで値・履歴を照合 |
| PT-16/20/27 | [test_saving_properties.py](../tests/test_saving_properties.py) | 一部Fix・一括Fix・名前の手編集・保存・Undo/Redo・再起動・保存失敗を混在。保存可能差分と保留を分け、保存済み値・履歴・dirty・実バイトを照合 |
| PT-18 | test_editing_properties.py、test_reload.py | 最新ゲーム値から新規開始。旧作業を無視し、再読み込みの取消・失敗時は現在状態を保持 |
| PT-21 | test_saving_properties.py | 対象ファイル・収納・working・保存案・偽のゲーム起動状態を変更し、置換前の拒否を確認 |
| PT-22 | 同ファイル | マクロ/装備の1〜3ファイルについて、全バックアップ・一時ファイルの作成/fsync/読込検証地点へ障害注入。計72ケース。全準備が最初の置換に先行することをイベント列で確認 |
| PT-23 | 同ファイル | ページ・マクロ座標・行・装備セット内位置・部位・移動先収納をseedで変える。固定オフセットから独立に作った期待バイト、MD5、対象外バイトと照合 |
| PT-24 | 同ファイル | 現行の収納番号Fixについて、CP932の1/2バイト文字、内部ゼロを含む既知トークン、保存後59/60/61バイトを生成。この生成器は収納番号Fixが対象。手編集と新規定型文はtest_manual_macro_saving.py、test_phrase_editing.py、test_item_phrases.pyで別途検証 |
| PT-25 | 同ファイル | 3ファイルの各置換前後・検証地点の失敗、形式を保持した外部更新、復元失敗と操作停止を確認 |
| PT-26 | 同ファイル | 書込前・各置換後・復旧記録の削除前後の中断。全原本・全予定出力・混在を区別し、再起動時は履歴を復元しない |

[property_support.py](../tests/property_support.py)に固定seed、独立モデルとの照合、失敗操作列の縮小・再現記録、合成ルート外I/Oの拒否を実装済み。[test_property_support.py](../tests/test_property_support.py)で隔離と縮小を検証する。仕様の全項目を網羅したという意味ではなく、上表は各生成器が扱う範囲を示す。

## 追加検証・仕様確認が残る箇所

| 対象 | 現状と残件 |
|---|---|
| LINK-001/002、PT-08（旧SPEC-01） | `macro_links.py`の逆参照一覧は`not is_empty`を使うため、未知動作・欠落枠のあるセットも含む。PT-08の「既知の非空」との関係を要件で確定し、コードとテストをそろえる。今回の整理で解消済みにはしない |
| PT-01〜12、PT-30/31 | 参照・Fix・使用状況の固定例と前節の回帰はある。読込状態・重複位置・候補数・順序を組み合わせる広い生成検証が残る |
| PT-19、PT-32〜34 | 装備手動選択・移動・コピー・参照検索の機能実装に合わせて生成器を追加する |
| PT-24、PT-AT | 手編集・定型文の境界と固定seed生成は実装済み。辞書更新・全文字列形式の網羅や、OSの実ロック・停電などは検証範囲外 |
| VIEW-001〜003、MAC-004 | 合成GUIとユーザーによる実機確認はある。アコーディオン・空行減光・Fix初期フィルター・ホバー反復などの専用自動検証は部分的 |
| EX/PT全体 | 代表テストと主要生成器の対応を本書に記載。すべてのEX/PTを個別に網羅した対応付けは残る。ケース数とテストメソッド数を同一視しない |

合成GUIは`FF11_RUN_INTEGRATION`、実ゲームを読む`test_ui.py`は`FF11_RUN_GAME_INTEGRATION`へ分離済み。共通I/O隔離はProperty Test用基盤に実装している。全テストへの隔離適用まで完了したとは扱わない。

## アプリ内通知・応答・計測

- D-18 / DP-01〜05: [workspace_ui.py](../ff11reader/workspace_ui.py)で本体の画面構成、[theme.py](../ff11reader/theme.py)で本体・モック共通のテーマ、[macro_editor_ui.py](../ff11reader/macro_editor_ui.py)と[workspace_state.py](../ff11reader/workspace_state.py)で画面内入力・表示位置の保持を管理する。[test_workspace_ui.py](../tests/test_workspace_ui.py)でEX-U06〜08・10〜11、候補復元・検索・入力競合・失敗後の再試行・キャラ切替を合成GUI検証する。EX-U09は同テストと`test_dialogs.py`で確認する。
- `dialogs.py`に通知・確認・入力を集約。初回Map後に通知することで起動時の未表示を解消。短文は本文量に合わせ、長文は上限でスクロールする。[test_dialogs.py](../tests/test_dialogs.py)で初回表示・取消・入れ子・サイズ・フォーカス復帰を検証。実機の通知とサイズはユーザー確認済み。
- `ui_actions.ActionButton(busy=True)`で保存・保存プレビュー・編集適用などに待機表示を明示指定。通常のUIイベントへのフックは撤去。`tests/test_ui_actions.py`で軽い操作に待機処理が入らないこと、キー実行、入れ子・例外・子ウィンドウ破棄・ダイアログ入力待ちを検証。
- `tracing.py`は操作ID・親子区間・所要時間・成否を記録。ログは`work/logs/timings.jsonl`、約2MBで過去3世代を保持。ゲーム保存内部の詳細区間は残件。
- 自動保存廃止前の参考計測は8,000マクロで編集26.1ms、Undo26.1ms、Redo25.4ms（繰返し5回の中央値）。作業保存・表示用データ更新・dirty判定を含み、GUI描画・ゲーム保存を含まない。現行の測定用は[benchmark_editor.py](../experiments/benchmark_editor.py)。実機の応答はユーザーが十分と確認済み。数値の合格基準は未確定。

## 直近の検証記録

- 2026-11-07の起動ごとの編集への変更: 合成テスト374件を通常・GUI・変更箇所の追加実行に分けて確認し、すべて成功。実ゲーム用1件は未実行。終了時の全キャラ・入力中マクロの書き戻し／破棄／継続、失敗後の保持・再試行、旧作業ファイルを無視した部位編集、進行中の復旧記録の保護を含む。要件・設計66件の参照検査も成功。ゲームファイルへの書込みは行っていない。
- `ffe9e8d`のコミット前: `FF11_RUN_INTEGRATION=1`で全体176件中175件成功・実ゲーム用1件スキップ。保存先は合成データ。
- 初期フォーカス変更（`f7c69de`）: 定型文・読み・アイテムの関連19件成功。その後、ユーザーがTabから大分類を選ぶ操作を確認。
- 2026-11-06の本体UI反映: 合成GUIとモックを含む全334件中333件成功・実ゲーム用1件スキップ。正本63件の検査も成功。合成データで本体を起動し、3タブ、4×4配置、右側候補、6行入力、はい／いいえの確認を目視確認した。保存前の復旧記録を一度に確定する修正も含む。

[Example Test仕様](../tests/specs/example-tests.md)・[Property Test仕様](../tests/specs/property-tests.md)は要件から導いた検証仕様。[ローカル形式](reference/local-formats.md)・[調査根拠](reference/sources.json)はバイナリ処理の根拠として参照する。

## 保存時の権限要求（SAVE-003/005/006）

保存前の復旧記録はD-05に従い、`SaveJournal`が対象の変更前後の指紋だけを排他的に記録する。`test_save_journal.py`で記録失敗・並行保存・全原本・全出力・混在・旧pendingの照合を合成検証する。

`edit_application._save_checkpoint` → `elevation.execute_with_permission` → `save_helper.py`。マクロ・装備セットの画面保存で共通使用する。権限不足かつ全原本未変更の場合にUACを要求し、補助プロセスで既存保存関数を再実行する。要求はハッシュ照合付きJSON。親側は完了記録・バックアップ・保存後バイトを検証する。`tests/test_elevation.py`で両保存形式、取消・再試行、要求改変、競合、結果欠落からの復旧、Windows起動APIへの引数を合成データとモックで検証。実際のUAC表示・承認後のゲーム保存は未確認。

権限要求の検証結果: 全体回帰183件は既存の権限エラー期待1件がUAC取消応答で失敗、実ゲーム用1件スキップ。他181件は成功。該当テストを取消の模擬へ修正し、補助プロセスの単体起動も追加した後、権限要求・装備保存・マクロ保存・編集GUI・定型文・アイテムの関連48件が成功。実ゲームへの書込みは実施していない。


待機表示の適用範囲を見直した後、共通アクション・ダイアログ・編集GUI・定型文・読み・アイテムの関連34件が成功。全イベントの待機処理は撤去済み。ゲームデータは使用していない。

起動表示（VIEW-003、D-10）: [startup.py](../ff11reader/startup.py)で初回表示後にゲームデータを読み込み、新しい編集セッションを開始。[test_startup.py](../tests/test_startup.py)で表示中の応答、完了引渡し、起動エラー、途中終了を合成データで検証。

装備枠編集（EDIT-006、SAVE-001〜006）: [equipment_editing.py](../ff11reader/equipment_editing.py)が候補と選択検証、[equipment_ui.py](../ff11reader/equipment_ui.py)が入力、[equipment_saving.py](../ff11reader/equipment_saving.py)が形式変換と依存資料の検証を担当する。[test_equipment_slots.py](../tests/test_equipment_slots.py)で複数候補の手動選択、keep/remove、起動中の履歴と保存、辞書・収納の競合、ロールバック、合成GUI、PT-EQSの240ケースを検証。

装備セットの既定名: `test_default_named_equipment_destination`で010→013（Set013・全keep）のコピー案を検証。独自名・別番号の既定名・内容を持つ枠は保護する（EX-UIE13）。

EDIT-005: `tests/test_reload.py`で最新ゲーム値への切替、読込失敗時の状態保持、復旧待ち、合成UIの取消・確定・6秒以上の待機応答を検証する。D-14に沿って`Editor.reload`が成功時だけメモリ内のセッションを交換する。実ゲームでの確認は未実施。

VIEW-003 / D-10: `test_ui_actions.py`で共通処理中メッセージの表示、入力待ちの非表示、処理再開時の再表示、例外後の解除を合成Tkで検証。

VIEW-003 / D-15: [ui_tasks.py](../ff11reader/ui_tasks.py)の共通ワーカーで読込・編集・保存を実行する。待機中は入力と背後のレイアウト計算を停止し、Tkイベントループは継続する。[test_ui_tasks.py](../tests/test_ui_tasks.py)で実行スレッド、コンテキスト引継ぎ、重複実行拒否、入力遮断、終了要求、例外と開始失敗後の復帰、既存モーダルのgrab復元を検証。[test_reload.py](../tests/test_reload.py)で6秒超のCPU負荷と連続リサイズを含む再読み込みを検証する。2026-11-03の合成GUI検証では6.41秒の処理中にUIタイマーが70回実行され、最大間隔は0.156秒だった。Tkへのワーカーからのアクセスはテスト用ガードで拒否する。実ゲームデータによる再確認は未実施。

2026-11-03: 共通ワーカー導入後、合成GUIを含む全262テストを実行し成功（実ゲーム読込テスト1件をスキップ）。全体実行中の長時間再読み込みは6.45秒、UIタイマー66回、最大間隔0.156秒。

再発防止（D-15、EX-UIBG04）: [test_ui_execution.py](../tests/test_ui_execution.py)がUI経由の再読み込み・編集・Undo/Redo・保存プレビュー・保存・リセットの実行スレッドを検証する。[tests.yml](../.github/workflows/tests.yml)に合成GUIの専用ステップを追加し、長時間応答・入力排他・復帰と併せて毎回実行する。2026-11-03、CIと同じ17テストがローカルで成功。ワーカーを意図的に迂回した検証では、編集のUIスレッド実行を検出した。GitHub上の実行は次回プッシュ後に確認する。

VIEW-002の追加表示: `augment_presentation.path_label` と `inventory_ui.item_row` を `ui.py` から利用。`tests/test_augment_ui.py` で枠内Path、表示切替、行クリック、表示方式の維持を合成GUIで確認。

VIEW-005 / D-17: `LocalReader.load_augment_names`がゲーム内の英日辞書を読み、`equipment_stat_names.py`が同じ辞書IDから能力名を対応させる。`equipment_stats.py`が装備・個体の加算値を集計し、原文・未対応の効果を内訳に保持する。根拠は[能力名と単位](reference/augment-stat-names.md)。`tests/test_augment_dictionary.py`で合成DATの取得・欠落・破損・Snapshotへの引継ぎと再読込、`tests/test_equipment_stat_names.py`で辞書の更新・競合・単位・引用符・II・原文を検証する（EX-EVAL01・07）。

曖昧な表記の活用（EX-EVAL10）: [test_practical_equipment_evaluation.py](../tests/test_practical_equipment_evaluation.py)で外部通信を禁止し、明確な数値の集計・差分、条件付き効果と未知の効果の原文・出典保持、元情報の未取得との区別を検証する。[test_equipment_review_ui.py](../tests/test_equipment_review_ui.py)の`test_offline_evaluation_exposes_original_properties_in_real_details_window`は本体の「全項目・内訳」を開き、現在・候補の原文と出典、取消後の表示を確認する。「雨天のとき被ダメージ-5%」の誤集計をこの検証で検出して修正し、続く独立した魔命の加算も確認した。

収集・保守コスト（D-17）は採用理由と依存先をレビューし、評価処理が読込済みのゲーム由来情報・個体情報だけで動作し、外部の補完収集を要求しないことを確認した。費用の定量評価や利便性の最大化の証明は含まない。選択アイテムの原文の欄外表示はVIEW-007で本体へ反映。セット全体の原文は「全項目・内訳」で確認する。

VIEW-006 / D-17・D-18: `equipment_picker_ui.py`の部位別候補を4×4枠の下に、`equipment_summary_ui.py`の集計を右へ常時表示する。主要43項目・分類・比較値の表示は`equipment_stats_presentation.py`で管理し、モックと定義を共有する。候補の一時比較は作業・原本を変更せず、確定は既存の変更案確認と共通ワーカーへ渡す。

比較の取得範囲（EX-EVAL04・08・09）: `equipment_stat_parser.py`が混在行の加算値・対象外・未解釈を分け、`equipment_stats.comparison_kind`が変更する枠・項目の情報を評価する。取得不足や対象項目の解析不足だけ既知分の印を付ける。`tests/test_equipment_stat_parser.py`・`tests/test_equipment_stats_presentation.py`で解析と影響範囲を、`tests/test_equipment_review_ui.py`・`prototypes/test_equipment_review.py`で表示・取消・適用を検証する。
2026-11-06: 関連53テスト成功、スキップ0（辞書・解析・集計・正規化・比較・EX-EVAL10の単体33、本体・モック・ワーカー20）。最小画面の可読性、取消・適用・Undo、候補選択時のUIスレッドとファイルI/Oなし、長時間処理中の応答・入力排他・失敗後の復帰を合成検証した。ロスタム本体説明の読取確認は[能力名と単位](reference/augment-stat-names.md)に記録する。

`tests/test_equipment_review_ui.py`が日本語の装備説明＋英語オグメからの現在値・候補値・差分、適用・Undo/Redo・未取得、1440×900と1320×840の文字幅・全項目・操作ボタン、失敗後の入力保持と再試行を検証する（EX-EVAL02〜06）。`tests/test_workspace_ui.py`でタブ往復、`tests/test_equipment_slots.py`で保存導線、`tests/test_equipment_stats_presentation.py`で追加項目・別単位の保持と未確定の差分を検証する。実データでの再確認は未実施。

起動後の部位編集（EX-EQS07）: `test_equipment_review_ui.py::test_old_draft_does_not_prevent_mouse_slot_editing`で、破損した旧作業があってもマウスで部位・候補を選び適用でき、旧ファイルと合成ゲーム原本が不変であることを確認する。

2026-11-06の装備評価モック: 仕様管理・既存集計と表示・旧新モック・共通ワーカーの関連46テスト成功、正本64件の参照検査成功。実画面で候補選択時の差分と未取得表示を確認した。主要項目追加後、モックの7テストで43項目の配置・現在値・候補値・差分を再確認した。

2026-11-06の本体反映: 合成GUI・モックを含む全347テストを実行し346件成功、実ゲーム読込1件をスキップ。Tkテストの破棄済み画面をUIスレッドで解放するよう修正した。目視で見つけたタブ往復後の集計幅の縮小を修正し、往復を含むレイアウト検証と既存操作の12テストが成功。本体の集計・候補比較・内訳を目視確認し、最小1320×840でタブ往復後の表示も確認した。正本64件の参照検査成功。実ゲームファイルへの書込みは行っていない。

2026-11-06のゲーム辞書への切替: 全352テスト中351件成功、実ゲームUI1件をスキップ。単位が競合する書式の扱いを調整した後も関連16テスト成功。ローカル辞書の読取確認は[能力名と単位](reference/augment-stat-names.md)に記録した。


### Rank付き装備の能力解決

DATA-003・DATA-005 / D-16・D-17: [Rank能力](reference/rank-augments.md)に形式と根拠を記録。`rank_augments.py`と`LocalReader.load_rank_augments`がゲームDATから現在Rankの追加能力を解決し、取り込み・復元時の照合結果を通して表示・集計へ渡す。`tests/test_rank_augments.py`でRank境界・複合/条件付き効果・破損/欠落・未知形式・二重加算・保存原文と再読込を検証。`tests/test_rank_augments_ui.py`で本体GUIの単体値とインベントリ表示を検証。2026-11-09、指定JSONのBundle形式39個を読取確認し、アグゥゲージRank 8の魔攻+8・MBダメージII+2、本体込み魔攻43を確認。実ゲーム画面との全件照合は未実施。

VIEW-007 / D-18: 能力と取得情報を分離。参照元・日時は詳細から確認し、装備セットとインベントリの取得情報欄を削除した。`tests/test_rank_augments_ui.py`で両画面の能力表示を、`tests/test_item_properties_ui.py`で最小画面・選択切替を確認する。

EDIT-006・VIEW-003 / D-18: 装備枠・セット名の即時適用とUndo、失敗後の再実行を装備関連合成GUIで検証。`window_placement.py`が親モニターの作業領域に子ウィンドウを配置し、共通モーダルは親の可視部分へ収める。`tests/test_dialogs.py`で負座標・端・過大サイズの配置計算とWindowsの実ウィンドウ枠を検証。

### 2026-11-09 UI仕様の整合性確認

VIEW-004の切り取り確定条件、D-18のショートカット・装備候補・比較からの適用導線に残った旧プレビュー記述を即時適用へ統一した。DP-05に確認省略の対象と確認を残す操作を明記し、終了確認の古い例を再読み込みの例へ変更した。FUT-001の専用移動プレビューとVIEW-004の切り取り・貼り付けを区別した。EX-UIE08も貼り付けの即時適用へ合わせた。VIEW-003の画面内操作とD-18のモニター作業領域への配置は整合する。今回の確認は仕様文書の整合性を対象とし、全UIの実機検証を意味しない。

2026-11-09 VIEW-003 / D-18: 差分確認の本文が表示領域を占有すると確認ボタンが非表示になる問題を合成Tkで再現。`dialogs.confirm_buttons` で下部の操作領域を本文より先に確保する配置へ修正した。小さい確認画面で両ボタンの表示と本文末尾へのスクロールを回帰検証する。

2026-11-09 VIEW-004 / D-13 / D-18 / DP-05: マクロパレットの上書き貼り付けを差分確認後に許可。既定の配置判定は衝突を拒否し、パレット上書き案だけ明示的に許可する。適用直前に案を再生成して一致を確認する。合成テスト26件で確認の表示・取消・適用、Undo/Redo、確認後の対象変更、読込不足、他種別の上書き拒否と既存の保存経路を検証。実ゲームへの書込みは実施していない。

2026-11-09 VIEW-004 / D-13 / D-18 / DP-05: 上書き確認をマクロ単体へ拡張。名前と6行を変更前後の確認後に一括置換する。共通の上書き判定・確認経路を使い、装備セットは上書き拒否を維持。関連28テストでマクロ・パレットの上書き、取消、Undo/Redo、確認後の変更検出と既存保存経路を合成検証した。

2026-11-09 VIEW-004 / D-13: ツリーの選択表示と共通編集コマンドの選択状態が異なる場合、Ctrl+Cで転送内容が作られないことを合成Tkで再現。ツリーからのキー操作時に選択対象・基点・フォーカスを同期する修正を実施。マウス選択、復元された選択、右クリックメニューのコマンド経路を回帰検証する。

2026-11-09 SAVE-002 / D-05: 未変更マクロのコピー元レコード差だけで辞書依存が追加され、保存直前の計画再構成と不一致になる不具合を修正。辞書の必要性判定を実際に保存対象となるマクロへ限定した。回帰テストは修正前の同じエラーを再現し、修正後に成功。関連20テスト中18件成功・2件は既定条件でスキップ。退避した実データでも保存計画と再検証の一致を読取専用で確認した。ゲームへの書込み検証は実施していない。

2026-11-09 SAVE-004 / VIEW-004: 定型文を含むマクロのコピペ保存について、32通りの合成ケースと転送後の追加編集・再保存を検証した。現行コードでは報告症状を再現せず、定型文ID保持を確認。関連21テスト中19件成功、2件は既定条件でスキップ。本確認では実ゲームへ書き込んでいない。

2026-11-09 SAVE-004 / VIEW-004: 定型文自体を新規挿入・同表示の別IDへ置換してゲームへ未保存のまま転送する16ケースを追加検証。全ケースで保存・再読込時のIDと範囲の保持、転送先の追加編集後の再保存を確認。合成ファイルのみを使用し、本体修正を要する不具合は再現しなかった。

2026-11-09 EDIT-006 / EDIT-007 / SAVE-004: マクロ入力欄に行コピー・行貼り付け・隣接行との入替えを追加。入力欄のCtrl+C/X/Vも定型文範囲・ID・取得元を保持する共通処理へ接続した。編集適用時は行の取得元を保持し、未知の既存IDも転送後に検証・保存できる。`test_macro_lines` と定型文関連12テスト、行操作・一般保存・コピー保存関連23テストが成功（対象には重複あり）。実ゲームへの書込みは行っていない。

2026-11-09 EDIT-006 / D-09 / D-18 / DP-03: 行操作を初期状態とし、Enterで内容編集、Enter確定・Esc取消を追加。行操作と文字範囲操作でクリップボードの対象を分離。合成GUIを含む行操作・定型文・編集UIの14テストが成功。実IMEでの変換操作は未確認。

2026-11-09 VIEW-004 / D-18 / DP-05: 先の上書き確認方針を更新。マクロ・パレット上書きを確認なしで即時適用し、Undoと適用前の変更検出を維持。行操作では4方向のカーソルキーで選択・フォーカスを移す。合成GUIの行操作・選択操作11テスト成功。

## UI共通操作要件の採用と適合状況

2026-11-09: VIEW-008 / D-19を採用。共通要件とキー規約を定義し、DP-03・DP-05・D-18から参照する。今回は仕様整備であり、全画面への実装完了を意味しない。

| 対象 | 確認状況・残作業 |
|---|---|
| マクロ行の選択・Enter/Esc・行コピー | 既存の合成GUIテストあり。実IMEと確定後の行単位Undoは適合確認が必要。 |
| マクロ・パレット上書き | 既存の即時適用・Undo・適用前変更検出テストあり。 |
| マクロ名・行入力の適用 | 直接入力、フォーカス移動による確定、変更案確認を経由する現行方式を共通要件と照合し、変更箇所を確定する。 |
| 装備・インベントリ・候補・確認画面 | キーボードだけの到達性、選択とフォーカス、Escの段階、復帰位置を全画面で確認する。 |
| 共通ダイアログ・非同期処理 | 既存の配置・応答性テストを参照し、VIEW-008の受入条件に対する網羅性を確認する。 |

受入条件はtests/specs/example-tests.mdの「UI共通操作モデルの受入条件」を参照する。

2026-11-09 UI共通仕様の重複整理: 整理前コミットは`bafbeac`。VIEW-008を共通操作保証、D-19をキー・確認規約の保持元とし、VIEW-003・VIEW-004・EDIT-006・D-18・DP-02/03/05の重複本文を参照へ置換した。表示条件・対象固有の制約・既存方式の適合差分は保持。アプリ実装は変更せず、実行時の仕様JSON参照がないことをソース検索で確認した。

## 2026-11-09 UI共通要件の適合監査

対象コミット: `8c621b5`。合成ファイルと実Tkウィジェットを使用。アプリ本体は変更せず、既存テストの更新と受入テスト追加を実施。実ゲームへの書込みは行っていない。

既存16モジュール・クラスの77テストは初回74成功、3件が旧UI前提で失敗した。保存ボタンの直下探索を`accept_button`へ変更、装備変更後の確認ウィンドウ待ちを即時適用の検証へ変更、行選択中の文字カーソル位置・Tab前提をEnterで内容編集する手順へ変更した。該当2モジュール10テストを再実行し全件成功。既存77件は初回と対象再実行を合わせて成功を確認しており、修正後の全件一括再実行は行っていない。

追加の共通操作7テストは2成功・5既知未達。`expectedFailure`は未達の追跡であり、適合済みではない。全5件とも意図したアサーションで失敗することを個別のトレースバックで確認した。

| ID | 再現した未達 | 必要な設計・実装 |
|---|---|---|
| UI-G01 | マクロ名が選択段階から直接変更できる | 名前入力にも選択→Enter編集→Enter確定/Esc復元の状態を設ける。 |
| UI-G02 | 行Enter確定後も履歴カーソルが増えず、入力バッファに残る | 入力確定と編集トランザクションの境界、行単位Undo、検証失敗時の編集継続、マウスで別行へ移る時の確定を設計する。既存「変更案を確認」経路との統合が必要。 |
| UI-G03 | 装備枠でRightを押してもmainのまま | 4×4の方向移動・端の扱い・Enterで候補へ進む導線と選択/フォーカス同期を実装する。 |
| UI-G04 | 候補リスト内のEscで選択が解除されない | 子ウィジェットにも届くキー経路を設け、候補の取消と枠への復帰を一段の操作として実装する。Frameだけのバインドでは子へ届かない。 |
| UI-G05 | インベントリ一覧のDownで次の個体へ移らない | リスト/パネル両表示の方向移動・選択/フォーカス同期、詳細への決定・復帰を設計する。 |

確認できた経路: 行編集のEnter開始・Esc復元、定型文候補だけをEscで閉じて編集を保持、マクロ/パレット上書きの即時適用とUndo、確認の初期取消・本文Enter抑止・フォーカス復帰、長文確認のボタン表示、負座標・過大ダイアログの配置、終了の3択と保存失敗時の保持、処理中の排他とUIスレッド境界。これらは各テストで扱った条件に限る。

残る確認: 実IME、全画面の初期フォーカス・Enterでの到達性、参照詳細などのEsc階層と復帰、全モニター構成での目視確認。初回実行ログに破棄後のTkタイマーコールバック警告（focus_set / position）が出たため、ウィンドウ終了時のタイマー解除も追加調査対象とする。テスト結果に失敗として現れない警告を見逃さない検出が必要。

次の順序: UI-G02の確定/Undo境界を先に設計し、UI-G01・03・04・05の状態とフォーカス遷移を揃える。修正ごとに既知未達テストを通常成功テストへ変更し、保存・定型文・Undoの回帰検証を行う。

実行ログ（ローカル作業用）: `work/ui-audit-existing.log`、`work/ui-audit-followup.log`、`work/ui-audit-gaps.log`。

2026-11-09 VIEW-008 / D-19 / D-20: `EditInteraction`と合成操作モックを追加。`prototypes.test_interaction_mock`の5テストで候補取消の段階、検証失敗時の編集保持、定型文を含む確定/Undo/Redo、名前の選択段階を検証。画像で配置を確認した。ユーザーによる操作感の確認待ち。本体のUI-G01〜05解消・実IME検証は未完了。

2026-11-09 D-20: 共通確定処理にapplying状態を追加し、適用中の重複確定・別編集開始・取消を拒否。失敗時のedit復帰と再試行、無変更時の履歴抑止、Undo後の新規編集でRedo分岐を置換する操作を含むモック関連7テスト成功。利用者確認待ちは継続。

2026-11-09 本体組込み: ユーザーが操作動画を承認。マクロ名/行の選択と編集、Enterで一回の履歴へ適用、Esc復元、行貼り付け・移動の即時履歴化、装備/インベントリの方向移動、候補Esc復帰を実装。UI-G01〜05をexpectedFailureから通常テストへ変更。失敗後の編集保持・再試行と確定後のUndo/Redo/フォーカスを追加検証し、共通受入・ワークスペース・終了/保存・定型文・編集・行操作30テスト成功。実IMEと主要画面全体の実操作は継続確認。

2026-11-09 追加検証: 広いGUI回帰46テスト成功。全体の単体テスト411件は成功（条件付き95件スキップ）。その後のフォーカス階層・タイマー・入力内Undoの変更は対象テストで検証し、全体テストの対象時点と区別する。ダイアログ破棄前に遅延配置/フォーカス処理を解除する共通処理を追加し、14テスト成功。マクロの行→マクロ→パレットのEsc復帰、装備一覧→枠→候補→復帰、インベントリのパネル端と詳細復帰、DraftHistoryとEditor履歴の分離を追加し、共通受入・行操作15テスト成功。

実操作の制約: Computer Useで対象ウィンドウの存在は確認できたが、取得画像がデスクトップ背景となり、前面化が`failed to activate captured window`で失敗したため実IME検証は未達。合成データの本体確認画面「FF11 本体UI確認 — 合成データ」を起動し、利用者にIME変換のEnter/Escと編集確定の確認を依頼した。IME判定を差し替えたテストや動画の入力は実IMEの根拠に含めない。

## 2026-11-09 全体再監査と補助画面の統一

`473b0c3`を基点に全テストとUIの子画面・キー経路を再確認した。補助画面6種の初期フォーカス、ボタンのEnter、Esc/閉じる操作と呼出元への復帰を共通処理へ接続した。共通文字入力ダイアログにEnter確定を追加し、定型文検索とともにIME変換中のEnter/Escを共通判定で保護した。マクロ編集も同じIME判定を参照する。

初回全件検証で保存・移動の3テストが旧ボタン配置を前提としていたため、実際の確認ボタンを参照するよう更新し、CIのGUI対象にも追加した。修正後の同じコード状態で、GUI有効・実ゲーム連携無効の全件を再実行した。

- 本体: 418件中417件成功、実インストール環境のGUI検証1件スキップ。309.576秒。
- 操作モック: 7件成功。
- 要件・設計管理: 69レコード、構造・参照検証成功。
- 対象: マクロ/パレット/行のコピー、保存済み・未保存の定型文、保存計画、Undo/Redo、装備とインベントリの移動、候補/補助画面の復帰、ダイアログ、終了、非同期処理、保存失敗からの復旧。UI-G01〜05は通常テストとして成功。
- 最終ログにテスト失敗・例外トレース・破棄後のTkコールバックエラーなし。

実IME、実際の複数モニター配置、OSのファイル選択画面、実ゲーム環境での一連の操作は今回の自動検証の対象外。IME状態の差替え・合成データによるTk操作と、実環境での操作を区別する。ゲームファイルへの書込みは行っていない。操作感の調整はユーザーが操作できる時点で再開する。

実行ログ（ローカル作業用）: `work/ui-comprehensive-final.log`、`work/ui-comprehensive-mock.log`。

## 2026-11-09 目的別メニューの追加要件

ユーザーが実機確認を完了条件から除外したため、既存の共通キー操作・編集段階のゴールは完了とした。これは実機確認済みへの変更ではない。

続いてVIEW-008 / D-19へ目的別の機能配置とタブからの独立を追加採用した。現状のworkspace_ui.pyはチェック、補正、取り込み、対象編集、Undo等を一つの操作メニューへ並べている。目的別の分類・対象範囲の明示・タブに依存しない共通コマンドの接続を追加設計・実装する。今回の変更は要件・設計・受入仕様の整備であり、アプリ実装は未変更。検証項目はexample-tests.md「目的別メニューとタブからの独立」を参照する。

2026-11-09 目的別メニューを実装。実装前のコミットポイントは`2f4c5dd`。common_actions_ui.pyに編集・チェック・取り込み/再読込・書き戻しの明示的なコマンド一覧を設け、タブ外の共通領域へ固定配置した。チェック/取り込み対象のキャラと全キャラ操作の範囲を表示し、既存ActionButtonの実行可否・処理中排他を維持する。装備参照位置の結果には「補正を適用」「閉じる」を表示。結果から対象を開く際は検査したキャラへ移動してフォーカスを合わせる。

対象回帰49件は初回48成功。追加した結果移動テスト1件は合成データに該当対象がないため失敗し、空セットを参照するマクロを準備するよう修正後、単独再実行で成功した。実装コードへの追加修正は不要だった。共通操作・実行スレッド境界・取り込み・終了保存・ワークスペース・ダイアログ・装備移動を検証。3タブそれぞれの共通入口、チェックでタブ/履歴が変わらないこと、取り込み取消、明示した結果移動を含む。今回は全体テストの再実行ではなく変更対象の回帰検証。ログは`work/common-menu-final.log`、結果移動の最終確認は単独実行。実機確認は完了条件に含めない。

## 2026-11-09 保存状態の範囲限定を本体へ反映

D-05 / PERF-001: 実験コミット`3e23340`で、全キャラSnapshotの生成を対象キャラだけに限定し、保存済み状態を変更レコード単位で更新、取得元指紋の照合を辞書化した。実ゲームから取得した同一バイト列の隔離コピーで、1ファイル書き戻し中央値48.74秒→20.96秒（57.0%短縮）、20ファイル67.52秒→21.42秒（68.3%短縮）。各3回であり性能保証ではない。元1,871ファイルのハッシュ不変、保存先・バックアップ一致、隔離違反0を確認した。

計測した候補と同じ処理を`save_state.py`へ移し、Editorの保存窓口から委譲する。本体は実験モジュールを参照しない。保存計画の再照合、依存ファイルの競合検出、バックアップ・復旧・UAC経路は維持。ディスク上の検証対象数は縮小していない。約11秒残る保存直前の全体読込・検証は次の改善対象。

検証: 実験候補はGUI有効420件中419成功・実ゲーム用1件スキップ、専用2テスト成功。本体移植後の422件実行では新モジュールの遅延importが隔離I/Oガードに拒否され、権限保存テストの5サブケースが失敗した。他のテストは成功、実ゲーム用1件はスキップ。既存方式に合わせてproperty_supportの事前importへ追加し、該当モジュールと専用テストの10件を再実行して全成功。本体ロジックへの追加修正はなし。修正後の全件一括再実行は行っていない。仕様検証成功。

計測方法・値・限界は[比較記録](../experiments/stack-evaluation/SCOPED-SAVE.md)を参照。ローカルログ: `work/scoped-save-tests-final.log`、`work/scoped-save-production-tests.log`、`work/scoped-save-import-followup.log`、`work/scoped-save-real.log`。
