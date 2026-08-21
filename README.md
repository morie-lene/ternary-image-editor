# Ternary Image Editor

原画像を参照しながら、三値ラベル画像（黒・灰・白）を画素単位で修正し、入力を上書きせず
PNGとして別保存するWindows向けデスクトップGUI。

筆、塗り潰し、二種の境界生成、Undo・Redo、原画像の重畳、比較（暗）、疑似色、画素格子、
小領域強調、一時メモ、操作割当を一つの画面にまとめている。

## 現在の状態

| 項目 | 状態 |
| --- | --- |
| アプリケーション版 | `0.9.0` |
| 対象環境 | Windows 10 / 11 64-bit |
| ソース実行環境 | Python 3.11.x、`uv` |
| 提供形態 | ソース実行、Windows配布候補のローカル構築 |
| Windows最終受入 | 未完了 |

現時点では、受理済みのWindows実行ファイルをGitHub Releasesで提供していない。macOS上では
局所自動試験に加え、sourceを通常窓で起動した代表利用経路を観測している。ただし、Windows実機、
高DPI、対象業務PC性能、実マウス・タッチパッド、生成した実行ファイルの起動は別の最終確認事項である。
画面有り観測はComputer Useと試験専用の一時`.app`外被を用いたsource操作であり、製品launcherや
物理入力の受理ではない。

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

画像寸法は固定しない。幅と高さがともに正で、Orientationを表示方向へ反映した原画像と、実際に
編集元として選ばれた入力または既存出力の幅・高さが完全に一致しなければならない。ラベルPNGは
Orientationがないか1だけを受理し、2〜8は自動転置せず拒否する。原画像のOrientation表示反映を
除き、自動拡縮、切抜き、回転、位置合わせは行わない。`2048 × 1536`は対象用途と性能測定で使う
代表実寸であり、読込要件ではない。

| 種別 | 条件 |
| --- | --- |
| 原画像 | `.png`、`.jpg`、`.jpeg`、`.bmp`、`.tif`、`.tiff`。Pillowで復号できる参照画像 |
| 三値画像 | 厳格三色の8-bit PNG、または警告確認後に三値化する8-bit RGB / グレースケールJPEG |
| 出力 | 原画像の表示寸法と同寸の8-bit RGB PNG、アルファなし、`#000000`、`#808080`、`#FFFFFF`だけを含む |

原画像は参照表示だけに使うため、アルファ、索引色、CMYK、16-bit、EXIF / TIFF Orientationを
理由に拒否しない。Orientationは表示方向へ反映し、表示用RGBへメモリ上で変換する。埋込ICCを
解釈できない場合も通常のRGB変換へ退避する。原画像ファイルは変更しない。

入力版の三値PNGはアルファ、索引色、16-bit、上記以外の色を受理しない。三値JPEGを入力版として
開く時は取消既定の警告を出し、確認後に各画素をsRGB上の黒・灰・白へ二乗距離最小で割り当てる。
同距離なら番号が小さいラベルを採る。変換結果は明示保存した時だけ出力フォルダへPNG保存する。

既存出力は先に厳格な出力条件で検査する。寸法が一致し、Orientationがないか1で、透明画素を持たない
1/2/4/8-bit PNGなら、グレースケール、索引色、完全不透明のアルファ付き画像、三値外のRGB色も
メモリ上で同じ規則により三値化して編集を再開できる。元の出力は読込時に変更せず、一覧と状態欄へ
「要保存」を示す。明示保存した時だけ同じ出力pathを厳格なRGB三色PNGへ置換する。

### 画像群と対応付け方式

原画像フォルダと三値画像フォルダは、対応拡張子を持つ通常ファイルがそれぞれ1件以上あり、
その件数が同じでなければならない。0件または件数不一致では一組も読み込まない。下位フォルダと
対応外拡張子は候補数に含めない。

対応方式は次の二つから選ぶ。既定は「仕様キーで厳格対応」であり、厳格対応の失敗から自然順へ
自動で切り替えない。

#### 仕様キーで厳格対応

次の両条件を満たす一対だけを一覧へ載せる。

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
原画像を`002...jpg`や`⑤...jpg`で始めても、厳格対応の対象にはならない。

#### ファイル名の自然順で対応

利用者が明示選択した場合だけ、原画像群と三値画像群を別々に自然順整列し、同じ位置同士を
対応させる。数字列は数値として扱い、互換文字は整列専用にUnicode NFKCへ正規化する。

導入前に「番号／原画像／三値画像／出力PNG」の全対応表を必ず表示する。「中止」が既定で、
「この対応で読み込む」を選んだ時だけ導入する。確認は保存せず、起動時再走査や手動再走査を
含め、対応計画を作るたびに全件を再確認する。

## 基本操作

1. 「フォルダ選択」で三フォルダと対応方式を指定する。自然順なら、表示された全対応表を確認する。
2. 一覧から画像対を開く。厳格条件を満たすか限定復旧できる編集済み出力があれば原画像＋出力を
   自動的に開き、なければ原画像＋入力版を開く。
3. 原画像の重畳、不透明度、比較（暗）、疑似色、格子を調整し、筆・塗り潰し・境界生成で三値画像を直す。
4. 必要なら、未割当の右ボタンで保存対象外の一時メモを上描きする。生成の有効・無効と記入色は、
   menu barの「ヘルプ」直前にある「設定」で変更する。
5. 「保存」または既定の`Ctrl+S`で、出力フォルダへ検証付きPNGを保存する。
6. 画像移動や終了時に未保存変更があれば、保存・破棄・中止を選ぶ。

利用者割当がない場合は、ホイール上下が拡大・縮小、中ボタンドラッグが自由移動、左ボタンが
現在の道具操作という固定操作になる。`Space`を保持した左ドラッグでも一時的に自由移動できる。
未割当の右ボタンは一時メモ、戻る・進むボタンには固定操作がない。「設定」では左右・中・戻る・
進むボタンとホイール上下へ、`Ctrl`、`Alt`、`Shift`を組み合わせた操作を割り当てられる。右ボタンも
修飾キーを含む完全一致割当があれば割当操作を優先し、メモを描かない。割当は主画像キャンバス上だけで
作動し、設定画面や一般UIのクリック・ホイールは奪わない。メモ生成を無効にしても完全一致割当は
従来どおり作動する。「設定」はファイルmenu内ではなく、menu barの「ヘルプ」直前にあり、主toolbarと
control panelの既存入口も維持する。詳しい優先・解放規則は
[マウス入力割当追補](docs/mouse-input-bindings-addendum.md)と
[一時メモ層追補](docs/transient-memo-layer-addendum.md)を参照する。

## 重要な挙動と制限

- 原画像と入力三値画像は読取専用で、アプリケーションから上書きしない。
- 正常な既存出力は確認なしで編集元にする。この時、入力三値画像は対応付けにだけ使い、内容を復号せず、
  形式・色・寸法・Orientation・内容指紋を検査しない。対応計画成立後の出力読込と、既に開いた出力
  セッションの保存は、未使用入力の変更・破損・削除だけでは止めない。冷間起動または再走査では、原・
  入力群の非零同数を改めて検査する。
- 外部由来の既存出力が限定復旧可能なら、出力を変更せず三値化して`OUTPUT`の未保存状態で開く。
  DPI情報は受否に使わない。寸法差、Orientation 2〜8、16-bit、透明・半透明画素、破損または非PNGは
  復旧せず、拡縮、回転、位置合わせもしない。
- 起動、フォルダ選択、再走査の事前検査では、復旧不能な出力があっても同じ対の入力版が正常なら
  警告箱なしで入力版を開き、出力理由を一覧と状態欄に残す。入力版がJPEGなら既存の変換確認は省かない。
  一覧から直接指定した復旧不能出力は、入力版への切替えを一回確認し、その許可を出力内容に結び付ける。
  前後移動は復旧不能な候補を警告箱なしで飛ばす。
- 高さが100を超える三値画像は末尾100行を、全画素の入力検査後に黒へ正規化し、編集中も
  保護する。高さ100以下では保護領域を設けない。保存時にも同じ境界で黒化を再適用する。
- 比較（暗）は、現在の三値表示色と原画像のRGB成分ごとに暗い方を、原画像不透明度に応じて表示する。
  既定は無効で、疑似色の有無にかかわらず切替できる。ラベル、履歴、未保存判定、保存PNGは変えない。
- 疑似色、比較（暗）、格子、小領域強調、原画像、筆ポインタ、一時メモは保存画像へ混入しない。
- 筆移動は、離散筆と補間線分が実際に触れた矩形だけをラベル表示像へ反映する。同じ色を再度
  なぞった時は表示更新を行わない。Undo、取消、保存の画素契約は全画像更新時と同じである。
- 画像上では筆・塗り潰し・保護状態の独自ポインタが位置を示すため、OSカーソルを隠す。
  画像外では通常表示へ戻し、`Space`一時移動と中ボタン移動では開いた手・閉じた手を表示する。
- 中ボタン、または`Space`保持中の左ボタンで移動する間は、指示位置だけでなく表示域全体を毎移動ごとに
  再描画する。三値画像層の表示状態にかかわらず画像がドラッグへ追従し、解放時だけ跳ぶ状態を残さない。
- 一時メモは現在画像だけに属する最上段の上描きで、メモだけでは未保存状態にならず、画像移動・終了の
  保存確認も出さない。メモ一筆と通常編集は一つのUndo・Redo時系列を共有する。
- 設定画面では右クリックによるメモ生成を有効・無効にでき、記入色を`#RRGGBB`、色選択部品、既定復元で
  変更できる。有効・無効と色は再起動後も復元するが、メモ画素とメモ履歴は復元しない。設定変更は以後の
  一筆とメモポインタへ反映し、既に描いたメモを再着色しない。黒い外線と透過度は固定である。
- ラベル筆がメモへ重なった時は、同色ラベル上でも重なったメモを消し、ラベルとメモの差分を同じ
  履歴操作にする。筆取消・Undo・Redoでは両方を一緒に戻す。
- 正常保存と正常な画像交換では一時メモを破棄する。保存失敗、読込失敗、遷移取消では現在のメモと
  履歴位置を保つ。正常保存後のUndoで破棄済みメモを復活させない。
- 三値画像を非表示にしている間はラベル画素編集を停止する。次の履歴項目がメモだけならUndo・Redo
  できるが、ラベル差分を含む項目では停止し、その奥のメモ項目を飛び越さない。
- 出力は一時PNGを再検査してから原子的に置換する。外部変更は内容のSHA-256で検出する。
- 異常終了後、保存前の編集内容は自動復元しない。

より細かな制約は[開発仕様書 v1.5](docs/ternary_image_editor_spec_v1_5.html)を基線とする。
柔軟入力、対応付け、JPEG三値化、寸法、下端保護については
[柔軟入力・対応付け追補](docs/flexible-input-pairing-addendum.md)を優先し、マウス入力割当については
[マウス入力割当追補](docs/mouse-input-bindings-addendum.md)、比較（暗）の表示合成・設定・操作追加については
[表示比較（暗）追補](docs/display-comparison-addendum.md)、一時メモの入力・履歴・破棄境界については
[一時メモ層追補](docs/transient-memo-layer-addendum.md)を優先する。

## 公開検査と証拠境界

公開リポジトリには、入力契約を再現する`tests/test_flexible_input_contract.py`、表示比較契約を再現する
`tests/test_display_comparison_contract.py`、筆の画素・局所更新・比較性能を再現する
`tests/test_brush_responsiveness_contract.py`、一時メモの統一履歴を動的に検査する
`tests/test_memo_history.py`、重要な実装接続を検査する`tests/test_transient_memo_layer_contract.py`、
2048×1536の長筆・疎履歴を検査する`tests/test_real_size_workflow.py`、別processの保存lock・外部置換を
検査する`tests/test_external_process_conflicts.py`、隔離wheel検証scriptの契約を検査する
`tests/test_isolated_distribution_workflow.py`、包装・構築経路を検査する`tests/test_packaging.py`を
格納している。試験の選び方と証拠限界は[試験戦略](docs/test-strategy.md)を参照する。

```powershell
uv run pytest
uv run ruff check .
uv build
```

公開cloneでは、`uv run pytest`が次を検査する。

- 非零同数門、厳格／自然順の分離、NFKC数値整列、出力名衝突、確認取消時の無作用。
- JPEGの決定的三値化、PNG厳格経路の維持、JPEG入力hash不変、明示PNG保存。
- 外部出力PNGの限定復旧、単一snapshot、元出力hash不変、未保存状態、明示保存後の厳格RGB三色化、
  復旧不能出力から入力版への事前検査退避。
- 任意の同寸画像対、対寸法不一致の取引的失敗、`H=100/101`の下端保護境界。
- JPEG警告取消が現在の未保存編集より先に働き、現在状態を変えないこと。
- フォルダ変更・再走査・起動時再読込が別セッションで読込preflightを行い、JPEG取消、全候補失敗、
  件数門停止では旧セッション、対応一覧、フォルダ、出力先を変えないこと。出力probeは読込preflight、
  JPEG確認、未保存判断の後だけに行う。
- 正常出力の再開では未使用入力を復号・検査・保存基準にせず、入力版を選んだ時だけ厳格検査すること。
  起動時再読込と編集元を省略した直接入口でも同じ優先規則を使い、正常出力がなければ入力版へ戻ること。
- 原画像の表示方向反映後寸法と選択ラベル源の完全一致、ラベルPNGのOrientation 2〜8拒否。
- 事前走査・前後移動の無通知skip、直接指定の一回通知、全候補失敗時の理由集約、fallback許可の
  出力snapshot寿命、一時的な出力失敗・分類不能例外の非恒久cache化。
- 比較（暗）の既定無効、保存色・疑似色での成分最小合成、不透明度端点、片層表示、操作同期、
  再起動復元、破損設定の既定退避、画像状態不変。
- 筆の円・正方形、補間、画像外再進入、保護領域、同色無更新、変更矩形、比較表示画素、
  主画面の局所更新経路、非連続ポインタ更新、局所格子列挙、独自ポインタ表示中のOSカーソル
  非表示、同一process内の相対性能退行門。中ボタン／`Space`＋左ボタンと三値画像層の表示／非表示を
  組み合わせ、各ドラッグ移動の解放前に表示域全体が実際に再描画されること。
- 一時メモの右button完全一致優先、最上段・非保存性、一筆原子性、通常編集との単一時系列、
  ラベル筆による同操作消去、三値非表示時の次項目門、保存・画像交換の成功専用破棄と失敗維持、
  共通履歴上限への算入、生成・色設定の永続境界、設定入口。
- 2048×1536の長筆を局所矩形だけで更新して全表示結果と一致させ、メモ複合履歴と200件の疎履歴を
  全画像snapshot列へ膨張させずUndo・Redoできること。
- 別processが保持する協調保存lockを即時検出し、別processによる出力置換を既存出力と未保存編集を
  壊さず拒否すること。
- 隔離wheel検証scriptが現行版を一意に選び、同梱`uv.lock`からhash付き本番依存を書き出して、
  offline cacheから完全一致導入した一時環境だけを対象にすること。OS水準の通信遮断は主張しない。

- sdistとwheelを実際に生成できること。
- sdistにREADME、`pyproject.toml`、`uv.lock`、Windows構築入口、隔離wheel検証script、v1.5仕様書、
  柔軟入力・対応付け追補、マウス入力割当追補、表示比較（暗）追補、一時メモ層追補、試験戦略、
  macOS画面有り検証記録、一時メモ設定検証記録、パン中再描画検証記録、九つの公開試験が入ること。
- 版0.7.1で採取した筆性能JSONを`application_version: 0.7.1`の基線証拠として含め、応用版0.8.0以降の
  現行性能証拠へ偽装しないこと。
- wheelにアプリケーション、GUI入口、三形式のアイコン、実行入口metadataが入ること。
- Windows構築スクリプトが公開包装試験を必須入力とし、`uv sync`、pytest、Ruff、PyInstallerの
  直後に終了符号を検査し、成果物の配置と内容を検査すること。

公開入力契約試験は上記範囲の局所自動証拠であり、ICC付き実データ、全編集算法、画面全体、
Windows固有eventまでの端から端の受入ではない。公開包装試験も、PowerShell制御流の実行、
PyInstaller成果物の妥当性、Windows上の実行ファイル起動を証明しない。より広い開発作業場の
機能試験、公開cloneで再現できる九試験、Windows人間受理を混同しない。一時メモの公開接続契約は
重要経路の存在と低倍率右単一クリックの事故回帰を検査するが、全Qt eventや保存成果物の受入を
単独では証明しない。版0.5.0の376件は履歴証拠で、
版0.5.1は全410件、公開66件、Ruff、依存固定、差分形式、sdist/wheel構築、画面外GUI煙試験が成功した。
版0.6.0は全415件、公開71件、Ruff、依存固定、差分形式、sdist/wheel構築、画面外GUI煙試験が成功し、
実装、動的挙動、文書・包装の三系統の独立査読でも未解決欠陥を検出しなかった。
版0.6.1は、編集元を省略した直接入口にも保存済み出力優先を適用し、厳格対応の冷間起動を含む
全417件、公開73件、Ruff、依存固定、差分形式、sdist/wheel構築が成功した。
版0.7.0は、外部由来出力の限定復旧、同一snapshot、非破壊三値化、復旧不能出力からの三preflight
入口INPUT退避、有効ICC用sample展開、IEND終端検査、内容指紋へ束縛した直接fallbackを固定し、
全456件、公開100件、Ruff、依存固定、差分形式、sdist/wheel構築、画面外GUI煙試験が成功した。
版0.7.1は、筆演算、ラベル表示像、ポインタ、格子を変更矩形へ限定し、同色区間の表示更新を省いた。
全477件、公開115件、性能標識1件が成功し、2048×1536の局所A/Bでは格子なしp50が
18.250msから1.466ms、高倍率格子ありp50が32.200msから1.610msへ減少した。この値は
macOS画面外描画の局所証拠であり、Windows実入力の受理値ではない。
版0.8.0は、右button一時メモ、メモ一筆を含む単一Undo・Redo時系列、ラベル編集との複合差分、
保存・画像交換の成功専用破棄を追加した。全520件、公開133件、Ruff、依存固定、差分形式、
sdist/wheel構築、隔離wheel画面外煙試験が成功した。メモ像は初回使用まで遅延確保し、一筆の
既訪問管理は接触画素だけに限定した。Windows実マウス、実DPI遷移、配布候補は未受理である。
後続の局所受入補強では、代表寸法・200件疎履歴、別process競合、隔離wheelの
読込→計画的編集→保存→同一processの新session再開を公開試験・再現scriptへ追加した。これらも
実launcher・物理入力・Windows人間受理を代行しない。補強時点では全529件、公開九試験142件が成功した。
後続の画面有りmacOS観測で低倍率の右単一クリック欠陥を検出・修正し、公開事故回帰を加えた後は
全530件、公開九試験143件が成功した。詳細は
[用途指向試験補強・ローカル検証記録](docs/local-verification-2026-08-20-local-acceptance.md)と
[macOS画面有り利用経路・ローカル検証記録](docs/local-verification-2026-08-21-headed-macos.md)に分離した。
版0.9.0は、メモ生成の有効・無効、記入色、既存メモ非再着色、表示名「設定」とヘルプ直前の入口、
低い画面でも使えるscroll可能な設定頁を追加した。全540件、公開九試験153件、静的検査、依存固定、
sdist/wheel構築、隔離wheel経路、Qt画面外描画が成功した。Windows物理入力、OS色選択部品、DPI、
PyInstaller候補は未受理である。詳細は
[一時メモ設定・設定入口ローカル検証記録](docs/local-verification-2026-08-21-memo-settings.md)に分離した。
同じ版0.9.0の後続修正では、中ボタン／`Space`＋左ボタンのパンがドラッグ中に追従しない欠陥を直し、
全544件、公開九試験157件、静的検査、sdist/wheel構築、隔離wheel経路まで再検査した。詳細は
[パン中再描画・ローカル検証記録](docs/local-verification-2026-08-21-middle-pan-repaint.md)に分離した。
測定器は`scripts/benchmark_brush_responsiveness.py`、同日の原出力は
`docs/brush-responsiveness-benchmark-2026-08-20.json`へ収載した。PowerShellでは次で再実行できる。

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
uv run --locked python .\scripts\benchmark_brush_responsiveness.py
```

`uv build`後のwheelを作業木外へ導入し、同梱`uv.lock`の本番依存をhash付きでoffline cacheから導入して、
読込・編集・保存・出力優先再開まで検査するには次を実行する。これはOS水準の通信遮断試験ではない。

```powershell
uv build
$WheelPath = Resolve-Path .\dist\ternary_image_editor-0.9.0-py3-none-any.whl
$WheelHash = (Get-FileHash -LiteralPath $WheelPath -Algorithm SHA256).Hash.ToLowerInvariant()
uv run --locked python .\scripts\verify_isolated_workflow.py $WheelPath `
  --version 0.9.0 --expected-wheel-sha256 $WheelHash
```

Windows固有事項は
[Windows最終受入チェックリスト](docs/windows-acceptance-checklist.md)で人間が判定する。

## Windows配布候補を構築する

Windows上で、リポジトリ直下から次を実行する。

```powershell
uv --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

構築スクリプトは次を順に行い、いずれかが失敗すれば停止する。

1. 固定lockからPython 3.11環境を同期する。
2. `tests/test_flexible_input_contract.py`、`tests/test_display_comparison_contract.py`、
   `tests/test_brush_responsiveness_contract.py`、`tests/test_memo_history.py`、
   `tests/test_transient_memo_layer_contract.py`、`tests/test_real_size_workflow.py`、
   `tests/test_external_process_conflicts.py`、`tests/test_isolated_distribution_workflow.py`、
   `tests/test_packaging.py`が通常ファイルとして存在することを検査し、`tests/`配下の試験をpytestで
   実行する。不合格なら非零終了として構築を止める。
3. Ruffによる静的検査を実行する。
4. PyInstallerでone-folder配布候補を生成する。
5. 実行ファイルが既定位置に一つだけあり、非零長でMZ先頭を持つことを検査し、SHA-256を表示する。
   同梱アイコン、v1.5仕様書、柔軟入力・対応付け追補、マウス入力割当追補、表示比較（暗）追補、
   一時メモ層追補は
   配置と固定hashを照合する。

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
| [開発仕様書 v1.5](docs/ternary_image_editor_spec_v1_5.html) | 変更しない基線要求正本 |
| [柔軟入力・対応付け追補](docs/flexible-input-pairing-addendum.md) | version 1.3。対応方式、参照原画像、JPEG三値化、選択ラベル源、外部出力復旧、保存済み出力再開、任意寸法、下端保護を限定上書き |
| [マウス入力割当追補](docs/mouse-input-bindings-addendum.md) | v1.5のマウス割当部分だけを限定上書き |
| [表示比較（暗）追補](docs/display-comparison-addendum.md) | version 1.0。比較（暗）の表示合成、永続設定、39件目の操作だけを限定上書き |
| [一時メモ層追補](docs/transient-memo-layer-addendum.md) | version 1.1。未割当右button、最上段非保存表示、単一履歴、保存・画像交換境界、生成・色設定と設定入口を限定上書き |
| [開発仕様書 v1.1](docs/ternary_image_editor_spec_v1_1.html) | 旧版の履歴。現行判断には用いない |
| [要求追跡表](docs/requirements-traceability.md) | 要求、実装、検証層、未受理事項の対応 |
| [試験戦略](docs/test-strategy.md) | 用途危険、証拠層、追加・削除基準、性能・外部画像資料、保証限界、公開保存面 |
| [設計判断](docs/design-decisions.md) | 仕様未規定の採用判断と差戻し条件 |
| [実装計画](docs/implementation-plan.md) | 作業単位と現在状態 |
| [v1.5ローカル検証記録](docs/local-verification-2026-08-18.md) | 版0.2.0までの局所自動試験と性能観測 |
| [マウス入力割当・ローカル検証記録](docs/local-verification-2026-08-19-pointer-bindings.md) | 版0.3.0の局所証拠 |
| [柔軟入力・対応付けローカル検証記録](docs/local-verification-2026-08-19-flexible-input.md) | 版0.4.0の367試験、静的検査、包装、画面外起動と未完了境界 |
| [参照原画像・編集元優先・界面文ローカル検証記録](docs/local-verification-2026-08-19-reference-source-ui.md) | 版0.5.0の376試験、静的検査、包装、画面外起動と未完了境界 |
| [保存済み出力再開・選択源境界ローカル検証記録](docs/local-verification-2026-08-19-output-resume.md) | 版0.5.1の410試験、公開66試験、静的検査、包装、画面外起動と未完了境界 |
| [表示比較（暗）ローカル検証記録](docs/local-verification-2026-08-19-display-comparison.md) | 版0.6.0の415試験、公開71試験、独立画素・状態・性能probe、包装、画面外起動と未完了境界 |
| [保存済み出力優先入口ローカル検証記録](docs/local-verification-2026-08-19-output-resume-entrypoint.md) | 版0.6.1の417試験、公開73試験、省略入口・厳格冷間起動、包装と未完了境界 |
| [外部出力復旧・preflight退避ローカル検証記録](docs/local-verification-2026-08-20-external-output-recovery.md) | 版0.7.0の456試験、公開100試験、外部出力復旧、三入口退避、内容指紋束縛、包装と未完了境界 |
| [筆追従局所更新・ローカル検証記録](docs/local-verification-2026-08-20-brush-responsiveness.md) | 版0.7.1の477試験、公開115試験、局所更新の画素等価・比較性能、Windows未完了境界 |
| [筆追従A/B原出力](docs/brush-responsiveness-benchmark-2026-08-20.json) | 収載測定器による反復数、暖機除外、p50/p95/最大、環境のJSON記録 |
| [一時メモ層ローカル検証記録](docs/local-verification-2026-08-20-transient-memo.md) | 版0.8.0の一時メモ入力・統一履歴・保存／遷移境界・包装とWindows未完了境界 |
| [用途指向試験補強・ローカル検証記録](docs/local-verification-2026-08-20-local-acceptance.md) | 代表寸法・別process競合・隔離wheel利用経路、版0.8.0性能再観測、未完了の実画面／Windows境界 |
| [macOS画面有り利用経路・ローカル検証記録](docs/local-verification-2026-08-21-headed-macos.md) | source通常窓の出力優先再開、実pointer操作、右単一クリック欠陥の再現・修正、残る物理入力／Windows境界 |
| [一時メモ設定・設定入口ローカル検証記録](docs/local-verification-2026-08-21-memo-settings.md) | 版0.9.0の生成・色設定、設定入口、画面寸法、公開試験・包装とWindows未完了境界 |
| [パン中再描画・ローカル検証記録](docs/local-verification-2026-08-21-middle-pan-repaint.md) | 中ボタン／Space＋左ボタンのドラッグ中追従、三値画像層の表示状態、公開事故回帰とWindows未完了境界 |
| [Windows最終受入チェックリスト](docs/windows-acceptance-checklist.md) | Windows実機の結果を記録し、人間が配布可否を決める表 |

v1.5仕様書のSHA-256は
`ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`、柔軟入力・対応付け追補version 1.3は
`ce148618e7cf049cbfe2fa13e00fc4f3cb17b4726c4bf8e878bd63edcbb6255c`、マウス入力割当追補version 1.0は
`91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba`、表示比較（暗）追補version 1.0は
`26f1ff442548d51f66bdb518a14d10d92e52e48c10daec877a8ab04ad27e3779`、一時メモ層追補version 1.1は
`151cd712ecef775c3a513a3c8bbcf7df13806e34c42aaaffb7c52d3eab9f08f7`。構築スクリプトもこれらの固定値を
照合する。

## 利用条件

現時点では`LICENSE`ファイルを配置していない。再利用条件は未提示であり、ライセンス選定は
別途の判断事項である。
