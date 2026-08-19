# 参照原画像・編集元優先・界面文ローカル検証記録

- 実行日: 2026-08-19（Asia/Tokyo）
- 対象応用版: `0.5.0`
- 対象追補: `TIE-ADD-FLEX-001` version 1.1
- 実行環境: macOS、Python 3.11、Qt画面外plugin
- 人間によるWindows最終受理: 未実施

本記録は、参照専用原画像の受付緩和、既存編集済み画像の自動優先、入力JPEG確認の実編集元限定、
利用者向け診断・確認文の整理について、現在の作業木で得た局所証拠を残す。Windows配布候補の
実行、実画面の可読性、対象業務画像の色再現を受理した記録ではない。

1〜10節は版0.5.0・追補version 1.1を検証した時点の履歴証拠であり、件数、成果物名、hash、当時の
検証対象を後続版に合わせて改竄しない。追補version 1.2が置換した選択源・寸法・保存基準については
11節を現行境界とし、旧376件や旧28件から追加契約の成功を導出しない。

## 1. 検証対象

- 原画像は対応拡張子とPillowによる復号可能性を門とし、RGBA、索引色、16-bit、CMYKを表示用RGBへ
  メモリ内変換する。
- 原画像のEXIF Orientationを表示方向へ反映した後、入力三値画像との寸法を照合する。
- 原画像のICC色特性を解釈できない場合は通常RGB変換へ退避し、入力ファイルを変更しない。
- 既存編集済み出力があれば確認なしで編集元にし、なければ入力三値画像を使う。
- 正常な既存出力を使う場合、入力三値画像がJPEGでも三値化確認と三値化処理を行わない。
- 不正な既存出力から入力版へ切り替える時、未保存破棄、外部変更、不可逆三値化、既存出力置換では
  必要な確認を維持する。
- 確認箱と診断は、対象、理由、変更される状態、取消結果を分け、命令調と曖昧なYes/Noを避ける。
- 三値PNG、三値JPEG、既存出力PNG、保存PNGの厳格な色・形式・寸法検査は緩和しない。

## 2. 公開入力契約試験

実行命令:

```sh
QT_QPA_PLATFORM=offscreen uv run pytest -q tests/test_flexible_input_contract.py
```

結果:

```text
28 passed
```

主な追加証拠:

- `test_original_reference_normalizes_decodable_encodings_without_writing`
- `test_original_reference_uses_exif_transposed_dimensions_without_writing`
- `test_original_reference_still_rejects_undecodable_data_without_writing`
- `test_existing_output_is_automatically_preferred_without_source_confirmation`
- `test_existing_output_bypasses_jpeg_confirmation_and_quantization`

これらは入力内容hash不変、転置後寸法、復号失敗、編集元、未保存状態、JPEG確認・三値化の不実行を
検査する。色の目視妥当性やWindows固有の復号器差は検査しない。

## 3. 局所全試験

実行命令:

```sh
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -p no:cacheprovider -q
```

結果:

```text
376 passed in 3.98s
```

この全件数には公開sdistへ収載しない開発用試験も含む。公開包装へ収載する試験は
`tests/test_flexible_input_contract.py`の28件と`tests/test_packaging.py`の4件、計32件である。
公開包装試験はこの二ファイル以外を公開試験として収載しないことも検査する。したがって、公開cloneで
再現できる32件と、現在の開発作業木にある376件を同一の証拠範囲として扱わない。

局所試験では、危険操作の確認箱について対象path、操作名、ButtonRole、取消既定、Escape時の取消を
固定した。本文全体や改行位置は固定せず、文言の微修正を不要に阻害しない。

## 4. 静的検査・依存固定・差分形式

実行命令:

```sh
uv run ruff check .
uv lock --check
git diff --check
```

結果:

```text
All checks passed!
Resolved 24 packages
```

`pyproject.toml`、応用内の`__version__`、`uv.lock`は`0.5.0`で一致した。依存package集合の追加・削除は
ない。

## 5. Python包装

一時フォルダを`--out-dir`へ指定して実行した。

```sh
uv build --out-dir <mktempで作成した一時フォルダ>
```

結果:

- `ternary_image_editor-0.5.0.tar.gz`を生成した。
- `ternary_image_editor-0.5.0-py3-none-any.whl`を生成した。
- 構築処理は終了符号0で完了した。
- `tests/test_packaging.py`は4件成功し、版、入口、アイコン、公開試験、三つの規範文書、Windows構築
  scriptの固定hash検査を確認した。

この結果はPythonのsdist / wheelを対象とし、Windowsのone-folder配布候補やexe起動を証明しない。

## 6. 画面外GUI煙試験

一時QSettingsを使い、主windowを生成、表示処理、閉鎖した。

観測結果:

```text
version=0.5.0
expected_size=None
startup_shutdown=ok
```

Qt画面外pluginは`Sans Serif`代替と`propagateSizeHints()`非対応の警告を出したが、起動・閉鎖は終了符号
0で完了した。この煙試験は実画面の改行、長いpath、標準ボタンの日本語表示、高DPI、実マウス入力を
受理しない。

## 7. 規範文書hash

実行命令:

```sh
shasum -a 256 \
  docs/ternary_image_editor_spec_v1_5.html \
  docs/flexible-input-pairing-addendum.md
```

結果:

```text
ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497  docs/ternary_image_editor_spec_v1_5.html
eca3870587a3dc292e21c80f0eb294b0dbaf8b5f1cddbf1771835f23a1f3c1b5  docs/flexible-input-pairing-addendum.md
```

基線v1.5 HTMLは変更していない。原画像と編集元優先の変更は別identityの追補version 1.1で限定上書き
した。構築script、README、要求追跡表、実装計画は追補の新hashと一致する。

## 8. 安全性・互換性・構成境界

- `git diff -- pyproject.toml uv.lock`で、両ファイルの変更が応用版`0.4.0`から`0.5.0`への同期だけで
  あることを確認した。依存package、Python範囲、入口、構築backend、試験設定は変更していない。
- 認証、認可、network通信、秘密情報、telemetry、外部log送信は追加していない。診断箱へ対象pathと
  OS / Pillowの理由を表示する既存境界だけを使う。
- 原画像と入力三値画像への書込経路は追加していない。公開試験は受理した全原画像とJPEG入力の
  SHA-256不変を検査した。書込先は従来の明示出力PNG、同一フォルダ一時PNG、協調lockに限る。
- 原画像の受付拡大でもPillowの展開爆弾制限を維持し、復号失敗と読込中変更を拒否する。三値画像と
  出力画像の厳格検査、保存前後の内容照合、原子的置換を変更していない。
- 公開挙動変更は`0.5.0`、追補version 1.1、README、要求追跡表、Windowsチェックリストへ明記した。
  QSettings schemaと既存設定値は変更しないため、設定移行は不要である。
- 追加分岐は既存出力を使うJPEG入力の量子化を避けるための一経路であり、JPEG復号・色管理は共通
  helperへ集約した。新規依存や将来用抽象は追加していない。

## 9. 独立査読

実装・試験・文書差分を、実装担当とは別の読取専用査読で確認した。重大・中程度の所見はなく、
ローカル統合可能と判定した。原画像だけの受付緩和、既存出力の無対話優先、入力JPEG確認の実編集元
限定、危険操作の取消既定、三値画像と出力画像の厳格検査維持を確認した。

軽微な管理事項として、本記録は新規文書であるため、公開コミット時の収載漏れを防ぐ必要がある。
本査読はWindows配布受理や実画面の目視確認を代行しない。

## 10. 未完了境界

- Windows 10 / 11の配布候補構築とexe起動。
- WindowsでのRGBA、索引色、16-bit、CMYK、Orientation、ICC異常を含む実原画像の表示確認。
- 長い日本語pathを含む診断箱の改行・可読性と、OS標準ボタンの表示確認。
- 無効な既存出力から入力版へ切り替え、既存出力を置換する一連の実画面確認。
- ICC退避時の表示は参照継続を優先し、厳密な色再現を保証しない。
- 透明情報を持つ原画像は表示用RGB化でalphaを保持しないため、透明画素の見え方は実データで確認する。
- 対応拡張子外の原画像は引き続き候補外であり、任意のPillow対応形式を無制限には探索しない。

以上は`windows-pending`または明示した残危険であり、局所自動試験から完了を導出しない。

## 11. 版0.5.1・追補version 1.2の後続境界

版0.5.1では、対応付け上の原・入力対と、実際に開く原画像＋選択ラベル源を分ける。原・入力群の
非零同数門は維持するが、対応計画成立後に正常な`OUTPUT`を選んだ場合は未使用入力を復号・検査・
保存基準にしない。`INPUT`を選んだ場合は厳格検査を維持する。寸法はEXIF Orientation反映後の原画像と
選択ラベル源を幅・高さ完全一致で照合し、ラベルPNGのOrientation 2〜8は拒否する。

preflightと前後移動は不正候補をmodalなしで飛ばし、直接指定は対象と理由を一回通知する。不正出力から
入力版へ切り替える許可は出力snapshotへ結び付け、同じsnapshotでは再確認しない。出力が変われば
再検査し、正常なら`OUTPUT`へ戻し、なお不正なら再確認する。出力由来または分類不能の失敗は恒久的な
画像対cacheへ入れない。`OUTPUT`再開後は未使用入力の変更・破損・削除だけで保存を止めない。

この後続契約には、少なくとも次の局所回帰試験を追加し、コード経路の局所試験成功を確認した。

- `test_output_resume_ignores_invalid_input_for_open_and_later_save`
- `test_output_resume_compares_output_with_display_oriented_original_only`
- `test_input_open_keeps_strict_validation_when_valid_output_exists`
- `test_label_png_with_orientation_is_rejected_without_auto_rotation`
- `test_folder_preflight_skips_invalid_pair_without_modal_error`
- `test_preflight_reports_every_failure_in_status_when_no_pair_is_usable`
- `test_directional_navigation_skips_invalid_pair_without_modal_error`
- `test_direct_invalid_pair_reports_target_once`
- `test_accepted_output_fallback_is_not_reconfirmed_for_same_snapshot`
- `test_accepted_output_fallback_is_invalidated_after_output_replacement`
- `test_transient_open_failure_is_reported_but_not_cached_as_pair_error`
- `test_cancelled_output_fallback_has_exactly_one_error_notification`

後続作業で追補version 1.2の固定SHA-256を包装検査へ同期し、全410試験、公開66試験、Ruff、
`uv lock --check`、`git diff --check`、sdist / wheel、画面外GUI煙試験が成功した。版0.5.1の証拠は
[保存済み出力再開・選択源境界ローカル検証記録](local-verification-2026-08-19-output-resume.md)へ分離する。
この後続証拠を版0.5.0の成果へ遡及合成せず、Windows最終受理も閉じない。
