# macOS画面有り利用経路・ローカル検証記録

## 記録範囲

- 日付: 2026-08-21（Asia/Tokyo）
- アプリケーション版: `0.8.0`
- 作業枝: `codex/local-acceptance-and-test-strategy`
- 基線commit: `6eb283c391f2d78e4542c2b1058759ae5f0fcac4`
- 対象: 基線上の未commit作業木。Windows配布候補ではない
- 環境: macOS 26.5.2 arm64、Python 3.11.15、PySide6 / Qt 6.11.1
- 実行時刻: 2026-08-21T03:01:38+09:00〜2026-08-21T03:15:07+09:00
- 表示環境: HDP-V104、3840×2160、Qt論理寸法1920×1080、機器画素比2.0、60 Hz
- 表示条件: 1168×768の通常Qt窓、全体表示41.1%、合成画像2048×1536
- 入力条件: Computer Useによる画面有りpointer操作と画面像観測
- 起動条件: source入口を一時的なmacOS `.app` 外被から`execv`した。外被は試験専用で、
  リポジトリ、wheel、Windows one-folder候補のいずれにも含めない

`0.8.0`はこの実行時の応用metadataであり、同じ版文字列を持つ過去の局所wheelやsdistを指さない。
本記録の修正版sourceは下記の関連源SHA-256で区別する。

本記録は、[用途指向試験補強](local-verification-2026-08-20-local-acceptance.md)で施錠により
停止していた画面有り観測を続行した証拠である。sourceを実窓で動かした局所証拠であり、物理マウス、
Windows 10 / 11、PyInstaller成果物、対象職場PCの性能を受理しない。

実行対象を同定するSHA-256は次のとおりである。最終二項は診断用一時物であり、製品構成要素ではない。

| 対象 | SHA-256 |
| --- | --- |
| `src/ternary_image_editor/canvas.py` | `b5fb083de1f73545749b7f946cf107c39c3b9ef448881f6caa3b13933e5823ce` |
| `tests/test_transient_memo_layer_contract.py` | `f0ce32d6d2f82ded94326aab37b038ee091a19805d36bffdc1467495c3ddd850` |
| 合成fixture manifest | `9eca37f0c2b4d183374152e207b967b30652866d4f0cb6cfaae9d60fbab5f459` |
| 一時`.app`実行入口 | `cb30c5034b12cfb2fa63371fa653df9b64efc452598def258c04df0092e2a477` |
| 右button事象記録 | `f0431174bcefd030f1238e197939a3445c8c1692d94fde151013a8481da3dff5` |

## 要求と観測の対応

| 要求 | 用途危険 | 本記録の手順・観測 | 局所状態 |
| --- | --- | --- | --- |
| FLEX-AT-012 | 入力版と編集済み出力を取り違える | 二組の厳格対応、既存出力の自動優先、出力なしの入力版使用、別process再起動後の両出力優先 | headed-local-pass / windows-pending |
| AT-011、AT-013 | 筆跡が途切れる、Undo・Redoが一操作にならない | 左dragの描画、Undo、Redo、保存を通常窓で操作 | headed-local-pass / target-performance-pending |
| FLEX-AT-008、AT-028、AT-029 | 保存物が画像対寸法・三値契約を外れる、入力を上書きする | 二出力の形式・対寸法・三色検査、四入力fileのSHA-256不変 | headed-local-pass / windows-filesystem-pending |
| DISP-CMP-001、004、007 | 比較表示が働かない、文書状態や保存物を変える | 比較（暗）の切替と画面像変化、保存済み状態維持、メモ保存前後の出力hash一致 | headed-local-partial / windows-renderer-pending |
| MEMO-AT-001〜005、007 | 一点が残らない、履歴が分裂する、筆との重なりや保存境界が誤る | 欠陥再現、右一点、Undo・Redo、筆重畳消去、複合Undo、保存時破棄を画面有りで観測 | headed-local-partial / physical-right-drag-and-windows-pending |

`headed-local-pass`と`headed-local-partial`は本記録内の局所状態語であり、要求追跡表の
`automated-local / automated-partial / windows-pending`を置換しない。

## 代表画像群

試験用一時directoryに、厳格対応する二組を生成した。原画像は色付き背景、三値画像は直径約250画素の
粒子五個を持つ。全画像の表示寸法は2048×1536である。一組目だけ既存出力を先に置き、中央の矩形により
入力版との違いを画面上でも判別できるようにした。画像binaryは公開資料集合へ収載しない。

| 役割 | file名 | 試験前SHA-256 |
| --- | --- | --- |
| 原画像1 | `①aaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg` | `68862a38c984dce70e4800e8da1f5605886f57a8e81715a3ecaf451fc01f7caa` |
| 原画像2 | `②bbbbbbbbbbbbbbbbbbbbbbbbbbb.png` | `ea90597688977b5134a38c56e1430ce6e1690e07aaa3e147b76895b2ea4d0fc9` |
| 入力三値1 | `001aaaaaaaaaaaaaaaaaaaaaaaaaaa.png` | `8768b5f22a443b3b771cb8abbf95ac8f2c943f0c99ca51e79a4004fddd70fbf8` |
| 入力三値2 | `002bbbbbbbbbbbbbbbbbbbbbbbbbbb.png` | `c58190d132b8fd7d7d55c42008731a6cecdf5b8541e8643b671bd5d0a3535e5a` |
| 既存出力1 | `001aaaaaaaaaaaaaaaaaaaaaaaaaaa.png` | `8e11f2cb9640fdc13c56beef25cc5df08d1a830a2ae981a3cae33935f49fe2b0` |

これは合成fixture一組の実行証拠であり、外部由来画像、ICC、全寸法、全形式を代表しない。

## 画面有り利用経路

| 手順 | 期待 | 観測 |
| --- | --- | --- |
| sourceを通常窓で起動 | 主画面が操作可能になる | 暗色主画面、tool bar、画像一覧、対象外一覧、表示・編集・境界・検査欄を描画した |
| GUIから三folderを設定し厳格対応 | 二組を導入する | 一組目を`1/2｜編集済み版｜出力あり｜保存済み`として自動表示した。一覧は二組を示した |
| 一組目の画面像を確認 | 入力版でなく既存出力を使う | 色付き原画像と粒子五個に、既存出力だけが持つ中央矩形が重なった |
| 比較（暗）をON | 表示だけが成分最小合成へ変わる | 背景が暗い比較像へ変わり、文書状態は保存済みのままだった |
| 左buttonで筆描画、Undo、Redo、保存 | 一操作を可逆にし、厳格PNGへ保存する | `筆描画を反映した`、Undo、Redo、`保存完了`を順に観測した |
| 二組目へ移動 | 出力がないため入力版を使う | `2/2｜入力版｜出力なし｜読込済み・未変更`を表示した |
| 筆径75 pxで二組目を描画して保存 | 新規出力を作る | `編集済み・未保存`から`出力あり｜保存済み`へ遷移した |
| 応用processを終了し、別processで再起動 | 保存済み出力を自動優先する | 一組目、二組目とも`編集済み版｜出力あり｜保存済み`として再読込した |

二組目の同一process内で保存直後に表示された`入力版｜出力あり`は、そのsessionが入力snapshotを
編集元にしたという由来表示である。別process再起動後は`編集済み版`となり、出力優先再開を確認した。

## 保存物と入力不変

全手順後も四入力fileのSHA-256は上表と完全一致した。出力は次のとおりだった。

| 出力 | 最終SHA-256 | 内容検査 |
| --- | --- | --- |
| 出力1 | `675fbfbd13b0346acba6da9a2763cd427db874fe0bf8a6ac0f4a6668dede5380` | PNG、2048×1536、RGB、黒・灰・白の三色、DPI metadataなし |
| 出力2 | `6902c20f01b3b80cf56238c9c9b05305c38be55c5ceeb83cd281ce41d7cc48ac` | PNG、2048×1536、RGB、黒・灰・白の三色、DPI metadataなし |

DPI metadataがないことは本fixtureの観測値であって、受理条件ではない。受否は表示寸法と画素内容で
判定し、DPI値を使っていない。

## 画面有り観測で検出したメモ一点欠陥

最初の右単一クリックは、Qtの`mousePressEvent`と`mouseReleaseEvent`へ右buttonとして届き、押下後に
`memo_drawing=true`となった。しかし解放後は`has_memo=false`で、Undo項目も作られなかった。
操作自動化系の入力欠落ではなく、応用内部の点描画欠陥である。

同じ作業木を画面外でも`scale=41.1%`として再現すると、太いpenによる
`QPainter.drawLine(p, p)`が画素を作らず、メモ差分が`None`になった。既存の点試験は1600%表示で
pen幅が1へ縮退する条件だけを通り、低倍率で太くなるpenの零長線分が試験設計から抜けていた。

修正は`ImageCanvas._draw_memo_segment`の一点だけである。始点と終点が同じ時は外縁penと内縁penの双方を
`drawPoint`で描き、移動区間は従来どおり`drawLine`で描く。公開事故回帰試験
`test_memo_003_single_right_click_at_low_zoom_commits_a_dot`を
`tests/test_transient_memo_layer_contract.py`へ追加した。

修正後の同じ画面有り経路では次を観測した。

- 右単一クリックで黄色い点が最上段に残り、状態欄が`メモ一筆`、Undoが有効になった。
- Undo一回で点が消え、Redo一回で同じ点が戻った。
- 正常保存後はメモとそのUndo項目が消え、出力1のSHA-256は保存前後とも
  `675fbfbd13b0346acba6da9a2763cd427db874fe0bf8a6ac0f4a6668dede5380`で一致した。
- 点を横切る通常筆で点が消え、Undo一回で通常筆のラベル差分と点が同時に戻った。
- もう一度Undoして試験用メモを除去し、未保存ラベル変更のない状態で終了した。

この失敗は「源に右button分岐がある」「高倍率でpen幅1の点が描ける」という既存証拠だけでは実利用の一点入力を
保証できない反例である。事故回帰を公開包装対象へ置き、源接続試験だけへ戻さない。

## 外部作用と後始末

- 一時`.app`外被と事象記録仕掛けは試験用一時領域だけに作り、製品源へ収載しない。
- GUI試験前にQSettingsを退避し、応用終了後に復元した。復元後SHA-256は退避前と同じ
  `91576aca446fcc33031fbcc99b856b48467aba7d608978b9cdcfabe73ee02c12`だった。
- 試験用原画像と入力三値画像は不変である。出力folderだけを通常の保存作用で更新した。

## 修正後の局所検査

画面有り再観測後の同じsourceと公開試験を、macOS開発環境で次のように検査した。

- 全試験: `530 passed in 6.03s`
- sdist収載対象の公開九試験: `143 passed in 2.09s`。通信を使わず、既存環境を
  `uv run --locked --no-sync`で変更しない独立実行で確認した
- 低倍率右単一クリック事故回帰: 一件を単独収集し、成功
- Ruff、固定lock検査、`src`と`tests`のPython bytecode compile、`git diff --check`: 成功
- 通信を使わない一時directory構築: 版0.8.0のsdistとwheelを生成し、sdistへ本記録と
  公開九試験だけが全て収載された

上記件数はこの未commit作業木の観測値であり、版番号そのものの恒久属性ではない。
`--no-sync`の公開九試験は現存環境の再利用証拠であり、固定lockからの新規環境再現を単独では
証明しない。sdist/wheel構築もWindows one-folder候補、PyInstaller、Explorer起動を証明しない。

## 保証限界と次の判断門

次は本記録で閉じていない。

- 物理マウスによる右drag、中button drag、canvas上のwheel、戻る・進むbutton。
- Computer Useのpointer表示が画面像へ重なるため、応用がOSカーソルを隠したことの視覚受理。
- 複数DPI・monitor移動、焦点喪失、捕捉喪失、長時間連続筆、入力対光子時間。
- Windows 10 / 11、PowerShell構築制御流、PyInstaller one-folder成果物、Explorer起動。
- 外部由来の業務画像、実ICC、Windows file lock・ACL、非協調writer窓。

最終配布判断は[Windows最終受入チェックリスト](windows-acceptance-checklist.md)へ候補SHA-256と実結果を
記録し、人間が`accept / reject / hold`として行う。

## 復帰面

| 項目 | 内容 |
| --- | --- |
| 文脈 | 0.8.0未commit sourceの画面有り代表経路と、MEMO-003低倍率一点欠陥の事故回帰 |
| 現在状態 | macOS source通常窓の対象手順、全530試験、公開九試験143件、静的検査、sdist/wheel構築は局所成功。Windowsは未受理 |
| 次行動 | Windows候補を構築し、物理入力、DPI、PyInstaller成果物、Explorer起動を人間受理する |
| 詳細参照 | [一時メモ層追補](transient-memo-layer-addendum.md)、[要求追跡表](requirements-traceability.md)、[試験戦略](test-strategy.md)、[Windows判断門](windows-acceptance-checklist.md) |
