# 要求追跡表

現行正本は `ternary_image_editor_spec_v1_5.html`（SHA-256:
`ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`）。v1.1は履歴であり、
現在の受理根拠には用いない。マウス入力割当だけは `mouse-input-bindings-addendum.md`
（`TIE-ADD-PTR-001`、SHA-256:
`91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba`）がv1.5を限定
上書きする。v1.5のHTMLとhashは変更しない。
この追跡表の現行対象応用版は `0.3.0`。

状態語は次の意味に限る。

- `implemented`: 該当実装が現在の作業木にある。
- `automated-local`: 現在のmacOS開発環境で当該契約を自動検証した。
- `automated-partial`: 下位契約は自動検証したが、受入条件全体の端から端までの試験ではない。
- `windows-pending`: Windows実機または配布候補でなければ閉じられない。
- `planned`: 契約と検証対象は記録したが、実装または証拠をまだ確認していない。

いずれも最終人間受理を表さない。試験コードは公開取得物へ含めないため、
`automated-local` は非公開の開発作業木で得た証拠を表す。

## v1.1から継続する受入条件

| 範囲 | 主な受入試験 | 実装面 | 検証面 | 状態 |
| --- | --- | --- | --- | --- |
| 対応付け・入力検査 | AT-001〜004 | `pairing.py`, `image_io.py` | `test_pairing.py`, `test_image_io.py` | implemented / automated-local |
| GIMP合成・疑似色 | AT-005〜007 | `operations.py`, `canvas.py` | `test_operations.py`, `test_canvas.py` | implemented / automated-local |
| 拡大・格子・筆 | AT-008〜013 | `canvas.py`, `canvas_transform.py`, `operations.py`, `history.py` | 数式・画素マスク・Qt入力統合 | implemented / automated-local |
| 二種境界生成 | AT-014〜020 | `operations.py`, `session.py` | `test_operations.py`, `test_session.py` | implemented / automated-local |
| 小領域検査 | AT-021〜023 | `operations.py`, `workers.py`, `main_window.py` | 配列、表示、保存除外、改訂/token統合 | implemented / automated-local |
| 遷移・既存出力 | AT-024〜025 | `session.py`, `main_window.py` | 保存・破棄・中止、編集元三分岐 | implemented / automated-local |
| 保存・入力不変 | AT-026〜029 | `image_io.py`, `session.py`, `main_window.py` | 再読込、故障注入、SHA-256、置換前後競合 | implemented / automated-local |
| 高DPI・画像外余白 | AT-030〜033 | `canvas.py`, `canvas_transform.py` | DPR数式・Qt統合・Windows実機 | implemented / automated-partial / AT-030 windows-pending |

## v1.2〜v1.5追加受入条件

| AT | 契約 | 現在の実装 | 現在の自動証拠 | 状態 |
| --- | --- | --- | --- | --- |
| AT-034 | 読込時の下端強制無化・差分あり | `image_io.py`, `session.py`, `main_window.py` | core正規化・基準・履歴試験に加え、`test_v15_main_window.py::test_at_034_bottom_normalization_reports_changed_pixels_in_status` | implemented / automated-local |
| AT-035 | 下端が既に無なら未変更 | `image_io.py`, `session.py` | 正規化差分0と基準配列比較は同経路。専用GUI遷移試験は未追加 | implemented / automated-partial |
| AT-036 | 全画素操作から下端を保護 | `operations.py`, `session.py`, `canvas.py` | `test_v15_canvas.py::test_at_036_*`, `test_v15_core.py::test_at_036_*` | implemented / automated-local |
| AT-037 | 保存時に下端を再強制無化 | `image_io.py` | `test_v15_core.py::test_at_037_save_uses_copy_and_forces_protected_rows_black` | implemented / automated-local |
| AT-038 | Action Registryの適用範囲 | `action_registry.py`, `settings_dialog.py`, `main_window.py` | 正規38件、設定表38行、主窓callback・QAction・メニュー各一件を自動検証 | implemented / automated-local |
| AT-039 | 単一キー取得 | `ShortcutCaptureController` | `test_settings_dialog_v15.py::test_capture_ignores_preheld_modifier_repeat_and_keyup_then_takes_one_chord` | implemented / automated-local |
| AT-040 | 修飾キー組合せ取得 | `ShortcutCaptureController` | 同上の `Ctrl+Shift+K` 候補化 | implemented / automated-local |
| AT-041 | 開始前押下・反復除外 | `ShortcutCaptureController` | KEY-010に従い、既知の事前押下、自動反復、未観測のControl/Alt/Shift/Metaを主キー修飾状態から推定した場合の全KeyUp待機と新chord取得を検証 | implemented / automated-local |
| AT-042 | 入力待機取消 | `settings_dialog.py` | Esc、行移動、非活性化、閉鎖の試験 | implemented / automated-local |
| AT-043 | 予約入力拒否 | `action_registry.py`, `settings_dialog.py` | Tab拒否・Esc取消を自動検証。ほかの予約列は判定実装証拠 | implemented / automated-partial |
| AT-044 | 割当競合の移動・取消 | `ShortcutAssignments`, `SettingsDialog` | registry単体とdialog作業値試験 | implemented / automated-local |
| AT-045 | 主・副割当 | `ShortcutBindings`, `ShortcutAssignments` | Redo既定副割当、自己重複拒否、両欄の検証 | implemented / automated-local |
| AT-046 | 割当の適用・取消 | `SettingsWorkCopy`, `SettingsDialog` | 適用・OK・取消と作業値隔離の試験 | implemented / automated-local |
| AT-047 | 永続化・スキーマ差分 | `SettingsRepository` | QSettings往復、未知ID無視、欠落既定補完、局所破損回復 | implemented / automated-local |
| AT-048 | 解除・既定復元 | `ShortcutAssignments`, `SettingsDialog` | assignment解除と全体既定・確認を自動検証。個別復元のGUI経路は実装証拠 | implemented / automated-partial |
| AT-049 | 設定画面への到達保証 | `main_window.py` の常設設定ボタン・メニュー・GUI保持操作 | `test_at_038_049_all_operations_have_one_registry_and_menu_surface`, `test_at_049_unassigned_hold_still_has_a_working_gui_surface` | implemented / automated-local |
| AT-050 | 論理キー・日本語入力方式 | PortableText保存、NativeText表示 | 形式往復は単体検証。日本語入力方式とWindows配列は未検証 | implemented / automated-partial / windows-pending |
| AT-051 | 選択色の順循環 | `control_panel.py`, `main_window.py` | 主窓のメニュー・ボタン・キーから同じ一段循環を自動検証。任意開始色の三周全組合せは未追加 | implemented / automated-partial |
| AT-052 | 選択色の逆循環 | `control_panel.py`, `main_window.py` | 共通経路は実装済み。三回循環の主窓統合試験は未追加 | implemented / automated-partial |
| AT-053 | 循環順と疑似色の独立 | ラベル値循環、意味名・保存色表示 | 配色モデルとラベル表示は個別試験。組合せ統合試験は未追加 | implemented / automated-partial |
| AT-054 | 色切替の非編集性・状態維持 | 選択色を画像配列・履歴・永続設定から分離 | 主窓で配列・未保存・改訂・履歴・道具・倍率不変を自動検証。画像移動を跨ぐ保持は未追加 | implemented / automated-partial |
| AT-055 | 色循環割当・描画中排他 | Registry割当、stroke中命令抑止 | 割当とstroke排他を個別自動検証。組合せ統合試験は未追加 | implemented / automated-partial |
| AT-056 | メニュー・ボタン・キー経路一致 | 全経路を `_cycle_label` へ集約 | `test_at_051_054_056_color_cycle_routes_share_nonediting_state` が三経路の選択色・状態欄・筆指示・非編集性を比較 | implemented / automated-local |
| AT-057 | 既定キーは固定入力でない | `ActionRegistry.set_assignments` | `test_generated_qaction_has_identity_repeat_policy_and_reassignable_shortcuts` | implemented / automated-local |
| AT-058 | 一回分・上下限 | ControlPanel刻み、倍率1.25、Registry刻み型 | 筆径、倍率、Registry型を自動検証。不透明度・境界太さを含む全主窓経路は未追加 | implemented / automated-partial |
| AT-059 | キー自動反復 | `ActionRegistry` のsingle/step/hold | `test_registry_enforces_single_step_hold_and_text_input_semantics` | implemented / automated-local |
| AT-060 | 初回既定値 | `AppSettings`, `MainWindow`, `CanvasTransform` | `test_app_settings_defaults_cover_persistent_scope_only` とfit試験 | implemented / automated-partial |
| AT-061 | 設定永続化範囲 | `AppSettings`, `SettingsRepository` | 全既知項目の往復と選択色・倍率・中心・現在画像の型上の排除 | implemented / automated-local |
| AT-062 | 設定の適用・取消 | `SettingsDialog`, `MainWindow._apply_settings_snapshot` | dialog適用・取消と `test_at_062_setting_apply_does_not_touch_image_state` による配列・基準・履歴・未保存不変 | implemented / automated-local |
| AT-063 | 疑似色設定・色差警告 | `settings_model.py`, `settings_dialog.py` | `#RRGGBB`、距離64境界、確認、色既定復元、永続化を自動検証。OS色選択部品経路は未追加 | implemented / automated-partial |
| AT-064 | 原画像入力条件・色管理 | `image_io.py` | `test_v15_core.py::test_at_064_*`、EXIF・入力不変試験 | implemented / automated-local |
| AT-065 | 三値非表示時の編集禁止 | `canvas.py`, `main_window.py` | canvas overlay試験と `test_at_065_hidden_labels_block_edit_undo_redo_and_preserve_history` | implemented / automated-local |
| AT-066 | 変更なし保存 | `session.py`, `main_window.py`, `image_io.py` | `test_at_066_079_unchanged_save_changes_list_to_output_present` がclean保存と出力あり遷移を検証 | implemented / automated-local |
| AT-067 | 内容比較による未保存判定 | `session.py` の基準配列比較 | `test_v15_core.py::test_at_067_dirty_state_is_based_on_content_not_history_position` | implemented / automated-local |
| AT-068 | 履歴破棄後の未保存判定 | 基準配列と履歴を分離 | 内容比較と履歴上限を個別試験。両者の組合せ専用試験は未追加 | implemented / automated-partial |
| AT-069 | 外部出力変更・新規出現 | `image_io.py`, `session.py`, `dialogs.py`, `main_window.py` | 内容変更・新規出現・削除・置換境界の故障注入に加え、主窓試験が取消後の未保存・履歴・外部出力維持と、外部削除/置換時の旧「出力不正」cache破棄を検証 | implemented / automated-local |
| AT-070 | 多重起動保存ロック | `save_lock.py`, 保存排他区間 | `test_v15_core.py::test_at_070_output_lock_is_nonblocking_stable_and_preserves_dirty_state` | implemented / automated-local / Windows多重プロセスはwindows-pending |
| AT-071 | 筆描画の原子性・取消 | `canvas.py`, `main_window.py`, `session.py` | Esc取消、正常解放、stroke一履歴、描画中排他を個別試験 | implemented / automated-partial |
| AT-072 | 偶数径筆マスク | `operations.py`, `canvas.py` | 離散円・正方形の余剰側、補間、予告像一致の試験 | implemented / automated-local |
| AT-073 | ウィンドウ寸法変更 | `canvas.py`, `canvas_transform.py` | fit再計算、手動倍率・中心維持の数式・Qt試験 | implemented / automated-local |
| AT-074 | モニターDPI変更 | `canvas.py`, `canvas_transform.py` | DPR変更時の中心・閾値再計算は自動検証。実モニター移動は未検証 | implemented / automated-partial / windows-pending |
| AT-075 | Unicode対応キー | `pairing.py` | `test_v15_core.py::test_at_075_nfc_equivalent_suffixes_pair_but_case_difference_does_not` | implemented / automated-local |
| AT-076 | 対象外画像の移動 | `pairing.py`, `main_window.py` の編集一覧・対象外一覧分離 | `test_at_076_lazy_invalid_pair_moves_to_error_list_and_next_reaches_later_pair` が遅延不正の移送と有効対だけの次移動を検証 | implemented / automated-local |
| AT-077 | 画素格子は自動ON/OFFのみ | `canvas.py`, `main_window.py`, `settings_model.py` | DPR閾値と設定既定・永続化は自動検証。G経路の専用主窓試験は未追加 | implemented / automated-partial |
| AT-078 | 固定マウス操作・保持パン | `canvas.py`, `ActionRegistry`, `main_window.py` | 固定mouse経路、GUI latch、K/Ctrl+K再割当、旧Space無効化、修飾キー先離し後の主キーKeyUp解除、重複hold tokenを自動検証 | implemented / automated-local |
| AT-079 | 出力ありと確認状態 | `main_window.py`, `session.py` | clean保存と外部新規出力に加え、`test_at_069_079_external_change_invalidates_cached_output_error` が削除CANCEL→出力なし、置換CANCEL→出力ありへ一覧を同期し、誤った「出力不正」を残さないことを検証 | implemented / automated-local |

## マウス入力割当追補の受入条件

`PTR-AT-*` は `TIE-ADD-PTR-001` だけに属し、v1.5本文の `AT-*` とは別の要求身元である。
局所統合証拠は2026-08-19（Asia/Tokyo）のmacOS開発作業木で `uv run pytest` を実行した
343件成功である。次表の試験名はこの非公開試験集合に属する。

| 追補AT | 契約 | 現在の実装 | 現在の自動証拠 | 状態 |
| --- | --- | --- | --- | --- |
| PTR-AT-001 | 七基底token、Ctrl/Alt/Shift正規化、完全一致 | `action_registry.py`, `main_window.py` | `test_pointer_tokens_are_canonical_bindings`, `test_pointer_modifiers_are_ordered_and_unsupported_modifiers_are_rejected`, `test_pointer_wheel_assignment_is_exact_and_overrides_fixed_zoom` | implemented / automated-local |
| PTR-AT-002 | Meta、鍵盤+mouse、複数button、専用double-click、drag、水平wheel、macro、global入力を拒否 | `action_registry.py`, `settings_dialog.py`, `main_window.py` | `test_qt_pointer_helpers_have_one_mapping_and_reject_unsupported_input`, `test_capture_consumes_double_click_sequence_without_second_candidate`, `test_capture_takes_vertical_wheel_but_excludes_zero_and_horizontal`。複数button・drag・macroの専用試験は未追加 | implemented / automated-partial |
| PTR-AT-003 | 既存38操作と主・副割当を維持し、鍵盤・ポインタ間で同じ競合移動・取消を適用 | `action_registry.py`, `settings_dialog.py` | `test_at_038_049_all_operations_have_one_registry_and_menu_surface`, `test_pointer_bindings_share_conflict_space_with_keyboard_bindings` | implemented / automated-local |
| PTR-AT-004 | button・垂直wheelを一候補として捕捉し、左・中・wheelの固定操作置換を適用前確認 | `settings_dialog.py` | `test_capture_takes_supported_mouse_button_and_consumes_its_release`, `test_capture_takes_vertical_wheel_but_excludes_zero_and_horizontal`, `test_fixed_pointer_override_confirmation_can_cancel_without_mutation`, `test_fixed_pointer_override_confirmation_can_accept` | implemented / automated-local |
| PTR-AT-005 | 主画像Canvas限定で作動し、設定画面・一般UI入力を奪わない | `main_window.py`, `settings_dialog.py` | `test_pointer_assignments_are_canvas_only_and_disabled_exact_input_is_consumed`, `test_dialog_does_not_intercept_idle_mouse_or_wheel` | implemented / automated-local |
| PTR-AT-006 | 未割当の固定操作を保ち、割当済み完全一致は無効時もfallbackせず、一時パン中の左buttonを優先 | `main_window.py`, `canvas.py`, `action_registry.py` | `test_pointer_wheel_assignment_is_exact_and_overrides_fixed_zoom`, `test_assigned_disabled_pointer_binding_is_consumed_without_invocation`, `test_mouse_left_assignment_preserves_existing_temporary_pan_escape_route`と既存wheel・pan回帰 | implemented / automated-local |
| PTR-AT-007 | SINGLE・STEP・HOLDをevent種別どおり実行し、wheel→HOLDとMouseLeft系→一時パンを拒否 | `action_registry.py`, `settings_dialog.py` | `test_registry_dispatches_pointer_single_step_and_hold_bindings`, `test_hold_binding_constraints_apply_to_assignment_and_initial_bindings`, `test_invalid_hold_pointer_bindings_show_core_reason_without_mutation` | implemented / automated-local |
| PTR-AT-008 | double-click二押下、wheel一event単位、押下token latch、同期modal再入、非活性化・焦点・捕捉喪失・設定適用で全HOLD解放 | `action_registry.py`, `main_window.py` | `test_pointer_runtime_double_click_counts_two_presses_and_stroke_blocks_new_inputs`, `test_pointer_button_hold_uses_press_token_and_deactivation_cleans_latch`, `test_pointer_latch_exists_before_reentrant_callback_and_is_not_recreated`, `test_dialog_cancel_and_deactivate_clear_pointer_release_latches`。pointer HOLDのFocusOut・UngrabMouse専用試験は未追加 | implemented / automated-partial |
| PTR-AT-009 | 筆描画中は完成・取消入力だけを所有し、ほかのポインタ割当を発火も予約もせず消費 | `canvas.py`, `main_window.py` | `test_pointer_runtime_double_click_counts_two_presses_and_stroke_blocks_new_inputs`, `test_edit_009_view_change_during_brush_is_rejected_not_reserved` | implemented / automated-local |
| PTR-AT-010 | schema 2保存、schema 0/1鍵盤割当の無警告移行、既存path維持、欄単位の破損fallback、正常な明示割当を低優先fallbackより優先 | `settings_model.py`, `action_registry.py` | `test_schema_one_keyboard_settings_migrate_to_schema_two_without_warning`, `test_schema_two_pointer_bindings_roundtrip`, `test_missing_shortcut_uses_default_unknown_id_is_ignored_and_corruption_is_local`, `test_invalid_fallback_does_not_displace_a_valid_explicit_binding`, `test_missing_default_does_not_displace_a_valid_explicit_binding`。schema 0の任意鍵盤割当と組織名・応用名を跨ぐ専用移行試験は未追加 | implemented / automated-partial |
| PTR-AT-011 | Windows実機でBack/Forward、precision touchpad/inertia、modal中release、旧schema保持を確認 | 配布候補 | macOSの合成Qt eventだけでは閉じない | windows-pending |

## AT表外の横断要求証拠

- KEY-004: `test_action_registry.py` が単文字・数字・記号と標準文字編集キーを編集欄では
  抑止し、Ctrl+S、Ctrl+Shift+B、Alt+1、F5等の非編集命令を過剰抑止しないことを検証。
  `test_v15_main_window.py::test_key_004_numeric_input_keeps_standard_up_key_for_the_widget` は
  数値欄のUpを操作割当へ漏らさず、部品自身へ渡す主窓経路を検証した。
- SAVE-009: 原画像・入力三値外部変更の取消、読込済みスナップショット保存、再読込破棄を
  `test_v15_main_window.py::test_input_source_external_change_screen_branches` で自動検証した。

## 現在環境では閉じない証拠

- AT-030とAT-074のWindows表示倍率100%、125%、150%、200%および実モニター移動。
- AT-050の日本語入力方式ON/OFF、PortableText保存、Windowsキーボード配列依存の
  NativeText表示。
- AT-070のWindows 10 / 11における実プロセス間ロック、ロック中断後の回復。
- Windows 10 / 11上の対象業務PCでの性能目標、ファイルロック、ACL、Unicode長パス。
- Windows配布物からの起動、設定永続化、画面外に残った旧geometryの復旧。
- PTR-AT-011のBack・Forward button、precision touchpadのwheel分割・inertia、modal画面中の
  HOLD解放、schema 0/1から2への実設定移行。
- 同じ側車ロック規約に従わない別アプリが、最後の内容照合と `os.replace` 呼出しの間へ
  割り込む競合。協調writerは保存ロックで排他するが、`os.replace` 自体は内容条件付き置換
  ではない。
