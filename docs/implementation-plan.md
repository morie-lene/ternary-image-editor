# 実装計画

## 基線

- 応用版: `0.8.0`
- 基線要求正本: `TIE-SPEC-001` version 1.5
- 基線SHA-256: `ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`
- 限定追補: `TIE-ADD-FLEX-001` version 1.3
- 限定追補SHA-256: `ce148618e7cf049cbfe2fa13e00fc4f3cb17b4726c4bf8e878bd63edcbb6255c`
- 限定追補: `TIE-ADD-PTR-001` version 1.0
- 限定追補SHA-256: `91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba`
- 限定追補: `TIE-ADD-DISP-CMP-001` version 1.0
- 限定追補SHA-256: `26f1ff442548d51f66bdb518a14d10d92e52e48c10daec877a8ab04ad27e3779`
- 限定追補: `TIE-ADD-MEMO-001` version 1.0
- 限定追補SHA-256: `2ee72910899b8daf9761bb41ad7312933444831e87da5200b61b358594567fb0`
- 範囲: v1.5の必須事項、`AT-001`〜`AT-079`、`FLEX-AT-001`〜`FLEX-AT-018`、
  `PTR-AT-001`〜`PTR-AT-011`、`DISP-CMP-001`〜`DISP-CMP-008`、
  `MEMO-AT-001`〜`MEMO-AT-010`
- 非目的: v1.5 19節の対象外。ただし柔軟入力・対応付けは`TIE-ADD-FLEX-001`、マウス入力割当は
  `TIE-ADD-PTR-001`、表示比較（暗）は`TIE-ADD-DISP-CMP-001`、一時メモ層は
  `TIE-ADD-MEMO-001`が各限定範囲を上書きし、各追補の非目的に従う

版文字列`0.8.0`は応用metadataであり、過去の局所0.8.0 wheelと現在の未commit修正版sourceを
同一artifactにしない。2026-08-21の実行対象は
`local-verification-2026-08-21-headed-macos.md`に記録した関連源SHA-256で区別する。

v1.1とそのSHA-256は履歴正本であり、現在の実装判断には用いない。WP0〜WP6の番号と成果物は
その履歴から継続した作業包として残し、v1.2〜v1.5で追加した実装を同じ責任範囲へ統合する。

## 本質的な達成状態

人間の目視判断を置換せず、原画像と入力三値画像を不変に保ったまま、誤対応・誤画素・表示像混入を避けて三値編集を検証付き別保存できること。

## 作業包

| ID | 成果物 | 依存 | 検証 |
| --- | --- | --- | --- |
| WP0 | Python 3.11環境、入口、文書骨格 | なし | `uv sync`、import |
| WP1 | 対応付け、画像検査、原子的保存 | WP0 | AT-001〜004、026〜029 |
| WP2 | 表示・編集・境界・成分の純粋演算 | WP0 | AT-005〜023 |
| WP3 | 履歴と編集セッション | WP1、WP2 | 保存点、上限、競合、状態遷移 |
| WP4 | 高DPI対応キャンバス | WP2、WP3 | AT-008〜010、030〜033 |
| WP5 | 操作盤、一覧、非同期処理、確認遷移 | WP1、WP3、WP4 | Qt統合試験 |
| WP6 | 受入対応、Windows配布補助 | WP0〜WP5 | 全ローカル検査、Windows判断門 |
| WP7 | ポインタ入力割当、設定schema 2、追補文書 | WP4〜WP6 | PTR-AT-001〜010の局所検査、PTR-AT-011のWindows判断門 |
| WP8 | 非零同数門、二対応方式、JPEG三値化、任意寸法、動的下端保護、追補文書 | WP1〜WP7 | FLEX-AT-001〜009の局所検査とWindows判断門 |
| WP9 | 参照原画像の受付緩和、既存出力の自動優先、確認・診断文の整理 | WP1、WP5、WP8 | FLEX-AT-010〜011、界面回帰、全局所検査、Windows判断門 |
| WP10 | 選択ラベル源の分離、保存済み出力再開、fallback snapshot、通知・cache寿命、選択源別保存基準 | WP1、WP3、WP5、WP9 | FLEX-AT-012〜016、全局所検査、Windows判断門 |
| WP11 | 比較（暗）の原解像度表示切替、操作台帳、設定永続化、追補・公開試験・包装同期 | WP4〜WP7、WP10 | DISP-CMP-001〜008、公開表示契約試験、全局所検査、Windows判断門 |
| WP12 | 編集元省略入口の保存済み出力優先、厳格冷間起動回帰、版追跡 | WP10、WP11 | FLEX-AT-012〜015、公開入力契約試験、全局所検査、Windows判断門 |
| WP13 | 外部由来出力PNGの限定復旧、同一snapshot検査、preflight入力退避 | WP10、WP12 | FLEX-AT-017〜018、非破壊・保存正規化・通知・回帰試験、Windows判断門 |
| WP14 | 筆演算・ラベル像・ポインタ・格子の変更矩形更新、公開比較性能試験 | WP2、WP4、WP5、WP13 | AT-071〜072、画素等価、局所割当、相対性能門、Windows性能判断門 |
| WP15 | 一時メモ層、右button完全一致優先、単一複合履歴、成功専用破棄、追補・公開試験・包装同期 | WP3、WP4、WP7、WP14 | MEMO-AT-001〜010、動的履歴試験、公開源接続・低倍率一点事故回帰、包装、Windows判断門 |

## 現在状態

| 作業包 | 状態 | 証拠境界 |
| --- | --- | --- |
| WP0 | completed | Python 3.11環境、GUI入口、依存固定 |
| WP1 | completed-local-with-residual | 対応付け・厳格読込・原子的保存の単体/故障注入試験。非協調writerの最終照合後競合は既知残危険 |
| WP2 | completed | 純粋演算試験、独立査読で円筆境界回帰を修正 |
| WP3 | completed | 保存点・未確定筆画・token世代を含むセッション試験 |
| WP4 | completed-local | 座標・DPR閾値・画像外余白の単体/Qt試験。Windows AT-030は未受理 |
| WP5 | completed-local | 主画面の筆、履歴、保存、遷移、解析陳腐化のQt統合試験 |
| WP6 | completed-local | ローカル全検査とsdist/wheel配布補助を完了。Windows構築は成果物の配置・非零長・MZ・一意性・hashを事後検査。Windows実機判断門はpending |
| WP7 | completed-local-with-residual | 既存38操作へ七ポインタtokenを追加し、Canvas限定、固定操作との優先、HOLD解放、schema 2移行を実装。全344試験と `uv run ruff check .` が成功。PTR-AT-002/008/010は自動部分証拠、PTR-AT-011はwindows-pending |
| WP8 | completed-local-with-residual | 実装と`TIE-ADD-FLEX-001`を統合し、全367試験、統合差分全体のRuff、版0.4.0 sdist/wheel、画面外GUI煙試験が成功。個別の`automated-partial`項目とWindows実機判断門はpending |
| WP9 | completed-local-with-residual | 原画像の表示正規化、既存出力の無対話優先、入力JPEG確認の実編集元限定、界面文の整理を実装。全376試験、Ruff、依存固定検査、版0.5.0 sdist/wheel、画面外GUI煙試験が成功。Windows実画面と実データによる受理はpending |
| WP10 | completed-local-with-residual | 選択源境界と回帰試験を版0.5.1へ実装。追補version 1.2の固定hash同期後に全410試験、公開66試験、Ruff、依存固定、差分形式、sdist/wheel、画面外GUI煙試験が成功。Windows実画面と実データによる受理はpending |
| WP11 | completed-local-with-residual | 比較（暗）の描画、常設チェック欄、39件目の操作、schema 2設定、公開契約試験、追補version 1.0、包装を版0.6.0へ統合。全415試験、公開71試験、Ruff、依存固定、差分形式、sdist/wheel、画面外GUI煙試験と三系統の独立査読が成功。Windows実画面と実データによる受理はpending |
| WP12 | completed-local-with-residual | `open_pair`の編集元省略時だけ既存の自動選択規則を適用し、明示INPUT/OUTPUTを維持。厳格名＋JPEG入力＋正常出力の冷間起動、不正出力fallback、出力なしを公開回帰へ追加。全417試験、公開73試験、Ruff、依存固定、差分形式、sdist/wheelが成功。通常GUI経路は修正前から局所成功しており、利用現場のWindows実データによる元報告の単独原因確認はpending |
| WP13 | completed-local-with-residual | 外部由来出力PNGの同一snapshot strict-first限定復旧、非破壊三値化、`OUTPUT`未保存状態、明示保存正規化、復旧不能出力からの三preflight入口INPUT退避、有効ICC用sample展開、IEND終端検査、直接fallbackの内容指紋束縛を版0.7.0へ実装。明示INPUT/OUTPUTの互換境界も維持した。全456試験、公開100試験、Ruff、依存固定、差分形式、sdist/wheel、画面外GUI煙試験が成功。Windows実画面、実外部生成器PNG、実物ICCによる受理はpending |
| WP14 | completed-local-with-residual | 離散筆のmask確保とラベル表示像を線分ROIへ、旧・新ポインタを別更新矩形へ、背景・格子をpaint領域の構成矩形へ限定し、同色区間の表示更新を省略した。独自モードポインタ表示中はOSカーソルを隠す。全477試験、公開115試験、性能標識1試験が成功。収載probeによる2048×1536局所A/Bのp50は格子なし12.45倍、高倍率格子あり20.00倍。Windows実入力対光子時間と人間の追従感受理はpending |
| WP15 | completed-local-with-residual | 一時メモの表示・入力・単一複合履歴、成功専用破棄、遅延表示像・疎一筆追跡、DPI取消、公開契約・包装を版0.8.0へ統合。2026-08-20時点の全520試験・公開133試験成功後、画面有りsource経路で低倍率右一点欠陥を検出し、一点`drawPoint`分岐、実`mouseClick`事故回帰、点・Undo/Redo・保存時破棄・筆重畳消去の再観測を追加した。後続の全530試験・公開九試験143件、静的検査、sdist/wheel構築も成功。Windows実マウス、DPI、焦点喪失、配布候補の受理はpending |

## 変更統制

仕様追加や19節の対象外機能は現基線へ黙って混ぜず、正本と別identityを持つ追補または後続候補へ
分離する。柔軟入力・対応付けは`TIE-ADD-FLEX-001`と`FLEX-AT-*`、マウス入力割当は
`TIE-ADD-PTR-001`と`PTR-AT-*`、表示比較（暗）は`TIE-ADD-DISP-CMP-001`と`DISP-CMP-*`に
分離済みであり、一時メモ層は`TIE-ADD-MEMO-001`と`MEMO-AT-*`へ分離する。必須要求から
逸脱する必要が生じた場合は、影響する受入試験、代替案、残危険を示し、人間判断まで実装を止める。

## 安全性・依存・構成影響

- 新しい認証、認可、秘密情報、network通信、telemetry、外部log出力は追加しない。入力は読取専用、
  書込先は既存の明示保存で指定した出力PNGと協調lockに限る。
- 依存package集合を追加・削除せず、既存のPillow `ImageCms`、NumPy、Qtを使う。
  `pyproject.toml`と`uv.lock`は応用版metadataだけを`0.8.0`へ同期する。0.7.1で採取した
  筆性能JSONは測定時版を変更せず、0.8.0の包装では0.7.1基線証拠として扱う。Windows配布候補では
  同梱された色管理経路と現行版の性能を別途実機確認する。
- 永続設定には列挙型の対応方式と、既定falseの比較（暗）真偽値だけを加える。対応方式の不明・破損値は
  厳格対応へ、比較（暗）の欠損・破損値はfalseへ戻す。自然順の対応表に対する確認結果とJPEG一件ごとの
  変換許可は永続化しない。
- フォルダ変更・再走査・起動時再読込は別`ImageSession`で候補を読込preflightし、成功後だけ
  session・pairs・foldersを一括導入する。preflightと前後移動は不正候補をmodalなしで飛ばし、直接
  指定だけ一回通知する。JPEG取消、全候補失敗、blocking count診断では旧状態を保つ。
- 対応計画は原・入力群の非零同数を維持する。計画成立後に正常な出力を選んだ編集用画像対では未使用
  入力を復号・検査・保存基準にせず、入力を選んだ経路だけ厳格検査する。出力由来または分類不能の
  読込失敗は恒久的な画像対cacheへ入れない。
- 公開包装とWindows構築は新追補の配置と固定hashを検査対象へ追加する。この検査は機能受入や
  Windows実行を代行しない。
- 比較（暗）は既存Qt描画合成だけで実装し、依存を追加しない。既定無効とし、画像側は表示用cacheだけを
  変更する。永続状態はschema 2の既定可能な真偽値として画像内容・履歴・保存経路から分離する。
- 筆局所更新は新しいthread、timer、依存を追加せず、ラベル配列を保存正本のまま保つ。全体変更には
  従来の全画像更新を残し、比較合成は局所像へ不透明度を累積せず毎回同じ原解像度基底から作る。
- 一時メモは現在セッションのメモリ上QImageと疎な前後差分だけに閉じ、PNG、QSettings、回復fileを
  増やさない。メモとラベルは単一履歴へ積むが、未保存判定は従来どおりラベル内容基準から求める。
  保存成功では履歴中のメモ成分まで除き、保存失敗と遷移取消では現在メモと履歴位置を保つ。
  原解像度QImageは初回メモ使用まで確保せず、空になれば解放する。一筆の既訪問管理は全画面maskを
  作らず、実際に触れた画素索引だけを保持する。

## 判断門

1. 実装開始: 要求・計画監査と限定作業範囲が成立。
2. ローカル統合: Python 3.11で試験・静的検査・画面外起動が成功し、受入追跡表に説明のない空欄が無い。
   版0.3.0のポインタ入力統合では344試験と静的検査の成功を記録した。版0.4.0は全367試験、
   統合差分全体のRuff、sdist/wheel、画面外GUI起動を
   `local-verification-2026-08-19-flexible-input.md`へ記録した。版0.5.0は全376試験、Ruff、依存固定検査、
   sdist/wheel、画面外GUI起動を
   `local-verification-2026-08-19-reference-source-ui.md`へ記録した。
   版0.5.1は追補version 1.2の固定hash同期後に全410試験、公開66試験、Ruff、依存固定、差分形式、
   sdist/wheel、画面外GUI煙試験の成功を
   `local-verification-2026-08-19-output-resume.md`へ記録した。
   版0.6.0は表示比較追補version 1.0の固定hash同期後に全415試験、公開71試験、Ruff、依存固定、
   差分形式、sdist/wheel、画面外GUI煙試験、独立画素・状態・性能probe、三系統の独立査読の成功を
   `local-verification-2026-08-19-display-comparison.md`へ記録した。
   版0.6.1は編集元省略入口の出力優先と厳格冷間起動を固定し、全417試験、公開73試験、Ruff、
   依存固定、差分形式、sdist/wheelの成功を
   `local-verification-2026-08-19-output-resume-entrypoint.md`へ記録した。
   版0.7.0は外部由来出力のstrict-first限定復旧、三preflight入口のINPUT退避、ICC sample展開、
   IEND終端検査、直接fallbackの内容指紋束縛、明示source保持を固定し、全456試験、公開100試験、Ruff、依存固定、
   差分形式、sdist/wheel、画面外GUI煙試験の成功を
   `local-verification-2026-08-20-external-output-recovery.md`へ記録した。
   版0.7.1は筆の局所演算・表示更新と公開比較性能門を固定し、全477試験、公開115試験、
   性能標識1試験、代表寸法A/B観測を
   `local-verification-2026-08-20-brush-responsiveness.md`へ記録した。
   版0.8.0は一時メモ層、単一複合履歴、保存・遷移境界、資源・DPI回帰、公開ソース接続契約、
   包装同期について、全520試験、公開133試験、Ruff、依存固定、差分形式、sdist/wheel、隔離wheel
   画面外煙試験の成功を`local-verification-2026-08-20-transient-memo.md`へ記録した。
3. 画面有りsource補助証拠: macOS通常窓の自動pointer入力で、出力優先の別process再開、筆、比較、
   一時メモの限定経路を観測した。低倍率右一点の事故回帰追加後は全530試験、公開九試験143件、
   静的検査、sdist/wheel構築を再確認した。これは配布launcher、物理入力、Windows判断門を代行しない。
4. 最終受理: Windows実機、高DPI、実データ、性能、配布物起動、PTR-AT-011、柔軟入力追補、
   表示比較（暗）追補、一時メモ層追補を人間が確認するまで `pending`。
