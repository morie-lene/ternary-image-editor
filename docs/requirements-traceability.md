# 要求追跡表

基線正本は `ternary_image_editor_spec_v1_5.html`（SHA-256:
`ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`）。v1.1は履歴であり、
現在の受理根拠には用いない。柔軟入力、対応付け、参照原画像、三値JPEG、編集元優先、外部出力復旧、
寸法、下端保護は`flexible-input-pairing-addendum.md`（`TIE-ADD-FLEX-001` version 1.3、SHA-256:
`ce148618e7cf049cbfe2fa13e00fc4f3cb17b4726c4bf8e878bd63edcbb6255c`）が限定上書きする。
version 1.2の履歴SHA-256は
`a2d8a8c1c1c6202a770bac69f14f5cfed71f8f1428e9ffee49b4a06875849798`である。
マウス入力割当は
`mouse-input-bindings-addendum.md`
（`TIE-ADD-PTR-001`、SHA-256:
`91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba`）がv1.5を限定
上書きする。表示比較（暗）は`display-comparison-addendum.md`（`TIE-ADD-DISP-CMP-001`
version 1.0、SHA-256:
`26f1ff442548d51f66bdb518a14d10d92e52e48c10daec877a8ab04ad27e3779`）が表示合成・表示設定・
操作件数だけを限定上書きする。v1.5のHTMLとhashは変更しない。
この追跡表の現行対象応用版は `0.7.0`。

状態語は次の意味に限る。

- `implemented`: 該当実装が現在の作業木にある。
- `automated-local`: 現在のmacOS開発環境で当該契約を自動検証した。
- `automated-partial`: 下位契約は自動検証したが、受入条件全体の端から端までの試験ではない。
- `windows-pending`: Windows実機または配布候補でなければ閉じられない。
- `planned`: 契約と検証対象は記録したが、実装または証拠をまだ確認していない。
- `superseded`: 旧版の要求身元と証拠を履歴として保つが、現行受入には用いない。

いずれも最終人間受理を表さない。公開取得物には入力契約用の
`tests/test_flexible_input_contract.py`、表示比較契約用の`tests/test_display_comparison_contract.py`、
包装検査用の`tests/test_packaging.py`を含める。
`FLEX-AT-*`でこの公開入力契約試験を明記した項目は公開cloneで再現できる。それ以外の機能要求に
対する`automated-local`は、特記がない限り非公開の開発作業木で得た機能試験証拠を表し、公開包装
試験の成功から導出しない。

固定hashを持つマウス入力割当追補9節の「試験コードを含めない」という一般記述は、現在の三つの
公開試験を反映していない。追補本文を同一hashのまま改変せず、本追跡表とREADMEでこの範囲差を
明示する。

`TIE-ADD-FLEX-001`が上書きする事項では `FLEX-AT-*` を現行受入条件とする。旧ATの証拠は
旧固定寸法経路の回帰証拠として保持するが、それだけから任意寸法、自然順、JPEG三値化の成功を
導出しない。

版0.4.0の局所統合証拠は2026-08-19（Asia/Tokyo）のmacOS作業木で、全367試験、統合差分全体の
Ruff、sdist/wheel構築、`expected_size=None`の画面外GUI起動が成功したことである。詳細な命令、結果、
未完了境界は[柔軟入力・対応付けローカル検証記録](local-verification-2026-08-19-flexible-input.md)に
分離する。この統合成功は、各行の`automated-partial`や`windows-pending`を自動で閉じない。

版0.5.0の局所統合証拠は同日のmacOS作業木で、全376試験、Ruff、依存固定、差分形式、
sdist/wheel構築、`expected_size=None`の画面外GUI起動が成功したことである。公開包装へ収載する試験は
32件で、全376件とは証拠範囲を分ける。詳細は
[参照原画像・編集元優先・界面文ローカル検証記録](local-verification-2026-08-19-reference-source-ui.md)に
分離する。Windows実機判断門は閉じていない。

版0.5.1の局所統合証拠は同日のmacOS作業木で、選択ラベル源、保存済み出力再開、fallback snapshot、
通知・cache寿命、選択源別保存基準の実装に対して全410試験、公開66試験、Ruff、依存固定、差分形式、
sdist/wheel構築、`expected_size=None`の画面外GUI起動が成功したことである。詳細は
[保存済み出力再開・選択源境界ローカル検証記録](local-verification-2026-08-19-output-resume.md)に分離する。
この局所成功はWindows実機受理を閉じない。

版0.6.0の局所統合証拠は同日のmacOS作業木で、表示比較（暗）の画素、操作、設定、画像状態・保存不変、
追補・包装の実装に対して全415試験、公開71試験、Ruff、依存固定、差分形式、sdist/wheel構築、画面外
GUI起動、独立動的probe、三系統の独立査読が成功したことである。詳細は
[表示比較（暗）ローカル検証記録](local-verification-2026-08-19-display-comparison.md)に分離する。
この局所成功はWindows描画器、実機入力、性能、配布受理を閉じない。

版0.6.1の局所統合証拠は同日のmacOS作業木で、編集元省略入口の保存済み出力優先と厳格対応の
冷間起動回帰に対して全417試験、公開73試験、Ruff、依存固定、差分形式、sdist/wheel構築が成功した
ことである。詳細は
[保存済み出力優先入口ローカル検証記録](local-verification-2026-08-19-output-resume-entrypoint.md)に
分離する。通常GUIの冷間起動は修正前から局所成功しており、この修正だけからWindows実データでの
元報告の単独原因だったとは導出しない。

版0.7.0では、外部由来出力PNGのstrict-first限定復旧と、復旧不能出力から同じ対の厳格INPUTへ
退避するpreflightを追跡対象へ加える。現在の作業木にある実装面と個別試験名は`FLEX-AT-017`、`018`
で対応付ける。2026-08-20（Asia/Tokyo）のmacOS開発作業木では、局所統合試験456件と公開取得物へ
収載する三公開試験ファイル計100件が成功し、柔軟入力・対応付け追補version 1.3の上記SHA-256を
現物照合した。
Ruff、依存固定、差分形式、sdist / wheel、画面外GUI煙試験、四規範文書hashも成功し、詳細を
[外部出力復旧・preflight退避ローカル検証記録](local-verification-2026-08-20-external-output-recovery.md)
へ分離した。これらの局所成功はWindows one-folder構築、exe起動、実物ICC、実業務画像の受理を閉じない。

## v1.1から継続する受入条件

| 範囲 | 主な受入試験 | 実装面 | 検証面 | 状態 |
| --- | --- | --- | --- | --- |
| 対応付け・入力検査 | AT-001〜004、現在はFLEX-AT-001〜008、017〜018で限定上書き | `pairing.py`, `image_io.py`, `main_window.py` | 旧厳格経路と外部出力復旧・preflight退避の個別試験 | implemented / automated-partial / windows-pending |
| GIMP合成・疑似色 | AT-005〜007 | `operations.py`, `canvas.py` | `test_operations.py`, `test_canvas.py` | implemented / automated-local |
| 拡大・格子・筆 | AT-008〜013 | `canvas.py`, `canvas_transform.py`, `operations.py`, `history.py` | 数式・画素マスク・Qt入力統合 | implemented / automated-local |
| 二種境界生成 | AT-014〜020 | `operations.py`, `session.py` | `test_operations.py`, `test_session.py` | implemented / automated-local |
| 小領域検査 | AT-021〜023 | `operations.py`, `workers.py`, `main_window.py` | 配列、表示、保存除外、改訂/token統合 | implemented / automated-local |
| 遷移・既存出力 | AT-024〜025。FLEX-AT-011は履歴、現在はFLEX-AT-012〜015、017〜018で限定上書き | `session.py`, `main_window.py`, `image_io.py` | 保存・破棄・中止、選択源分離、外部出力復旧、不正出力fallback snapshot、preflight INPUT退避、通知・cache寿命 | implemented / automated-partial / windows-pending |
| 保存・入力不変 | AT-026〜029 | `image_io.py`, `session.py`, `main_window.py` | 再読込、故障注入、SHA-256、置換前後競合 | implemented / automated-local |
| 高DPI・画像外余白 | AT-030〜033 | `canvas.py`, `canvas_transform.py` | DPR数式・Qt統合・Windows実機 | implemented / automated-partial / AT-030 windows-pending |

## v1.2〜v1.5追加受入条件

| AT | 契約 | 現在の実装 | 現在の自動証拠 | 状態 |
| --- | --- | --- | --- | --- |
| AT-034 | 読込時の下端強制無化・差分あり。現行境界はFLEX-DIM-004 | `image_io.py`, `session.py`, `main_window.py` | 旧固定寸法のcore正規化・基準・履歴試験に加え、`test_v15_main_window.py::test_at_034_bottom_normalization_reports_changed_pixels_in_status` | implemented / automated-partial |
| AT-035 | 下端が既に無なら未変更。現行境界はFLEX-DIM-004 | `image_io.py`, `session.py` | 正規化差分0と基準配列比較は同経路。`H=100/101`はFLEX-AT-009へ分離 | implemented / automated-partial |
| AT-036 | 全画素操作から下端を保護。現行境界はFLEX-DIM-004 | `operations.py`, `session.py`, `canvas.py` | 旧固定寸法の`test_v15_canvas.py::test_at_036_*`, `test_v15_core.py::test_at_036_*` | implemented / automated-partial |
| AT-037 | 保存時に下端を再強制無化。現行境界はFLEX-DIM-004 | `image_io.py` | 旧固定寸法の`test_v15_core.py::test_at_037_save_uses_copy_and_forces_protected_rows_black` | implemented / automated-partial |
| AT-038 | Action Registryの基線適用範囲。表示追補が基線38 IDを保持して一操作を加える | `action_registry.py`, `settings_dialog.py`, `main_window.py` | 基線38件＋追補1件、設定表39行、主窓callback・QAction・メニュー各一件を自動検証 | implemented / automated-local |
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
| AT-064 | 原画像入力条件・色管理。現在はFLEX-ORIG-001/002とFLEX-AT-010で限定上書き | `image_io.py` | 公開原画像正規化・EXIF転置・復号失敗・入力不変試験と局所回帰試験 | implemented / automated-local |
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
| AT-075 | Unicode対応キー。厳格対応identityはNFC、自然順の整列だけNFKC | `pairing.py` | 厳格経路の`test_v15_core.py::test_at_075_nfc_equivalent_suffixes_pair_but_case_difference_does_not`。自然順はFLEX-AT-003へ分離 | implemented / automated-partial |
| AT-076 | 対象外画像の移動 | `pairing.py`, `main_window.py` の編集一覧・対象外一覧分離 | `test_at_076_lazy_invalid_pair_moves_to_error_list_and_next_reaches_later_pair` が遅延不正の移送と有効対だけの次移動を検証 | implemented / automated-local |
| AT-077 | 画素格子は自動ON/OFFのみ | `canvas.py`, `main_window.py`, `settings_model.py` | DPR閾値と設定既定・永続化は自動検証。G経路の専用主窓試験は未追加 | implemented / automated-partial |
| AT-078 | 固定マウス操作・保持パン | `canvas.py`, `ActionRegistry`, `main_window.py` | 固定mouse経路、GUI latch、K/Ctrl+K再割当、旧Space無効化、修飾キー先離し後の主キーKeyUp解除、重複hold tokenを自動検証 | implemented / automated-local |
| AT-079 | 出力ありと確認状態 | `main_window.py`, `session.py` | clean保存と外部新規出力に加え、`test_at_069_079_external_change_invalidates_cached_output_error` が削除CANCEL→出力なし、置換CANCEL→出力ありへ一覧を同期し、誤った「出力不正」を残さないことを検証 | implemented / automated-local |

## 柔軟入力・対応付け追補の受入条件

`FLEX-AT-*`は`TIE-ADD-FLEX-001`だけに属し、v1.5本文の`AT-*`およびマウス追補の
`PTR-AT-*`とは別の要求身元である。`test_flexible_input_contract.py`は公開cloneで再現できる自動証拠
だが、各行に記した未試験経路とWindows受理を閉じない。版0.5.0までの局所証拠は2026-08-19
（Asia/Tokyo）のmacOS作業木で
`QT_QPA_PLATFORM=offscreen uv run pytest -q tests/test_flexible_input_contract.py`を実行した28件成功である。
版0.5.1では同じ公開契約試験62件、包装試験と合わせた公開二試験66件が成功した。版0.6.1では
公開入力契約試験64件、表示比較契約5件、包装契約4件の計73件が成功した。
版0.7.0では、同じ三公開試験ファイルの計100件と局所統合試験456件が成功した。この件数と下表の
個別試験名だけから、Ruff、依存固定、包装成果物、Windows実機受理の成功を推定しない。

フォルダ変更、再走査、起動時再読込は、候補画像を現在とは別の`ImageSession`へpreflightし、成功後に
だけ対応一覧とセッションを一括導入する。版0.5.0までの公開試験は、JPEG取消、無効PNGから後続JPEG取消、
空群診断、移動先全候補失敗で旧session・pairs・folders・出力先が不変であることを検査した。版0.5.1の
追加試験は、preflightと前後移動の無modal skip、全候補失敗時の理由集約、直接指定の一回通知、
出力snapshotによるfallback許可、一時的失敗の非恒久cache化を別に検査する。旧28件からこの追加契約の
成功を導出しない。

| 追補AT | 契約 | 現在の実装 | 必要な自動証拠 | 状態 |
| --- | --- | --- | --- | --- |
| FLEX-AT-001 | 両入力群が非零同数の時だけ対応計画を作り、不一致時は0組と候補数を示す | `pairing.py`, `models.py`, `main_window.py` | 公開試験`test_candidate_count_mismatch_blocks_every_mode_and_ignores_unsupported_files`、`test_empty_candidate_group_reports_both_zero_counts_without_touching_output`。同数成功は後続対応試験が検証 | implemented / automated-local |
| FLEX-AT-002 | 厳格対応を既定とし、旧キーだけを採り、自然順へ自動fallbackしない | `models.py`, `pairing.py`, `dialogs.py`, `main_window.py` | 公開自然順試験が同じ不正名で厳格経路0組を検証。既定・破損設定fallbackと旧キー全回帰は別試験 | implemented / automated-partial |
| FLEX-AT-003 | 明示自然順、NFKC数値整列、全対応表の毎回確認、取消時不変、出力衝突時全拒否 | `pairing.py`, `dialogs.py`, `main_window.py` | 公開試験`test_natural_order_pairs_independently_using_nfkc_and_numeric_runs`、`test_natural_order_output_collision_blocks_the_entire_plan`、`test_pairing_plan_has_no_output_side_effect_until_finalize`、`test_natural_confirmation_cancel_has_no_output_or_window_state_side_effect`。起動時/手動再走査の再確認は実装証拠 | implemented / automated-partial |
| FLEX-AT-004 | JPEG一件ごとに取消既定の警告を出し、取消時は状態とファイルを不変にする | `dialogs.py`, `main_window.py`, `session.py` | 公開試験`test_jpeg_session_requires_opt_in_then_saves_rgb_png_without_mutating_sources`、`test_jpeg_cancel_precedes_unsaved_resolution_and_preserves_current_edit`、`test_folder_selection_jpeg_cancel_precedes_output_probe`、`test_folder_preflight_rolls_back_when_invalid_png_skips_to_cancelled_jpeg`、`test_discarded_navigation_commits_only_after_a_later_jpeg_is_accepted`。実buttonの既定・Escapeは未試験 | implemented / automated-partial |
| FLEX-AT-005 | ICC後sRGBを`SAVE_RGB`二乗距離最小へ割り当て、tieは小ラベル、乱数なし | `image_io.py` | 公開試験`test_quantize_l_all_values_matches_squared_srgb_distance_and_lower_tie`、`test_quantize_rgb_uses_lower_label_for_an_exact_tie_without_mutating_input`。ICC有効・不正profileは未試験 | implemented / automated-partial |
| FLEX-AT-006 | JPEG入力hash不変、取込後未保存、明示保存だけで同寸RGB三色PNGを出力 | `image_io.py`, `session.py`, `main_window.py` | 公開試験`test_load_ternary_accepts_l_and_rgb_jpeg_without_writing_source`、`test_load_ternary_rejects_oriented_cmyk_and_fake_jpeg_without_writing`、`test_jpeg_session_requires_opt_in_then_saves_rgb_png_without_mutating_sources` | implemented / automated-local |
| FLEX-AT-007 | 任意の正寸法を許し、原・三値不一致は双方の実寸付きで拒否し、resizeしない | `image_io.py`, `session.py`, `canvas_transform.py`, `main_window.py` | 公開試験`test_session_accepts_arbitrary_matching_dimensions`、`test_pair_dimension_failure_is_transactional_and_preserves_old_session`。複数寸法のGUI表示は未試験 | implemented / automated-partial |
| FLEX-AT-008 | 既存出力を対と同寸に限定し、保存PNGも対と同寸にする | `image_io.py`, `session.py`, `main_window.py` | 公開JPEG session試験が新規保存寸法を検証。既存出力不一致と入力fallbackは未試験 | implemented / automated-partial |
| FLEX-AT-009 | `H>100`末尾100行、`H<=100`保護なしを全経路で共有する | `constants.py`, `image_io.py`, `operations.py`, `canvas.py`, `main_window.py` | 公開試験`test_dynamic_protected_start_normalization_and_operations`が`H=80/100/101/1536`、正規化、塗りを検証。筆・境界・解析・保存の全経路は既存回帰との組合せ証拠 | implemented / automated-partial |
| FLEX-AT-010 | 参照原画像は復号可能性を門とし、表示用RGB化、ICC退避、Orientation反映後寸法照合を行い、入力を変更しない | `image_io.py` | 公開試験`test_original_reference_normalizes_decodable_encodings_without_writing`、`test_original_reference_uses_exif_transposed_dimensions_without_writing`、`test_original_reference_still_rejects_undecodable_data_without_writing` | implemented / automated-local |
| FLEX-AT-011 | version 1.1の既存出力自動優先と入力JPEG確認抑止。version 1.2の選択源分離は証明しない | `session.py`, `main_window.py`, `dialogs.py` | 公開試験`test_existing_output_is_automatically_preferred_without_source_confirmation`、`test_existing_output_bypasses_jpeg_confirmation_and_quantization`を履歴証拠として保持 | superseded / automated-local (version 1.1) |
| FLEX-AT-012 | 対応付けの非零同数を維持し、正常出力を選んだ編集用画像対では未使用入力を復号・検査せず、入力選択時は厳格検査する | `session.py`, `main_window.py`, `image_io.py` | `test_output_resume_ignores_invalid_input_for_open_and_later_save`、`test_input_open_keeps_strict_validation_when_valid_output_exists`、`test_gui_auto_prefers_valid_output_when_unused_input_is_invalid`、`test_direct_open_pair_without_source_uses_output_priority`、`test_cold_start_auto_opens_first_strict_pair_from_existing_output` | implemented / automated-local |
| FLEX-AT-013 | 原画像のEXIF表示方向反映後寸法と選択ラベル源を幅・高さ完全一致で照合し、ラベルPNGのOrientation 2〜8を拒否する | `image_io.py`, `session.py` | `test_output_resume_compares_output_with_display_oriented_original_only`、`test_output_resume_requires_exact_width_and_height`、`test_label_png_with_orientation_is_rejected_without_auto_rotation` | implemented / automated-local |
| FLEX-AT-014 | preflight・前後移動は不正候補をmodalなしで飛ばし、全候補失敗時は理由を状態表示へ集約し、直接指定は一回通知する。出力由来・分類不能の失敗を恒久的な画像対cacheへ入れない | `main_window.py`, `errors.py` | `test_folder_preflight_skips_invalid_pair_without_modal_error`、`test_preflight_reports_every_failure_in_status_when_no_pair_is_usable`、`test_directional_navigation_skips_invalid_pair_without_modal_error`、`test_preflight_falls_back_from_output_and_skips_unknown_failures_without_modal`、`test_directional_navigation_skips_output_and_unknown_failures_without_modal`、`test_direct_invalid_pair_reports_target_once`、`test_transient_open_failure_is_reported_but_not_cached_as_pair_error`、`test_cancelled_output_fallback_has_exactly_one_error_notification` | implemented / automated-local |
| FLEX-AT-015 | fallback許可を出力snapshotへ結び付け、同じsnapshotでは再確認せず、変更後に再検査し、正常ならOUTPUTへ戻す。明示sourceは自動選択へ読み替えない | `main_window.py`, `image_io.py`, `errors.py` | `test_accepted_output_fallback_is_not_reconfirmed_for_same_snapshot`、`test_accepted_output_fallback_is_invalidated_after_output_replacement`に加え、`test_direct_output_fallback_binds_failure_to_the_failed_snapshot`、`test_direct_output_fallback_reopens_valid_replacement_changed_during_modal`、`test_direct_output_fallback_aborts_input_commit_when_snapshot_changes`が失敗後・確認中・仮INPUT読込中の置換を検出し、旧許可を流用せずOUTPUTへ戻す。`test_explicit_input_remains_explicit_after_accepted_output_fallback_changes`が明示INPUT保持とsource省略時OUTPUT再評価を固定する | implemented / automated-local |
| FLEX-AT-016 | OUTPUT再開の保存は未使用入力の変更・破損・削除で止めず、INPUT開始では入力変更検査を維持する | `session.py`, `main_window.py` | `test_output_resume_ignores_invalid_input_for_open_and_later_save`がOUTPUT読込後の未使用入力置換・削除を、`test_input_source_external_change_screen_branches`がINPUT開始時の変更検査を固定 | implemented / automated-local |
| FLEX-AT-017 | 同一snapshotをstrict-firstで検査し、復旧可能な外部PNGだけをICC best-effort sRGBと共通最近傍規則で非破壊三値化する。選択源は`OUTPUT`、状態は未保存とし、DPI metadataは受否に使わず、明示保存だけが同pathを厳格RGB三値PNGへ置換する | `image_io.py`の`load_editable_output_image`、`_decode_label_png_snapshot`、`_load_recoverable_output_png`、`quantize_srgb_to_labels`、`session.py`、`models.py`、`main_window.py` | 公開`test_external_output_recovery_public_format_matrix`がbit depth 1/2/4/8、mode `1/L/RGB/P/LA/RGBA`、実使用alpha全255の`P+tRNS`と元hash不変を、`test_external_output_recovery_rejects_unsafe_cases_without_writing`が透明・半透明alpha、16-bit、寸法、破損・非PNG、IEND後の余剰データを、`test_external_output_recovery_orientation_and_single_snapshot_contract`がOrientationと単一snapshotを検証する。`test_external_output_recovery_uses_rgb_fallback_for_invalid_icc_without_write`が不正ICCのRGB退避を、`test_external_output_recovery_expands_samples_for_valid_icc_color_space`がPをRGB、LAをLへ展開してからCMSへ渡すことを、`test_external_output_recovery_ignores_dpi_metadata`が72/300 DPIのファイルhash差・ラベル一致を固定する。`test_external_output_is_recovered_as_dirty_output_and_saved_canonically`、`test_recovered_output_save_detects_external_replacement`、`test_preflight_opens_external_output_set_without_modal_or_source_write`、`test_cold_start_recovers_external_output_without_input_jpeg_confirmation`が`OUTPUT`未保存、元hash不変、保存競合、要保存表示、明示保存後の厳格PNG、冷間起動を検証する。実物ICCによる色変換はWindows判断門に残す | implemented / automated-partial / windows-pending |
| FLEX-AT-018 | 復旧不能OUTPUTに対し、起動・フォルダ選択・再走査preflightは同じ対の厳格INPUTへfallback確認modalなしで退避し、理由を保持する。INPUT JPEG確認、直接指定snapshot確認、前後移動skipは維持する | `main_window.py`の`_preflight_first_usable_pair`、`_choose_edit_source`、`_open_pair`、`session.py`、`image_io.py` | 公開`test_cold_start_falls_back_to_input_for_nonrecoverable_output_without_modal`、`test_folder_selection_falls_back_to_input_for_nonrecoverable_output_without_modal`、`test_rescan_falls_back_to_input_for_new_nonrecoverable_output_without_modal`が三preflight入口の同一対INPUT退避・理由表示・元hash不変・無modalを検証し、`test_preflight_falls_back_from_output_and_skips_unknown_failures_without_modal`が後続候補探索も固定する。`test_preflight_rechecks_output_replaced_after_failed_snapshot`はpreflight失敗snapshotの置換後にOUTPUT優先を再評価する。`test_folder_selection_jpeg_cancel_precedes_output_probe`、`test_folder_preflight_rolls_back_when_invalid_png_skips_to_cancelled_jpeg`、`test_directional_navigation_skips_output_and_unknown_failures_without_modal`、`test_accepted_output_fallback_is_not_reconfirmed_for_same_snapshot`、`test_accepted_output_fallback_is_invalidated_after_output_replacement`、`test_cancelled_output_fallback_has_exactly_one_error_notification`がJPEG確認、前後移動、直接指定snapshot境界を固定する。Windowsでは三入口を実包装・実ファイルでも別々に確認する | implemented / automated-partial / windows-pending |

## マウス入力割当追補の受入条件

`PTR-AT-*` は `TIE-ADD-PTR-001` だけに属し、v1.5本文の `AT-*` とは別の要求身元である。
局所統合証拠は2026-08-19（Asia/Tokyo）のmacOS開発作業木で `uv run pytest` を実行した
344件成功である。次表の試験名はこの非公開機能試験集合に属する。

| 追補AT | 契約 | 現在の実装 | 現在の自動証拠 | 状態 |
| --- | --- | --- | --- | --- |
| PTR-AT-001 | 七基底token、Ctrl/Alt/Shift正規化、完全一致 | `action_registry.py`, `main_window.py` | `test_pointer_tokens_are_canonical_bindings`, `test_pointer_modifiers_are_ordered_and_unsupported_modifiers_are_rejected`, `test_pointer_wheel_assignment_is_exact_and_overrides_fixed_zoom` | implemented / automated-local |
| PTR-AT-002 | Meta、鍵盤+mouse、複数button、専用double-click、drag、水平wheel、macro、global入力を拒否 | `action_registry.py`, `settings_dialog.py`, `main_window.py` | `test_qt_pointer_helpers_have_one_mapping_and_reject_unsupported_input`, `test_capture_consumes_double_click_sequence_without_second_candidate`, `test_capture_takes_vertical_wheel_but_excludes_zero_and_horizontal`。複数button・drag・macroの専用試験は未追加 | implemented / automated-partial |
| PTR-AT-003 | マウス追補自体は操作を増やさず、現行操作群と主・副割当を維持して鍵盤・ポインタ間で同じ競合移動・取消を適用 | `action_registry.py`, `settings_dialog.py` | `test_at_038_049_all_operations_have_one_registry_and_menu_surface`, `test_pointer_bindings_share_conflict_space_with_keyboard_bindings` | implemented / automated-local |
| PTR-AT-004 | button・垂直wheelを一候補として捕捉し、左・中・wheelの固定操作置換を適用前確認 | `settings_dialog.py` | `test_capture_takes_supported_mouse_button_and_consumes_its_release`, `test_capture_takes_vertical_wheel_but_excludes_zero_and_horizontal`, `test_fixed_pointer_override_confirmation_can_cancel_without_mutation`, `test_fixed_pointer_override_confirmation_can_accept` | implemented / automated-local |
| PTR-AT-005 | 主画像Canvas限定で作動し、設定画面・一般UI入力を奪わない | `main_window.py`, `settings_dialog.py` | `test_pointer_assignments_are_canvas_only_and_disabled_exact_input_is_consumed`, `test_dialog_does_not_intercept_idle_mouse_or_wheel` | implemented / automated-local |
| PTR-AT-006 | 未割当の固定操作を保ち、割当済み完全一致は無効時もfallbackせず、一時パン中の左buttonを優先 | `main_window.py`, `canvas.py`, `action_registry.py` | `test_pointer_wheel_assignment_is_exact_and_overrides_fixed_zoom`, `test_assigned_disabled_pointer_binding_is_consumed_without_invocation`, `test_mouse_left_assignment_preserves_existing_temporary_pan_escape_route`と既存wheel・pan回帰 | implemented / automated-local |
| PTR-AT-007 | SINGLE・STEP・HOLDをevent種別どおり実行し、wheel→HOLDとMouseLeft系→一時パンを拒否 | `action_registry.py`, `settings_dialog.py` | `test_registry_dispatches_pointer_single_step_and_hold_bindings`, `test_hold_binding_constraints_apply_to_assignment_and_initial_bindings`, `test_invalid_hold_pointer_bindings_show_core_reason_without_mutation` | implemented / automated-local |
| PTR-AT-008 | double-click二押下、wheel一event単位、押下token latch、同期modal再入、非活性化・焦点・捕捉喪失・設定適用で全HOLD解放 | `action_registry.py`, `main_window.py` | `test_pointer_runtime_double_click_counts_two_presses_and_stroke_blocks_new_inputs`, `test_pointer_button_hold_uses_press_token_and_deactivation_cleans_latch`, `test_pointer_latch_exists_before_reentrant_callback_and_is_not_recreated`, `test_dialog_cancel_and_deactivate_clear_pointer_release_latches`。pointer HOLDのFocusOut・UngrabMouse専用試験は未追加 | implemented / automated-partial |
| PTR-AT-009 | 筆描画中は完成・取消入力だけを所有し、ほかのポインタ割当を発火も予約もせず消費 | `canvas.py`, `main_window.py` | `test_pointer_runtime_double_click_counts_two_presses_and_stroke_blocks_new_inputs`, `test_edit_009_view_change_during_brush_is_rejected_not_reserved` | implemented / automated-local |
| PTR-AT-010 | schema 2保存、schema 0/1鍵盤割当の無警告移行、既存path維持、欄単位の破損fallback、正常な明示割当を低優先fallbackより優先 | `settings_model.py`, `action_registry.py` | `test_schema_one_keyboard_settings_migrate_to_schema_two_without_warning`, `test_schema_two_pointer_bindings_roundtrip`, `test_missing_shortcut_uses_default_unknown_id_is_ignored_and_corruption_is_local`, `test_invalid_fallback_does_not_displace_a_valid_explicit_binding`, `test_missing_default_does_not_displace_a_valid_explicit_binding`。schema 0の任意鍵盤割当と組織名・応用名を跨ぐ専用移行試験は未追加 | implemented / automated-partial |
| PTR-AT-011 | Windows実機でBack/Forward、precision touchpad/inertia、modal中release、旧schema保持を確認 | 配布候補 | macOSの合成Qt eventだけでは閉じない | windows-pending |

## 表示比較（暗）追補の受入条件

`DISP-CMP-*`は`TIE-ADD-DISP-CMP-001`だけに属し、v1.5の`AT-*`、柔軟入力追補の
`FLEX-AT-*`、マウス追補の`PTR-AT-*`とは別の要求身元である。公開試験
`tests/test_display_comparison_contract.py`は画素・状態・永続化契約を再現するが、Windows実描画と
人間受理を閉じない。

| 追補ID | 契約 | 現在の実装 | 現在の自動証拠 | 状態 |
| --- | --- | --- | --- | --- |
| DISP-CMP-001 | 主画面表示欄の常設「比較（暗）」チェックと状態表示 | `control_panel.py`, `main_window.py` | `test_control_defaults_and_semantic_signals`、主画面操作同期試験 | implemented / automated-local / windows-pending |
| DISP-CMP-002 | `view.toggle-darken-comparison`を既定割当なしのSINGLE操作として追加し、現行39操作を一台帳・一menu surfaceで扱う | `action_registry.py`, `main_window.py`, `settings_dialog.py` | `test_registry_is_v15_plus_the_display_comparison_operation`、`test_at_038_049_all_operations_have_one_registry_and_menu_surface`、公開`test_disp_cmp_002_007_action_sync_and_restart_do_not_touch_document_state` | implemented / automated-local / windows-pending |
| DISP-CMP-003 | 既定無効。無効時の保存色Lightenと疑似色SourceOverを維持し、ON→OFFで復元 | `canvas.py` | 公開`test_disp_cmp_003_005_default_off_and_darken_cover_saved_and_pseudo_colors`と既存`test_view_005_composes_at_native_resolution_then_scales_once` | implemented / automated-local / windows-pending |
| DISP-CMP-004 | 有効時は原解像度で成分最小値と原画像不透明度を合成し、完成像を一度だけ拡縮 | `canvas.py` | 公開`test_disp_cmp_003_005_default_off_and_darken_cover_saved_and_pseudo_colors`、`test_disp_cmp_004_006_opacity_endpoints_and_single_layer_views_are_stable`。中間値は8-bit量子化差2以内、端点完全一致 | implemented / automated-local / windows-pending |
| DISP-CMP-005 | 保存色・現在疑似色の双方へ比較（暗）を適用し、ラベルを変えない | `canvas.py` | 公開`test_disp_cmp_003_005_default_off_and_darken_cover_saved_and_pseudo_colors` | implemented / automated-local / windows-pending |
| DISP-CMP-006 | 三値のみ、原画像のみ、双方非表示、不透明度0で非表示層の内容を混入させない | `canvas.py` | 公開`test_disp_cmp_004_006_opacity_endpoints_and_single_layer_views_are_stable` | implemented / automated-local / windows-pending |
| DISP-CMP-007 | 切替・設定適用・復元を表示専用とし、ラベル、基準、履歴、改訂、未保存判定、保存PNGを変えない | `canvas.py`, `main_window.py` | 公開`test_disp_cmp_002_007_action_sync_and_restart_do_not_touch_document_state`、`test_disp_cmp_007_saved_png_is_identical_before_and_after_display_toggle`、`test_at_062_setting_apply_does_not_touch_image_state` | implemented / automated-local / windows-pending |
| DISP-CMP-008 | 既定false、QSettings `view/darkenComparison`、schema 2据置、Apply/Cancel境界、欠損・破損fallback | `settings_model.py`, `settings_dialog.py`, `main_window.py` | 公開`test_disp_cmp_008_settings_roundtrip_and_corrupt_value_fallback`、設定model往復、dialog適用・取消回帰 | implemented / automated-local / windows-pending |

## AT表外の横断要求証拠

- KEY-004: `test_action_registry.py` が単文字・数字・記号と標準文字編集キーを編集欄では
  抑止し、Ctrl+S、Ctrl+Shift+B、Alt+1、F5等の非編集命令を過剰抑止しないことを検証。
  `test_v15_main_window.py::test_key_004_numeric_input_keeps_standard_up_key_for_the_widget` は
  数値欄のUpを操作割当へ漏らさず、部品自身へ渡す主窓経路を検証した。
- SAVE-009: `INPUT`を選んだセッションの原画像・入力三値外部変更について、取消、読込済み
  snapshot保存、再読込破棄を`test_v15_main_window.py::test_input_source_external_change_screen_branches`で
  自動検証した。`OUTPUT`再開では未使用入力を保存基準に含めず、`FLEX-SAVE-001`とFLEX-AT-016で
  別に追跡する。

## 現在環境では閉じない証拠

- AT-030とAT-074のWindows表示倍率100%、125%、150%、200%および実モニター移動。
- AT-050の日本語入力方式ON/OFF、PortableText保存、Windowsキーボード配列依存の
  NativeText表示。
- AT-070のWindows 10 / 11における実プロセス間ロック、ロック中断後の回復。
- Windows 10 / 11上の対象業務PCでの性能目標、ファイルロック、ACL、Unicode長パス。
- Windows配布物からの起動、設定永続化、画面外に残った旧geometryの復旧。
- PTR-AT-011のBack・Forward button、precision touchpadのwheel分割・inertia、modal画面中の
  HOLD解放、schema 0/1から2への実設定移行。
- FLEX-AT-003〜009のWindows実ファイル名自然順、全対応表の可読性、JPEG警告・ICC変換、
  入力hash不変、対象業務寸法、`H=100/101`境界。
- FLEX-AT-012〜016のWindows実ファイルによる選択源分離、ラベルOrientation、無modal探索、直接通知、
  fallback snapshot、未使用入力変更後のOUTPUT保存。
- FLEX-AT-017〜018のWindows実ファイルによる外部出力限定復旧、元hash不変、要保存表示、厳格保存、
  復旧不能出力からの三preflight入口INPUT退避、DPI metadata非依存、実物ICCとalphaの判定。
- DISP-CMP-001〜008のWindows描画器での比較（暗）画素、100%〜200%表示、疑似色、再起動復元、
  切替前後の保存PNG不変。
- 同じ側車ロック規約に従わない別アプリが、最後の内容照合と `os.replace` 呼出しの間へ
  割り込む競合。協調writerは保存ロックで排他するが、`os.replace` 自体は内容条件付き置換
  ではない。
