# Ternary Image Editor

原画像を参照しながら、三値ラベル画像（黒・灰・白）を画素単位で修正し、入力を上書きせず
PNGとして別保存するWindows向けデスクトップGUI。

筆、塗り潰し、二種の境界生成、Undo・Redo、原画像の重畳、疑似色、画素格子、小領域強調、
操作割当を一つの画面にまとめている。

## 現在の状態

| 項目 | 状態 |
| --- | --- |
| アプリケーション版 | `0.3.0` |
| 対象環境 | Windows 10 / 11 64-bit |
| ソース実行環境 | Python 3.11.x、`uv` |
| 提供形態 | ソース実行、Windows配布候補のローカル構築 |
| Windows最終受入 | 未完了 |

現時点では、受理済みのWindows実行ファイルをGitHub Releasesで提供していない。macOS上の
局所自動試験は通しているが、Windows実機、高DPI、対象業務PC性能、実マウス・タッチパッド、
生成した実行ファイルの起動は別の最終確認事項である。

## ソースから起動する

Gitと[`uv`](https://docs.astral.sh/uv/)を用意し、PowerShellで次を実行する。

```powershell
git clone https://github.com/morie-lene/ternary-image-editor.git
Set-Location .\ternary-image-editor
uv sync --locked --python 3.11
uv run ternary-image-editor
```

GitHubのZIPを使う場合は、展開後に`pyproject.toml`、`uv.lock`、`src`、`docs`、`scripts`が
並ぶフォルダをPowerShellで開き、後半二命令を実行する。macOSでは同じ命令によるGUI起動を
局所確認済み。Linuxは配布対象外かつ未確認である。

## 対応データ

原画像と三値画像は、座標が完全に一致した`2048 × 1536`ピクセルでなければならない。
自動拡縮、回転、位置合わせは行わない。

| 種別 | 条件 |
| --- | --- |
| 原画像 | `.png`、`.jpg`、`.jpeg`、`.bmp`、`.tif`、`.tiff`。復号後が8-bit RGBまたは8-bitグレースケール |
| 三値画像 | 8-bit PNG。RGBまたはグレースケールで、`#000000`、`#808080`、`#FFFFFF`だけを含む |
| 出力 | 2048 × 1536、8-bit RGB PNG、アルファなし、上記三色だけを含む |

原画像ではアルファ、索引色、CMYK、16-bit以上、EXIF / TIFF Orientation 2〜8を受理しない。
三値画像でもアルファ、索引色、16-bit、上記以外の色を受理しない。ICC色特性付き原画像は
表示用メモリ上だけでsRGBへ変換し、原ファイルは変更しない。

### ファイル名の対応規則

単に並び順が同じ画像同士を組にするわけではない。次の両条件を満たす一対だけを一覧へ載せる。

| 原画像の幹名先頭 | 三値画像の幹名先頭 | 対応群 |
| --- | --- | --- |
| `①` | `001` | `001` |
| `②` | `002` | `002` |

- 拡張子を除く幹名をUnicode NFCへ正規化する。
- 幹名末尾27 Unicodeコードポイントが完全一致すること。大文字と小文字は区別する。
- 幹名が27コードポイント未満、想定外の先頭、対応相手なし、同じ対応キーの重複は対象外にする。
- 選択したフォルダ直下だけを走査し、下位フォルダは探索しない。
- 出力名は三値画像の幹名を継承し、出力フォルダ直下へ`.png`として保存する。
- 出力フォルダには、二つの入力フォルダと異なる場所を指定する。

たとえば原画像を`②...jpg`、三値画像を`002...png`として、双方の幹名末尾27文字を一致させる。
原画像を`002...jpg`や`⑤...jpg`で始めても対応対象にはならない。

## 基本操作

1. 「フォルダ選択」で原画像、入力三値画像、編集済み画像出力の三フォルダを指定する。
2. 一覧から画像対を開く。既存出力があれば、編集済み版または入力版のどちらから始めるか選ぶ。
3. 原画像の重畳、不透明度、疑似色、格子を調整し、筆・塗り潰し・境界生成で三値画像を直す。
4. 「保存」または既定の`Ctrl+S`で、出力フォルダへ検証付きPNGを保存する。
5. 画像移動や終了時に未保存変更があれば、保存・破棄・中止を選ぶ。

利用者割当がない場合は、ホイール上下が拡大・縮小、中ボタンドラッグが自由移動、左ボタンが
現在の道具操作という固定操作になる。`Space`を保持した左ドラッグでも一時的に自由移動できる。
右・戻る・進むボタンには固定操作がない。「設定」では左右・中・戻る・進むボタンとホイール上下へ、
`Ctrl`、`Alt`、`Shift`を組み合わせた操作を割り当てられる。割当は主画像キャンバス上だけで
作動し、設定画面や一般UIのクリック・ホイールは奪わない。詳しい優先・解放規則は
[マウス入力割当追補](docs/mouse-input-bindings-addendum.md)を参照する。

## 重要な挙動と制限

- 原画像と入力三値画像は読取専用で、アプリケーションから上書きしない。
- 三値画像の下端100行（`y=1436..1535`）は、全画素の入力検査後に黒へ正規化し、編集中も
  保護する。保存時にも黒化を再適用する。
- 疑似色、格子、小領域強調、原画像、筆ポインタは表示専用で、保存画像へ混入しない。
- 三値画像を非表示にしている間は画素編集とUndo・Redoを停止する。
- 出力は一時PNGを再検査してから原子的に置換する。外部変更は内容のSHA-256で検出する。
- 異常終了後、保存前の編集内容は自動復元しない。

より細かな制約は[開発仕様書 v1.5](docs/ternary_image_editor_spec_v1_5.html)を正とする。

## 公開検査と証拠境界

公開リポジトリには、包装と構築経路に必要な`tests/test_packaging.py`を格納している。

```powershell
uv run pytest
uv run ruff check .
uv build
```

公開cloneでは、`uv run pytest`が次の構造的不変条件を検査する。

- sdistとwheelを実際に生成できること。
- sdistにREADME、`pyproject.toml`、`uv.lock`、Windows構築入口、v1.5仕様書、マウス入力割当
  追補、公開包装試験が入ること。
- wheelにアプリケーション、GUI入口、三形式のアイコン、実行入口metadataが入ること。
- Windows構築スクリプトが公開包装試験を必須入力とし、`uv sync`、pytest、Ruff、PyInstallerの
  直後に終了符号を検査し、成果物の配置と内容を検査すること。

公開包装試験は、画像編集機能全体の受入、PowerShell制御流の実行、PyInstaller成果物の妥当性、
Windows上の実行ファイル起動を証明するものではない。機能試験一式は開発作業場だけにあり、
その局所記録と公開cloneで再現できる包装試験を混同しない。Windows固有事項は
[Windows最終受入チェックリスト](docs/windows-acceptance-checklist.md)で人間が判定する。

## Windows配布候補を構築する

Windows上で、リポジトリ直下から次を実行する。

```powershell
uv --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

構築スクリプトは次を順に行い、いずれかが失敗すれば停止する。

1. 固定lockからPython 3.11環境を同期する。
2. `tests/test_packaging.py`が通常ファイルとして存在することを検査し、`tests/`配下の試験を
   pytestで実行する。不合格なら非零終了として構築を止める。
3. Ruffによる静的検査を実行する。
4. PyInstallerでone-folder配布候補を生成する。
5. 実行ファイルが既定位置に一つだけあり、非零長でMZ先頭を持つことを検査し、SHA-256を表示する。
   同梱アイコン、v1.5仕様書、マウス入力割当追補は配置と固定hashを照合する。

成果物は、実行時の作業フォルダにかかわらず次へ生成される。

```text
dist/TernaryImageEditor/TernaryImageEditor.exe
```

one-folder形式なので、`TernaryImageEditor.exe`だけを抜き出さず、
`dist/TernaryImageEditor/`一式を保つ。生成後はExplorerから実行ファイルを開き、起動・表示・
読込・編集・保存・終了をWindows最終受入チェックリストへ記録する。この確認が終わるまで、
生成物を受理済み配布物とは扱わない。

別の作業フォルダから構築する場合は、スクリプトを絶対パスで指定できる。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\work\ternary-image-editor\scripts\build_windows.ps1"
```

## 仕様・検証資料

| 文書 | 役割 |
| --- | --- |
| [開発仕様書 v1.5](docs/ternary_image_editor_spec_v1_5.html) | 現行の要求正本 |
| [マウス入力割当追補](docs/mouse-input-bindings-addendum.md) | v1.5のマウス割当部分だけを限定上書き |
| [開発仕様書 v1.1](docs/ternary_image_editor_spec_v1_1.html) | 旧版の履歴。現行判断には用いない |
| [要求追跡表](docs/requirements-traceability.md) | 要求、実装、検証層、未受理事項の対応 |
| [設計判断](docs/design-decisions.md) | 仕様未規定の採用判断と差戻し条件 |
| [実装計画](docs/implementation-plan.md) | 作業単位と現在状態 |
| [v1.5ローカル検証記録](docs/local-verification-2026-08-18.md) | 版0.2.0までの局所自動試験と性能観測 |
| [マウス入力割当・ローカル検証記録](docs/local-verification-2026-08-19-pointer-bindings.md) | 版0.3.0の局所証拠 |
| [Windows最終受入チェックリスト](docs/windows-acceptance-checklist.md) | Windows実機の結果を記録し、人間が配布可否を決める表 |

v1.5仕様書のSHA-256は
`ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`。構築スクリプトも
このv1.5固定値とマウス入力割当追補の固定hashを照合する。

## 利用条件

現時点では`LICENSE`ファイルを配置していない。再利用条件は未提示であり、ライセンス選定は
別途の判断事項である。
