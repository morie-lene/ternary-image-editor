# ローカル検証記録 2026-08-18

この記録はWindows最終受理の代替ではない。現在のmacOS開発機で自動化可能な契約を
確認した証拠と、v1.1時点の実寸観測を分けて記す。

## 環境と正本

- macOS 26.5.2 (25F84)、arm64、Apple M4
- Python 3.11.15
- Qt/PySide6 6.11.1
- 現行正本 v1.5 SHA-256:
  `ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`
- 履歴正本 v1.1 SHA-256:
  `8e4705469d5472968c41120b6e4e47ea898c9eb0429719d862b885a1d5bad0ec`
- 応用版: `0.2.0`

## v1.5現在の自動検査

現時点の全試験結果は次のとおり。292件を検証集合の主証拠とし、1.82秒は今回走行の
観測時間である。

```text
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
292 passed in 1.82s

.venv/bin/python -m ruff check .
All checks passed!

.venv/bin/python -m ruff format --check .
46 files already formatted

.venv/bin/python -m compileall -q src tests packaging
exit 0

uv lock --check
Resolved 24 packages; exit 0
```

v1.5追加試験は次を含む。

- 下端100行の全体検証後正規化、正規化前の内容基準、未保存判定、履歴非追加、保存時の
  防御的再正規化。
- 筆、塗り潰し、二種境界による保護行書換え防止、保護領域指示、色別小領域集計。
- 原画像の8-bit `L` / `RGB`限定、ICCからsRGBへの記憶内変換、アルファ・索引色・CMYK・
  16-bit・Orientation拒否。
- 原解像度合成後の単一拡縮、倍率1.25刻み、三値非表示時の編集停止。
- 離散 `D×D` 円・正方形筆、偶数径余剰方向、Bresenham補間、筆予告と実変更マスク一致、
  Esc取消と正常解放の分離。
- v1.5表どおりの不変ID付き38操作（単発29、刻み8、保持1）、既定割当、主・副割当、
  競合移動、反復意味、再割当後のQAction更新。
- 設定作業値、適用・取消、二頁・38行一覧・絞込、キー入力待機、予約入力拒否、色差64境界、
  スキーマ付きQSettings往復、未知ID無視、欠落既定補完、局所破損回復。
- キー入力待機以前から押されていたControl/Alt/Shift/Metaを、未観測でも主キーeventの
  修飾状態から推定し、汚染された主キーと共に全KeyUpまで無視してから新chordだけを取得。
- 原画像・入力三値・出力のSHA-256再検査、入力変更と出力変更の例外分離、同一出力の
  非待機側車lock、lock取得失敗時の既存出力・未保存内容維持。
- 履歴位置から独立した内容基準比較、NFC正規化後27コードポイント対応、大文字小文字区別。
- fit中のwindow寸法変更、手動倍率中の中心維持、DPR変更時の中心・格子・筆閾値再計算。
- 主窓38操作のcallback・QAction・メニュー一意性、全割当解除後の設定到達とGUI一時パン
  latch、保持キー再割当、修飾付き保持キーで修飾キーを先に離した後の主キーKeyUp解除。
- 編集可能な文字・数値欄で単文字割当とUp/Down/Enter/Return/Shift+Home、
  Ctrl+Backspace等の標準編集キーを操作へ漏らさず、Ctrl+S等の非編集命令は維持する文脈判定。
- 選択色循環のメニュー・ボタン・キー経路一致、配列・未保存・改訂・履歴・道具・倍率不変、
  意味名・保存色・筆指示の同期。
- 三値非表示時の筆・塗り潰し・境界・Undo・Redo停止と、再表示後の履歴・未保存内容保持。
- 原画像・入力三値の外部変更に対する取消、読込済みスナップショット保存、再読込破棄。
- 読込後に外部出力が新規出現した保存競合の取消で、一覧を「出力あり」へ更新しつつ、
  未保存配列・履歴・外部出力内容を維持する主窓遷移。
- 旧「出力不正」cacheを外部削除・置換の競合検出時に破棄し、取消後の実在状態を
  「出力なし」または「出力あり」へ同期しつつ、未保存配列・履歴と置換済み外部内容を維持。
- 遅延検査で判明した不正対のエラー一覧移送と、有効対だけを辿る移動。
- 未変更画像の明示保存による「出力なし」から「出力あり」への遷移、設定適用時の画像・基準・
  履歴不変、下端正規化の変更画素数通知。

要求ごとの自動化境界は [要求追跡表](requirements-traceability.md) を正とする。上記292件の
成功だけから、AT-034〜079の全てを端から端まで受理済みとは解釈しない。

## v1.5包装・隔離煙試験

同じ版0.2.0の作業木からsdistとwheelを構築し、wheelだけを与えた隔離Python 3.11環境で
公開版、操作台帳、GUI入口を確認した。

```text
uv build
dist/ternary_image_editor-0.2.0.tar.gz 生成
dist/ternary_image_editor-0.2.0-py3-none-any.whl 生成

QT_QPA_PLATFORM=offscreen uv run --isolated --no-project --python 3.11 \
  --with dist/ternary_image_editor-0.2.0-py3-none-any.whl python <smoke-script>
wheel_smoke=ok version=0.2.0 operations=38 main_window=ok
```

## 代表経路煙試験（v1.1履歴）

一時フォルダ内で実PNG一対を作成し、対応付け、入力版読込、四近傍塗り潰し、一操作確定、
正式保存、出力再読込までを公開Python入口で一巡した履歴結果は次のとおり。

```text
status=ok
pairs=1
input_hashes_unchanged=true
output_rgb_png_valid=true
saved_state_clean=true
```

これは局所データ層の代表実行であり、v1.5 GUI配布物の煙試験ではない。

## 公開面・構成

- 版0.2.0の `uv lock --check` で24包のlock整合を確認した。直接依存はNumPy、Pillow、
  PySide6、SciPyの範囲から増えていない。
- `src/`, `packaging/`, `scripts/` に本アプリ独自の通信、利用者口座、認証・認可、遠隔API、
  遠隔測定の公開面はない。
- `QSettings` の永続対象は三フォルダ、window geometry/state、原画像・三値表示、疑似色
  ON/OFFと三色、原画像不透明度、格子自動、小領域表示、道具、筆形状・径、境界方式・太さ、
  38操作の主・副割当とスキーマ版である。
- 選択ラベル、倍率、表示中心、現在画像、画像内容、基準配列、Undo・Redo履歴、秘密値は
  永続化しない。
- 公開入出力は対話GUIで選ぶ局所画像ファイルである。機械可読CLI/API/MCPの出力契約は
  存在しない。
- Windows構築スクリプトはnative終了値、期待exeの配置、非零長、MZ先頭、候補一意性、
  SHA-256取得の事後条件を静的回帰試験で固定している。Windows上の実行は未閉鎖。

## 実寸性能観測（v1.1基線、v1.5保証ではない）

2048×1536の合成画像一対を一回ずつ処理した旧基線。v1.5では下端正規化、離散筆、
原解像度合成、入力SHA検査、保存lockが加わったため、同じ値を現行保証へ流用しない。

| 処理 | v1.1観測 |
| --- | ---: |
| セッション読込 | 0.031秒 |
| 筆予告1移動・径512（150点逐次、QImage再構築込み） | 最大18.5ms、p95 18.0ms |
| 半画像の四近傍塗り潰し | 0.033秒 |
| 無側境界・太さ64 | 0.981秒 |
| 非無側境界・太さ64 | 0.977秒 |
| 小領域解析 | 0.023秒 |
| 検証付き原子的保存 | 0.136秒 |
| キャンバス表示像構築 | 0.017秒 |
| 過程全体の最大RSS | 253.5 MiB |

## 未閉鎖

- v1.5経路による2048×1536実寸性能の再測定。
- Windows 10/11実機と表示倍率100/125/150/200%のAT-030/074。
- 日本語入力方式、JIS/US配列、PortableText保存・NativeText表示のAT-050。
- Windows対象業務PC上の反復性能、実プロセス間保存lock、強制終了回復、ACL、Unicode長パス。
- PyInstaller配布候補を開発環境のないWindows利用者権限で起動する確認。
- 側車lockに従わない別アプリが最終内容照合と `os.replace` 呼出しの間へ割り込む非協調
  保存競合。
- 実業務データに対する最終的な人間の目視受理。
