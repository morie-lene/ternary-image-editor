# 一時メモ層・ローカル検証記録

## 記録範囲

- 日付: 2026-08-20（Asia/Tokyo）
- アプリケーション版: `0.8.0`
- 直前基線: 版0.7.1の筆追従局所更新を含む同一作業木
- 対象: `TIE-ADD-MEMO-001` version 1.0、`MEMO-AT-001`〜`MEMO-AT-010`
- 環境: macOS開発環境、`QT_QPA_PLATFORM=offscreen`
- 受理境界: Windows 10 / 11、実マウス、実モニター、配布候補の人間受理ではない

この記録は、一時メモ層の入力、表示、統一履歴、ラベル編集との複合操作、保存・画像交換境界、
公開契約、包装を局所検証した証拠をまとめる。自動試験とソース接続検査は、人間によるWindows最終
受理を代行しない。

## 要求と検査面

| 範囲 | 局所検査 | 証拠境界 |
| --- | --- | --- |
| 未割当右buttonと完全一致割当 | Canvas・主窓・設定確認の動的試験、公開ソース接続契約 | Windows実マウスbutton eventは未受理 |
| 最上段・非保存表示 | Canvas描画順、ラベル・未保存・保存PNG不変試験 | Windows描画器と実DPIの視認性は未受理 |
| 一筆原子性 | 点入力、drag、Esc、非活性化、焦点／捕捉喪失、命令排他 | 実window managerと機器捕捉喪失は未受理 |
| 単一履歴と複合項目 | 公開`test_memo_history.py`の順序、Redo枝、前後適用、メモ除去、上限 | 利用者の操作感は未受理 |
| ラベル重複消去 | 同色筆、異色筆、取消、Undo・Redo、非筆編集の変更画素 | 実マウス軌跡と高DPI境界は未受理 |
| 三値非表示時の次項目門 | `memo-only`適用、`label-containing`停止、非飛越し | Windows操作面の目視は未受理 |
| 保存・画像交換 | 成功専用破棄、失敗・取消維持、保存中入力停止 | Windows file lock、ACL、実配布候補は未受理 |
| 包装と版身元 | sdist必須集合、追補固定hash、応用版0.8.0、性能JSON版0.7.1 | PowerShell・PyInstallerのWindows実行は未受理 |

## 実行結果

次の命令を同じ作業木で実行した。

```text
QT_QPA_PLATFORM=offscreen uv run --locked pytest -q

QT_QPA_PLATFORM=offscreen uv run --locked pytest -q \
  tests/test_flexible_input_contract.py \
  tests/test_display_comparison_contract.py \
  tests/test_brush_responsiveness_contract.py \
  tests/test_memo_history.py \
  tests/test_transient_memo_layer_contract.py \
  tests/test_packaging.py

uv lock --check
uv run --locked ruff check .
uv run --locked python -m compileall -q src
uv build
git diff --check

QT_QPA_PLATFORM=offscreen uv run --isolated --no-project --python 3.11 \
  --with ./dist/ternary_image_editor-0.8.0-py3-none-any.whl python <smoke-script>
```

結果は次のとおりである。

- 全試験: `520 passed in 5.47s`
- 公開六試験: `133 passed in 1.61s`
- Ruff、固定lock検査、Python bytecode compile、`git diff --check`: 成功
- 版0.8.0 sdist / wheel構築: 成功
- 版0.8.0 wheel隔離環境の主画面生成・表示・event loop終了: `wheel_smoke=ok version=0.8.0 exit=0`

包装試験は、sdistへ収載した公開試験と追補のSHA-256が作業木と一致すること、性能JSONが
測定時版0.7.1を保持することも検査した。Qt画面外pluginは代替書体と
`propagateSizeHints()`非対応の警告を出したが、煙試験の終了符号は0だった。

## 独立査読で検出して修正した事項

- メモ中に既存の`Space` HOLD解放を呑み、一時移動状態を残す競合を修正した。新しい命令は遮断した
  まま、押下済みHOLDの解放だけを通す。
- 右解放時の座標更新がDPI差を検出して一筆を取り消した後、失われた最終位置を参照する例外経路を
  修正した。DPI・画面変更通知でも即時同期し、取消後は履歴を作らない。
- 画像読込時の全画面RGBAメモ像と、一筆ごとの全画面既訪問maskの無条件確保を廃した。メモ像は
  初回使用時だけ確保し、空なら解放する。一筆の初期値は実際に触れた画素索引だけを一度保持する。
  確保失敗は一筆を開始せず診断する。

修正後の全520試験には、遅延確保、空操作非確保、疎な一意索引、確保失敗、DPI中の右解放、
`DevicePixelRatioChange`と`ScreenChangeInternal`の各回帰を含む。これはC++割当器が極端な
過大確保でprocessを停止する場合や、Windows実モニター移動を保証する証拠ではない。
修正後の読取専用再査読は専用7試験、対象統合233試験、Ruffを再実行し、中程度以上の未解決を
検出せず、局所統合を`ready_for_parent_integration_with_residuals`と判定した。

## 2026-08-21の後続事故回帰

上記520試験と査読は本記録時点の履歴証拠として保持するが、画面有りsource経路で41.1%表示の
右単一クリックが点を残さない欠陥を後から検出した。既存点試験は高倍率によりpen幅が1へ縮退する
条件だけを通り、低倍率で太いpenとなる零長`drawLine`を検出していなかった。

MEMO-003に従い、一点だけを`drawPoint`へ分岐し、320×240・41.1%の実Canvasへ右`mouseClick`を
送る公開事故回帰を追加した。画面有りの再観測では、点表示、Undo・Redo、保存時破棄、筆重畳消去と
複合Undoを確認した。詳細は
[macOS画面有り利用経路・ローカル検証記録](local-verification-2026-08-21-headed-macos.md)を参照する。
これは既存の成功件数を取消すものではないが、その成功だけでは低倍率一点入力を保証できなかった
事実を隠さない。事故回帰追加後は全530試験、公開九試験143件、Ruff、固定lock、bytecode compile、
差分形式、sdist/wheel構築が成功し、sdistに本事故回帰と画面有り記録が収載された。
Windows実マウスと配布候補は引き続き未受理である。

## 安全性・外部作用の確認

- `pyproject.toml`と`uv.lock`の差分を照合し、依存package集合と版範囲に追加・削除・変更がないことを
  確認した。変更は応用版metadata、sdist収載物、性能markerの証拠境界に限る。
- 認証、認可、秘密情報、network通信、telemetry、clipboard、外部logの入口を追加していない。
  追加源差分にもHTTP、socket、credential、password、API key、secretの使用はない。
- メモは現在processのQImageと履歴差分だけに属し、入力画像、原画像、QSettings、回復fileへ書かない。
  既存の明示保存経路へ渡す値もラベル配列のままである。保存PNG不変と入力hash不変は機能試験で検査した。
- 公開CLI、API、MCP、機械可読応答schemaは追加していない。利用者向けの新しい公開面はCanvas上の
  右button入力、表示、Undo・Redo、状態・診断文と、標準Python包装metadataである。

残危険は、下記のWindows実入力・描画・配布判断門、極端に密な一筆で疎集合の要素費が増えること、
C++側の過大QImage確保がPythonの診断経路へ戻らずprocessを停止し得ること、版0.8.0の実入力対光子
性能を未測定であることだ。局所成功からこれらを閉じない。

## 0.7.1性能基線との境界

`docs/brush-responsiveness-benchmark-2026-08-20.json`は版0.7.1で採取した原出力であり、
`application_version`を`0.7.1`のまま保持する。版0.8.0のsdistへ含める目的は、直前性能基線の
追跡可能性を保つことであって、0.8.0で再測定したという主張ではない。包装試験は応用版`0.8.0`と
性能証拠版`0.7.1`を別々に固定する。

## 未完了境界

- Windows 10 / 11の実マウスで、右button完全一致割当、点入力、drag、焦点・捕捉喪失を未確認。
- 100%、125%、150%、200%と異なるDPIモニター間で、メモ位置、太さ、補間、Undo画素を未確認。
- 疑似色、比較（暗）、格子、小領域強調を組み合わせた時の最上段視認性を実描画器で未確認。
- Windows file lock、ACL、外部変更確認を伴う保存失敗時のメモ・履歴維持を未確認。
- PyInstaller one-folder候補での入力、保存除外、画像交換、終了、再起動後非復元を未確認。
- 版0.8.0の筆性能、メモ描画の入力対光子時間、長時間連続メモによる履歴容量・応答を未測定。

最終判断は`docs/windows-acceptance-checklist.md`へ結果を記録した人間が
`accept / reject / hold`として行う。
