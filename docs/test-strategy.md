# 試験戦略

## 1. 目的と位置付け

このリポジトリの試験は、試験件数を増やすためではなく、画像の取違え、入力破壊、編集消失、
保存物への表示層混入、応答退行、配布不能といった用途上の危険を、再現可能な反例として早く
検出するために行う。

試験成功は、記録した入力、環境、経路、観測点について反例を検出しなかったという限定証拠である。
全入力での正しさ、利用者の意図、Windowsでの操作感、配布可否を件数だけから導出しない。

本書は試験の選び方と証拠の読み方を定めるが、新しい規範要求や受理結果は作らない。期待挙動は
[開発仕様書 v1.5](ternary_image_editor_spec_v1_5.html)と各追補が定め、現在の実装・試験・
未受理事項の対応は[要求追跡表](requirements-traceability.md)が示す。実行結果は版別の
ローカル検証記録へ残し、Windows配布候補の最終判断は
[Windows最終受入チェックリスト](windows-acceptance-checklist.md)へ記録した人間が
`accept / reject / hold`のいずれかで行う。

本書自体は、新しい試験結果、実行時保証、機械可読出力、CLI入出力契約を生まない。

したがって、要求、試験、局所証拠、人間受理は別物である。試験が通ったことを理由に要求を書き換えず、
要求と実装が食い違う時は、その不一致を先に扱う。

## 2. 基本原則

1. 試験件数ではなく用途危険から試験経路を選ぶ。一つの危険に複数要求が関わり、一つの要求に
   複数証拠層が必要でもよい。
2. 最も低く決定的な層で算法・状態を絞り、実ファイル、Qt、OS、配布物の境界だけを上位層で足す。
   上位層だけで細かな算法を代用せず、下位層だけで実環境を代用しない。
3. 正常系だけでなく、取消、失敗、再試行、外部変更、境界値、途中状態を別々の観測経路として試す。
4. 各証拠には「何を支えるか」と「何を支えないか」を併記する。未実施を成功へ読み替えない。
5. 局所自動試験、画面有りOS確認、隔離配布物確認、Windows人間受理は相互に代替しない。

## 3. 証拠層と保証限界

| 証拠層 | 主な対象と本リポジトリでの例 | 当該層が支える範囲 | 当該層だけでは支えない範囲 |
| --- | --- | --- | --- |
| 純粋算法・状態 | 配列算法、対応付け、履歴、状態遷移。公開例: [test_memo_history.py](../tests/test_memo_history.py)。非公開開発作業場の例: `tests/test_operations.py`、`tests/test_pairing.py`、`tests/test_history.py` | 与えた値域・境界・遷移について、決定的な入出力、不変条件、可逆性、取引性 | 実復号器、実ファイルシステム、Qt event、描画器、機器入力、配布物 |
| 実ファイル | 一時ディレクトリ上のPNG/JPEG、hash、原子的置換、実archive。公開例: [test_flexible_input_contract.py](../tests/test_flexible_input_contract.py)、[test_external_process_conflicts.py](../tests/test_external_process_conflicts.py)、[test_packaging.py](../tests/test_packaging.py)のarchive構築。非公開開発作業場の例: `tests/test_image_io.py` | 実byte列と現行OS上での復号、入力不変、保存形式、内容指紋、包装内容、別processの協調lock・外部置換 | Windows ACL・長いpath・ウイルス対策ソフト、非協調writerの最終照合後割込み、未知の実データ全般 |
| 画面外Qt（offscreen Qt） | `QT_QPA_PLATFORM=offscreen`でのCanvas、主窓、QSettings、Qt event。公開例: [test_display_comparison_contract.py](../tests/test_display_comparison_contract.py)、[test_brush_responsiveness_contract.py](../tests/test_brush_responsiveness_contract.py)、[test_real_size_workflow.py](../tests/test_real_size_workflow.py)。非公開開発作業場の例: `tests/test_canvas.py`、`tests/test_main_window.py` | 使用したQt版と画面外pluginにおける部品接続、event順、状態同期、画像画素、代表寸法の疎履歴 | 画面有り描画器、window manager、実マウス・touchpad、日本語入力方式、実DPI遷移、入力対光子時間 |
| 画面有りOS（headed OS） | windowを実表示し、実描画器、焦点、cursor、monitor、入力機器を使う確認 | 記録したOS、Qt、画面、DPI、機器、操作経路での可視・対話挙動 | 別OS、別GPU・DPI・機器、未実施経路、配布物を使わなかった場合の配布妥当性 |
| 隔離配布物 | sdist/wheelを作業木外へ導入する[隔離wheel利用経路](../scripts/verify_isolated_workflow.py)と[同script契約試験](../tests/test_isolated_distribution_workflow.py)、またはWindows one-folder候補そのものの起動 | 検査したartifact hash、作業木外import、画面外主窓直接生成、実画像の読込・計画的編集・保存、同一process新sessionでの出力優先再開 | 宣言済みlauncherの実行、物理入力、画面有り描画、Windows固有入力、PyInstaller候補、対象PC性能、利用者受理 |
| Windows人間受理 | 固定した配布候補をWindows 10/11の実機でチェックリストに沿って操作し、結果と判断を記録 | 記録した候補、実機、機器、資料、操作についての`accept / reject / hold`判断 | 全Windows機での一般保証、将来版の受理、自動試験の欠落補完、未記録の主観的推定 |

Markdownリンクは公開取得物へ収載する試験だけに張る。`tests/test_operations.py`等のpathは
非公開開発作業場の証拠名であり、公開cloneから取得できる外部資料として示さない。

層番号を品質順位として扱わない。たとえばWindows起動試験は三値化式の全境界を実行・比較した証拠に
ならず、純粋算法試験はWindowsの右button捕捉や保存lockを観測した証拠にならない。

画面有りOS確認は、OS名と版、Qt版、表示倍率とDPI、monitor構成、入力機器、ソース実行か配布物か、
操作手順、期待、実結果を記録して初めて証拠になる。「手元で見えた」だけの記憶は証拠へ数えない。

## 4. 用途危険から選ぶ代表経路

次表は最小の代表経路であり、全要求の列挙ではない。具体的な要求身元と現在状態は
[要求追跡表](requirements-traceability.md)を参照する。

| 用途危険 | 主な要求群 | 代表する証拠経路 | 最後まで残る判断 |
| --- | --- | --- | --- |
| 原画像と三値画像、入力と既存出力を取り違える | FLEX-AT-001〜003、012〜018、AT-075〜076 | 対応付け算法 → 生成した実画像群と内容指紋 → 画面外Qtの起動・再走査・直接指定 → Windows実データ | 一覧、確認文、fallback理由が業務上誤解されないか |
| 入力を上書きする、保存失敗で編集や既存出力を失う | AT-024〜029、066〜070、FLEX-AT-006、016〜018、MEMO-AT-007〜009 | 実ファイルhashと故障注入 → sessionの取消・再試行状態 → 画面外Qtの保存遷移 → Windows ACL・lock・多重process | 対象運用での保存可否と残る非協調writer窓の受容 |
| 三値画素、下端保護、Undo・Redoが誤る | AT-008〜020、034〜037、065〜068、071〜072、FLEX-AT-009、MEMO-AT-003〜006 | 参照算法・境界値・可逆差分 → 実PNG保存再読込 → 画面外Qtの一操作一履歴 → 画面有り入力 | 実軌跡、取消、履歴順が利用者の作業に耐えるか |
| 疑似色、比較、格子、小領域、一時メモが保存PNGへ混入する | AT-005〜007、021〜023、DISP-CMP-003〜007、MEMO-AT-002、007 | 合成画素・状態不変 → 保存前後byte/hash → 画面外Qtの層切替 → 画面有り視認 | 実描画器での見分けやすさと保存物の業務受理 |
| pointer、筆、メモがDPI・焦点・捕捉喪失でずれる | AT-030〜033、071〜074、078、PTR-AT-*、MEMO-AT-001〜005、010 | 座標・筆跡算法 → 画面外Qt eventと取消 → 画面有りOSの実機器・複数DPI → Windows配布候補 | 位置、太さ、解放、疲労、追従感 |
| メモ設定が失われる、既存メモを変える、設定入口へ到達できない | AT-046〜049、MEMO-AT-011〜012 | 設定模型の往復・破損退避 → Canvas画素・画像状態不変 → Qt menu構造と画面配置 → Windows再起動・実操作 | 色の視認性と入口配置が対象利用者に足りるか |
| 開発作業木では動くが配布物が欠ける、起動しない | 横断包装要求 | 構築scriptの静的契約 → sdist/wheel実構築 → 隔離wheel煙試験 → Windows one-folder構築・起動 | 候補hashを固定した配布可否 |
| 局所更新が正しいが対象PCで遅い | 性能判断門、AT-071〜074 | 画素等価 → 同一process相対退行試験 → 版・環境付き反復測定 → Windows対象PCの入力対光子観測 | p95/p99、tail、操作感、業務目標の受容 |
| パン座標だけ進み表示が追従しない | AT-078、PTR-AT-006 | moveごとの写像差分 → release前の実paint領域 → 中／Space＋左と三値画像層表示状態の四条件 → Windows物理入力 | 入力対光子時間、DPI、描画器、物理button捕捉 |
| 復号器やmetadataの実物差を見落とす | FLEX-AT-005〜010、013、017〜018 | 合成fixtureの形式行列 → 権利確認済み外部画像資料集合 → OS別の実ファイル経路 → Windows実データ | 元ラベル意図を復元したという過大主張をしないこと |

## 5. 試験を追加する基準

次のいずれかが生じた時は、件数ではなく未検出危険を示して試験を追加する。

- 新しい要求身元、入力形式、状態、保存先、操作、配布入口を加える。
- 不具合が既存試験を通過した。再現試験は実際に抜けていた入口、順序、取消、失敗境界へ置く。
- 正常系と失敗系で状態所有者、内容基準、snapshot、履歴、外部作用が分岐する。
- 純粋算法と実ファイル、実ファイルとQt、QtとOS、作業木と配布物の接続に新しい継目ができる。
- 寸法、bit depth、Orientation、alpha、DPI、筆径、履歴上限などに意味の変わる境界がある。
- 性能上の熱点を変更し、画素等価または対象経路の計算量退行を機械検出する必要がある。

試験は、失敗時にどの要求または危険が破れたか判別できる最小範囲へ置く。既に同じ危険を同じ
観測点で覆う試験を、件数を増やす目的だけで複製しない。上位層の試験は高価で揺れやすいため、
下位層で判別できる反例を上位層へ無理に持ち込まない。一方、OSや配布物にしか存在しない危険を
mockだけで閉じない。

### parameterized試験と件数

pytestはparameterの各組合せを別の収集nodeとして数える。したがって、試験件数は独立した要求数、
危険数、算法数、利用者経路数のいずれとも一致しない。

- 同じ不変条件を、有限で意味のある形式・境界値へ反復する時はparameterizeする。
- 条件ごとに準備、期待結果、失敗後状態、証拠層が変わるなら、別試験へ分ける。
- 直積は、各組合せに固有の相互作用仮説がある時だけ使う。単なる全組合せで件数を膨らませない。
- 失敗node名から形式や境界を識別できるIDを付ける。
- 分割、統合、parameter追加で件数が変わっても、収集件数の増減自体を品質向上または退行と
  判定しない。

`520 passed`のような表記が意味するのは、その命令と収集条件で520 nodeが成功したことだけである。
一試験が複数要求を支える場合も、一要求を複数試験が支える場合もある。進捗は件数ではなく、
要求・危険ごとの証拠層と未受理欄で読む。

### 試験を統合・削除する基準

試験は通っているから残し、古いから消す、という扱いにはしない。次をすべて満たす時だけ統合または
削除する。

1. 要求追跡表の当該行から、対応する要求が現行か、`superseded`か、削除済みかを読み取る。
2. その試験だけが持つ入口、失敗注入、境界値、観測点、OS・artifact証拠がないことを確認する。
3. 代替試験が同じ危険と非保証を、同等以上に判別できることを差分で示す。
4. 試験名、要求追跡表、検証記録、包装必須集合などの参照を同時に更新する。
5. 旧版の履歴証拠を消さず、現行受理へ使わない状態を明記する。

実装内部の形だけを固定し、利用者可視契約を支えなくなった試験は、動的契約へ置換できる。ただし
包装の必須入力や事故で得た回帰入口は、単なる重複と決め付けない。

## 6. 静的契約試験と事故回帰の位置

[test_transient_memo_layer_contract.py](../tests/test_transient_memo_layer_contract.py)は
`inspect.getsource`等で入力、描画、履歴、保存、画像交換の重要な接続が源から外れていないかを
検査する。加えて、画面有り観測で見つかった低倍率右単一クリック欠陥については、41.1%の実Canvasへ
右`mouseClick`を送る動的事故回帰を同じ公開包装面へ置く。version 1.1では、生成設定、記入色、
QSettings往復・破損退避、既存画素非再着色、設定入口も動的または構造試験で加える。
[test_packaging.py](../tests/test_packaging.py)の一部はWindows構築scriptの必須入力、
終了符号検査、固定hash、成果物検査の並びを源から確認する。

この種の試験は、公開cloneで接続欠落を安価に検出し、実行できないWindows制御流をfail-closedに
保つため、その検出結果を補助証拠へ加える。しかし、文字列や呼出しが源に存在しても、到達可能性、
event順、画素結果、例外後状態、PowerShell実行、Windows起動は証明しない。refactorで挙動不変でも
壊れ得る。

ゆえに静的契約を単独の動的保証にしない。一時メモなら
[test_memo_history.py](../tests/test_memo_history.py)と非公開開発作業場の
`tests/test_main_window.py`・`tests/test_canvas.py`の動的試験を併用し、包装なら
実archive構築、隔離環境の煙試験、Windows上での構築script実行と候補起動を順に足す。
高倍率でpen幅1へ縮退した点試験が成功しても、低倍率の太いpenによる零長線分を保証しない。
既存試験を通過した不具合の回帰は、実際に抜けていた倍率とpress／release入口へ置く。

### 隔離wheel検証scriptの公開出力契約

[verify_isolated_workflow.py](../scripts/verify_isolated_workflow.py)の機械可読契約は
`ternary-image-editor.isolated-workflow-verification/v1`である。標準出力は`--help`を除き、一行の
UTF-8 JSON object一個だけとする。script自身は標準誤出力へ診断を書かず、子processの標準出力・
標準誤出力は失敗時の`error.details`へ末尾最大4000文字だけ収める。`uv run`等の呼出し側が出す診断は
このscriptの出力契約には含めない。

正常時の欄と型は次のとおりである。

| 欄 | 型・値 |
| --- | --- |
| `schema_version` | string。上記固定値 |
| `status` | string enum `"ok"` |
| `checks` | object。`wheel_metadata`、`installed_origin`、`offscreen_main_window_constructed`、`image_loaded`、`programmatic_edit_applied`、`saved`、`same_process_new_window_session`、`output_priority_resume`を固定keyとするboolean |
| `wheel` | object。`distribution`、`path`、`sha256`、`version`はstring |
| `wheel_sha256` | string。選択wheelのSHA-256で、`wheel.sha256`と同値 |
| `installation` | object。`dependencies`、`dependency_resolution`、`environment`はstring enum、`os_network_sandboxed`と`temporary_environment_removed`はboolean |
| `installed_distributions` | object。正規化distribution名をkey、実導入版stringを値とする |
| `package_version`、`python_version`、`declared_entry_point`、`module_relative_path` | string。Pythonは3.11のpatch版まで記録し、entry pointはmetadata宣言値であってlauncher実行証拠ではない |
| `edit` | object。`x`、`y`、`label`はinteger |
| `display_mode`、`interaction_mode`、`session_restart_mode` | string enum。画面外、計画的操作、同一process新MainWindow・ImageSessionを明示 |
| `launcher_executed` | boolean。現経路は常に`false` |
| `acceptance_boundary` | string enum `"local_offscreen_programmatic_workflow_same_process_not_launcher_windows_or_pyinstaller"` |

失敗時は`schema_version`、string enum `status: "error"`、object `error`を返す。`error`はstringの
`stage`、`code`、`message`、`next_action`と、objectの`details`を必須とする。正常欄を部分成功として
混在させない。終了符号0は全八検査成功または`--help`、1は選択・依存・導入・workflow・内部失敗、
2は引数不正を表す。依存不足を成功や引数不正へ畳まない。

このJSONは一回の再現検査結果であり、永続監査台帳そのものではない。版別検証記録へ取り込む時に
日付・時区、命令、環境、artifact hash、観測結果、未実施、残危険、人間判断待ちを併記する。
`installation`はさらに、同梱`uv.lock`と、そこから書き出したhash付き本番依存資料のSHA-256を
`lock_sha256`、`requirements_sha256`へ持つ。
`dependency_resolution: "exact_versions_and_hashes_offline_uv_cache"`は、依存版と配布hashをlockへ
束縛し、uvの取得をcacheへ限定した印である。子processをOS水準のnetwork sandboxへ入れた印ではない。
後者は`os_network_sandboxed: false`として明記する。
受入証拠として実行する時は`--expected-wheel-sha256`を必ず渡し、同版の別artifactへすり替わった場合を
失敗させる。引数を省略した実行はwheel hashを報告する探索probeに留め、現作業木の構築物証拠と
呼ばない。source snapshotは別に基線commitと作業木manifestで同定する。

## 7. 性能試験

性能は、正しい結果を速く得られるかを扱う。速いが画素や状態が異なる経路を採用しないため、
先に参照経路との画素等価、取消、Undo・Redo、保存不変を固定する。

[test_brush_responsiveness_contract.py](../tests/test_brush_responsiveness_contract.py)の
`performance`標識は、同一process内の局所更新と全画像更新相当を比べる広い相対退行門である。
開発機やOSを跨ぐ絶対性能保証ではなく、画面外Qtの処理時間を入力対光子時間へ読み替えない。

反復測定では、少なくとも次を結果と共に記録する。

- 応用版、commitまたは作業木基線、測定script、artifact hash。
- OS、CPU、記憶量、Python、Qt、描画方式、画面有り／画面外、DPIと表示倍率。
- 画像寸法、筆径、格子・比較状態、反復数、暖機除外、計時区間。
- p50、p95、最大、解放後tail。p99は十分な標本数を採れる時だけ加え、少数標本の最大値を
  p99という別名へ置き換えない。平均値一つだけで判断しない。
- 機械的な閾値と、人間が判断する操作感・疲労・停止後追越しを分ける。

[筆追従A/B原出力](brush-responsiveness-benchmark-2026-08-20.json)は版0.7.1で採取した証拠であり、
0.8.0以降の応用版の現行性能へ付け替えない。測定条件と限界は
[筆追従局所更新・ローカル検証記録](local-verification-2026-08-20-brush-responsiveness.md)にある。
2048×1536での読込2秒、筆反映50ms、長処理3秒、保存3秒、常用記憶1GiB未満という対象用途の
目標は、[Windows最終受入チェックリスト](windows-acceptance-checklist.md)の対象PC判断門で測る。

## 8. 外部画像資料集合（corpus）

公開自動試験は、networkや私的資料集合へ依存せず、試験中に作る小さな合成画像を既定とする。
現時点で、外部画像資料集合を公開試験の必須入力として収載していない。合成fixtureは、色、
bit depth、Orientation、alpha、破損位置、寸法など一条件を明瞭に固定できる。

実カメラ、scanner、画像編集器、ICC profile、PNG encoderの差を調べる時は、外部画像資料集合を
補助証拠へ加えられる。ただし、資料集合の存在を暗黙の要求や非公開の合格門にしない。採用項目には
次をmanifestへ記録する。

- 資料集合IDと版、各fileのSHA-256、形式、寸法、取得元、取得日。
- licenseまたは利用許可、再配布可否、改変可否、個人情報・機密・位置情報の検査結果。
- 対応する要求身元と用途危険、期待する受理・拒否・退避、期待値を決めた根拠。
- 実行命令、応用版、OS・復号器、結果、非保証、保管場所。

manifestに再配布可と機微情報除去済みを記録した小資料だけを公開リポジトリへ置く。顧客・利用者画像、
資格情報、私的path、未浄化logは置かない。再配布できない場合はbinaryを収載せず、許される範囲の
hash、来歴、分類、実行結果だけを記録し、公開cloneで再現可能とは書かない。

外部資料で見つけた不具合は、可能なら権利上公開できる最小合成fixtureへ縮小して回帰試験にする。
外部由来出力の三値化試験は、復号と決定規則の結果を検査するのであって、元のラベル意図を復元した
証拠にはしない。

## 9. 要求から人間判断までの追跡

追跡は次の順で保つ。

1. 基線仕様または追補で、AT-*、FLEX-AT-*、PTR-AT-*、DISP-CMP-*、MEMO-AT-*の要求身元を定める。
2. [要求追跡表](requirements-traceability.md)で、要求から実装面、試験名または手動判断門、
   `implemented / automated-local / automated-partial / windows-pending / superseded`へ結ぶ。
3. 試験はpathとnode ID、証拠層、用途危険を示す。静的検査と動的検査を区別する。
4. 版別検証記録へ、命令、日付、環境、版・基線、artifact hash、結果、未実施、残危険を残す。
5. Windows固有事項は配布候補hashを固定し、チェックリストへ実結果を記入する。
6. 最後に人間が`accept / reject / hold`を記録する。自動試験、監査、件数はこの判断を代行しない。

新しい証拠を残す時は、少なくとも次の項目を一組にする。

| 項目 | 記録内容 |
| --- | --- |
| 文脈 | 要求身元、用途危険、守る利用者価値、対象版・作業木・配布候補 |
| 試験 | path、node IDまたは手順、証拠層、正常／失敗／取消の別 |
| 実行 | 命令、版・基線、日付、OS・依存、fixtureまたはcorpus、artifact hash |
| 現在状態 | 観測した成功・失敗・未実施、推定、`windows-pending`、人間判断待ちを分離 |
| 保証限界 | その証拠が支える主張と、支えない主張 |
| 次行動 | 次の証拠層、Windows門、人間の`accept / reject / hold` |
| 詳細参照 | 原出力、検証記録、fixture/corpus manifest、Windows記録への相対path |

日付には時区を付ける。観測事実、資料からの推定、未決定、時点依存の値を同じ状態語へ潰さない。
時刻まで必要な反復・競合・性能記録はISO 8601の`YYYY-MM-DDThh:mm:ss+09:00`を用い、日単位の
版別記録は`YYYY-MM-DD（Asia/Tokyo）`を用いる。後から拾う最小表面は`文脈`、`現在状態`、`次行動`、
`詳細参照`の四欄であり、詳細な原出力をこの四欄へ埋め込まない。

名前と実体も分ける。`0.9.0`は応用版、JSONの`schema_version`は出力形、wheel SHA-256は一構築物、
`2048×1536`は代表fixture寸法、`docs/`は物理保存面である。これらを要求ID、受理状態、一般知識の
所属へ読み替えない。

例としてMEMO-AT-007は、履歴算法、保存成功・失敗の動的主窓試験、
[一時メモ層の源接続契約](../tests/test_transient_memo_layer_contract.py)、
[0.8.0局所検証記録](local-verification-2026-08-20-transient-memo.md)を経ても、
Windows file lock、ACL、配布候補での失敗維持は`windows-pending`のまま残す。要求身元、試験、
局所証拠、人間判断門をこの順で結ぶことが、最小の追跡連鎖である。

## 10. 0.8.0の履歴証拠

[2026-08-20の一時メモ層ローカル検証記録](local-verification-2026-08-20-transient-memo.md)には、
macOS開発環境と画面外Qtで、全520件、sdist収載対象の公開六試験133件、Ruff、固定lock、
bytecode compile、差分形式、sdist/wheel構築、隔離wheel煙試験が成功したと記録されている。

上記の520件と133件は、同日の記録時点における0.8.0作業木の履歴証拠である。将来も
520件または133件であることを要求せず、同じ版表示を持つ未確定作業木で収集件数が変わっても、
その増減だけを完成度へ換算しない。
また、この記録はWindows実マウス、実DPI、Windows file lock・ACL、PyInstaller one-folder候補、
0.8.0の入力対光子性能を受理していない。

同日後続の[用途指向試験補強・ローカル検証記録](local-verification-2026-08-20-local-acceptance.md)は、
代表寸法、別process競合、隔離wheelの利用経路を追加し、全529件・公開九試験142件を観測した。
これは上記履歴を上書きせず、証拠層を足した別の時点記録である。同記録時点では画面有りmacOS観測を
施錠により完了できなかった。

翌日の[macOS画面有り利用経路・ローカル検証記録](local-verification-2026-08-21-headed-macos.md)は、
source通常窓で出力優先、別process再開、筆、比較、一時メモの限定経路を観測した。既存の緑試験群を
通過した低倍率右単一クリック欠陥を発見し、MEMO-003の動的事故回帰を公開包装面へ追加した。
事故回帰追加後は全530件・公開九試験143件、静的検査、sdist/wheel構築を再確認した。
この後続証拠も物理入力、Windows、PyInstaller候補の受理を閉じない。

## 11. 0.9.0の一時メモ設定証拠

[一時メモ設定・設定入口ローカル検証記録](local-verification-2026-08-21-memo-settings.md)は、生成可否、
記入色、既存メモ非再着色、設定入口、設定頁の高さ、反映・保存失敗時の復元を別の用途危険として検査する。全540件と公開九試験
153件の成功は、物理右button、OS色選択部品、Windows menu・DPI、PyInstaller候補を受理しない。

## 12. 0.9.0のパン中再描画証拠

[パン中再描画・ローカル検証記録](local-verification-2026-08-21-middle-pan-repaint.md)は、表示写像が
動いても指示位置周辺しか再描画されず、三値画像層非表示時には移動中の再描画が消える欠陥を事故として
記録する。公開`test_pan_repaints_the_full_canvas_during_each_drag_move`は、初期表示や解放時の全域更新を
証拠へ混ぜず、各moveの直前に記録を消して解放前の`QRegion`がCanvas全域を含むことを四条件で検査する。
通常の筆・メモ・ポインタ局所更新は別契約として残す。Qt画面外成功はWindows物理入力と体感追従を
受理しない。

## 13. 公開保存面の境界

当面、本書、規範文書、要求追跡表、版別検証記録、原測定値、Windowsチェックリストは、公開GitHub
リポジトリの`docs/`を外部から参照できる版管理面に指定する。[README](../README.md)は入口、
`docs/`はこの応用の要求・判断・証拠を辿る面である。

ただし、このリポジトリを全用途の試験理論集、組織横断知識庫、私的画像保管庫、未整理log置場には
しない。ここへ置くのはternary-image-editorの要求、危険、実行証拠、再現手順に直接結び付く物だけ
とする。一般化した知識や再配布不能な資料集合を別の保存面へ移す場合も、公開可能で安定した参照だけを
本書から結び、存在しない外部知識庫を前提にしない。
