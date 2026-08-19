# 設計判断と同一性境界

`notation_profile: entity-reference-notation/v0`

この文書は実装裁量として採った判断を記録する。基線正本
`ternary_image_editor_spec_v1_5.html`を置換せず、`TIE-ADD-FLEX-001`、`TIE-ADD-PTR-001`、
`TIE-ADD-DISP-CMP-001`がそれぞれの限定範囲だけを上書きする。自動監査を最終人間受理へ
昇格させない。

## 同一性模型

| 参照 | 意味 | 同じ物と判定する根拠 | 混同してはならない物 |
| --- | --- | --- | --- |
| 対応候補キー・identity.pair-key | NFC正規化後の群番号と幹名末尾27コードポイント | 大文字小文字を区別した完全一致 | ファイル身元、画像対身元、一覧位置 |
| 対応方式・identity.pairing-mode | `strict_key`または`natural_order` | 設定値の列挙型 | 対応計画、自然順確認、画像対身元 |
| 自然順対応計画・identity.natural-pairing-plan | 一回の走査結果にある原画像・三値画像・出力名の全行 | 入力path集合、整列規則、出力path | 保存済み対応方式、確認済み許可、画像内容の正しさ |
| 画像対・identity.image-pair | 対応検査後に一対一と確定した原画像と三値画像 | セッション内の画像対識別子 | 対応候補キー、再訪時の編集セッション |
| 編集用画像対・identity.editable-pair | 一つの原画像と、実際に選択したINPUTまたはOUTPUTラベル源 | 画像対識別子、選択源、各source snapshot | 対応付け上の原・入力対、未選択入力、出力先だけの身元 |
| 出力snapshot・identity.output-snapshot | fallback許可または保存競合検査の対象となった一時点の出力状態 | 正規化path、存在状態、内容指紋 | 出力pathだけ、画像対全体、将来の出力内容 |
| 編集セッション・identity.edit-session | 一つの画像対を開いてから離れるまで | セッション識別子 | 画像対、画像改訂、現在一覧行 |
| 履歴状態・identity.history-state | Undo・Redo上の一状態 | 単調な状態ID | 基準配列、履歴配列添字、画素内容hash |
| 内容基準・identity.content-baseline | 未保存判定の比較対象 | 読込時は下端正規化前の検証済み配列、正常保存後は保存済み正規化配列 | 履歴上の保存点、現在配列、入力ファイル身元 |
| 画像改訂・identity.image-revision | 同一セッション内の非同期結果順序 | 単調な改訂番号 | 履歴状態、画像対、内容基準 |
| 操作・identity.operation | 主画面命令の永続的同一性 | v1.5操作表の38 IDと表示比較追補の1 ID、全39件 | 表示名、既定キー、現在割当、QAction物体 |
| 表示比較状態・identity.display-comparison-state | 原画像と三値表示の合成方式を選ぶ永続真偽値 | `darken_comparison_enabled` | チェック部品、操作ID、表示用QImage、ラベル配列、保存PNG |
| 入力割当・identity.input-binding | 一つの操作slotへ割り当てる永続的な入力 | 鍵盤PortableTextまたは追補の正規化ポインタtoken | 操作ID、物理event、button番号、HOLD起動状態 |
| 内容指紋・evidence.content-fingerprint | 原画像・入力三値・出力の外部変更証拠 | SHA-256等の内容証拠 | ファイル身元、同じ編集内容、保存許可 |
| 保存ロック対象・identity.output-lock-target | 一つの正式出力名に対する協調排他対象 | 正式出力パスから決定した安定側車lockパス | 出力内容指紋、OS全体の排他、非協調writer |

対応候補キーは同じ画像対である可能性を調べる `candidate_ref` 相当であり、重複・欠落を
解消する前に `ref` として扱わない。内容一致は同じ内容の証拠でしかない。特に内容基準と
履歴状態を分けることで、履歴位置が違っても画素が基準へ戻れば未保存を解除できる。

## v1.5で採用中の判断

| 判断参照 | 状態 | 内容 | 根拠と差戻し条件 |
| --- | --- | --- | --- |
| 100%倍率・decision.scale-100.logical | adopted | 1画像画素を1 Qt論理画素として扱い、機器画素比は格子・筆閾値へ用いる | VIEW-007。Windows AT-030/074で齟齬が出れば差戻す |
| 極小キャンバス・decision.canvas.minimum-size | adopted | 主キャンバス最小寸法を設け、5%倍率と全体表示が両立しない窓寸法を通常操作から排除する | VIEW-002/009の衝突局所化 |
| 離散筆・decision.brush.discrete-dxd-mask | adopted | ポインタ下画素を錨とし、仕様の離散 `D×D` 円・正方形マスクをBresenhamで結んで、予告と編集へ共用する。偶数径の余剰は+x/+y側 | EDIT-008、AT-072。旧連続中心判断を置換 |
| 筆取引・decision.stroke.atomic-cancel | adopted | 押下時の色・径・形状と変更前配列を固定し、正常解放だけを一履歴単位で確定する。Esc、非活性化、捕捉喪失は筆跡全体を復元し、描画中の他命令は実行も予約もしない | EDIT-009/010、AT-071。旧DPI変化時確定判断を置換 |
| 原解像度表示・decision.display.native-first | adopted | 原解像度でラベル、疑似色、原画像を合成した完成像を一度だけ倍率へ拡縮し、overlayを最後に描く | VIEW-005/006。表示像を保存正本にしない |
| 未保存遷移・decision.transition.deferred-discard | adopted | 移動先の読込可否が確定する前に現在編集の破棄を確定しない | 移動先の読込失敗やJPEG取込取消で現在編集だけを失う事故を防ぐ |
| 小領域解析・decision.component.nonblocking | adopted | 有と境界を別集計し、保護行を除外する。解析中も編集・移動を許し、編集セッションと画像改訂が一致する結果だけを反映する | COMP-004/005、§11.2。古い結果は棄却して現状態を再計算 |
| 長処理排他・decision.activity.exclusive-writes | adopted | 保存、塗り潰し、境界生成中は編集・移動・再読込を止め、パン・ズーム等の読取表示は許す | UI-003、§13.3 |
| 一時パン入力・decision.pan.application-key-state | adopted | 現在割り当てた保持キーの押下・解放を応用全体で観測し、焦点またはwindow活性喪失時は一時状態を解除する | VIEW-003、KEY-023、AT-078。Spaceは固定入力ではなく既定割当 |
| 一時パンGUI latch・decision.pan.gui-latch | adopted | キー未割当でもGUIから保持操作へ到達できるよう、checkable QActionを合成hold tokenのON/OFFとして扱う。再切替、焦点・window活性喪失で解除し、keyboardの「押下中だけ」という意味は変えない | §13.5の全キー割当解除、VIEW-003、KEY-023、AT-049/078。GUI操作を瞬間triggerへ潰さない |
| 操作台帳・decision.actions.registry | superseded-by-display-comparison-addendum | v1.5表の38操作を不変IDで登録し、表示名・既定キー・現在割当・QActionを分離する | 基線38 IDは保持する。追補が明示した一操作だけを`decision.display-comparison.operation-registry`で追加する |
| 設定作業値・decision.settings.work-copy | adopted | 適用済み設定、ダイアログ作業値、画像状態を別物として保持し、競合解決後の完全な候補だけを永続化・反映する | SET-003、KEY-008/019 |
| 論理キー表現・decision.keys.portable-native | adopted | 保存・同一性比較はQt PortableText相当、利用者表示はNativeText相当を用い、物理走査符号を永続化しない | KEY-015。日本語入力方式とWindows配列は実機判断門に残す |
| 上書き権限・decision.save.split-authority | adopted | 入力版から既存出力を置換する許可、外部出力変更を上書きする許可、外部入力変更後に読込済みスナップショットを保存する許可を別々に得る | §5.3、SAVE-008/009を一つのforceへ潰さない |
| 協調保存排他・decision.save.cooperative-lock | adopted | 正式出力ごとの安定側車lockを非待機で取得し、取得後のSHA再検査から一時PNG検証、`os.replace`、置換後検査まで保持する。lockファイル自体は削除せず再利用する | SAVE-007/010、AT-070。Windows実プロセス試験で差戻し可 |
| 原子的保存境界・decision.save.replace-boundary | adopted | 同一フォルダ一時PNGを再読込検証後 `os.replace` し、v1.5経路では原画像・入力三値・出力を内容指紋で再検査する | 故障原子性と観測可能な外部変更を守る。柔軟入力追補の選択源別再検査範囲は`decision.flex.save-source-baseline`が限定上書きし、非協調writerのCAS極小窓は残危険へ分離 |
| 画面外geometry回復・decision.window.geometry-recovery | adopted | 保存geometryが現在の画面集合と交差しない場合は主画面を既定画面の可視範囲へ戻す | §15.2のウィンドウ位置・寸法、SET-004。複数モニター変更後の到達不能を避ける |
| アプリケーションアイコン資産・decision.packaging.application-icon | adopted | SVGを編集正本、PNGをQt実行時資産、ICOをWindows exe資産として分離し、`QApplication.setWindowIcon`とPyInstaller `--icon`へ同じ図案族を接続する | クリック起動、ウィンドウ、タスクバー、Explorerの視覚同一性を保つ。PNG同梱hashとWindows実表示に齟齬があれば差戻す |

## 柔軟入力・対応付け追補で採用する判断

この節は `TIE-ADD-FLEX-001` に属する。v1.5本文へ遡及して書き換えた判断ではない。

| 判断参照 | 状態 | 内容 | 根拠と差戻し条件 |
| --- | --- | --- | --- |
| 追補優先境界・decision.flex.addendum-precedence | adopted | 対応付け、候補数、参照原画像、三値JPEG、編集元優先、固定寸法、下端保護だけを追補で上書きし、v1.5 HTMLとhashを保持する | 要求身元と変更履歴を保つ。列挙外のv1.5契約と衝突したら公開を止める |
| 候補数門・decision.flex.equal-nonzero-counts | adopted | 対応拡張子を持つ直下通常ファイルを名前・内容検査前に数え、両群が非零同数でなければ0組とする | 余剰を黙って捨てた不完全な編集集合を作らない。対応外拡張子は理由表示に分離する |
| 対応方式既定・decision.flex.strict-default | adopted | 厳格キーを既定とし、自然順は明示選択だけで使い、自動fallbackしない | 名前規約が持つ同一性証拠と、一覧位置による作業仮説を混同しない |
| 自然順確認・decision.flex.natural-plan-confirm-every-time | adopted | 原・三値を別々にNFKC自然順整列し、全行を表示して毎回確認する。確認は対応方式設定へ格上げせず、取消時は現在状態を保つ | フォルダ内容が変われば同じ方式でも対応計画は変わる。Windows同名出力衝突は全計画を拒否する |
| JPEG三値化・decision.flex.jpeg-nearest-save-rgb | adopted | ICC後sRGBで`SAVE_RGB`とのRGB二乗距離最小へ割り当て、同距離は小ラベルを採る。dither・自動閾値を使わない | 再現可能な変換とする。圧縮前ラベルの復元保証はせず、警告取消を既定にする |
| JPEG保存境界・decision.flex.jpeg-explicit-png-save | adopted | JPEG入力を不変に保ち、取込直後を未保存とし、明示保存だけで検証済みRGB PNGを出力する | 取込許可と入力書換権限を混同しない。入力hash変化があれば差戻す |
| 原画像参照境界・decision.flex.original-display-normalization | adopted | 対応拡張子の原画像は復号可能性だけを門とし、Orientation反映、ICCのbest-effort sRGB化、通常RGB退避をメモリ上で行う | 参照画像へ三値画像の厳格色契約を誤適用しない。入力書換えまたは寸法の暗黙変形があれば差戻す |
| 選択ラベル源境界・decision.flex.selected-label-source-boundary | adopted | 対応付けは原・入力の非零同数を維持し、編集用画像対は原画像と選択したINPUTまたはOUTPUTだけで作る。正常なOUTPUTを自動優先し、未選択入力は復号・検査しない | 対応付けの候補根拠と実編集データを混同しない。OUTPUT再開が未使用入力の内容に依存したら差戻す |
| 選択源寸法・decision.flex.selected-label-orientation-size | adopted | 原画像のEXIF表示方向反映後寸法と選択ラベル源を幅・高さ完全一致で照合する。ラベルPNGはOrientationなし／1だけを許し、2〜8を拒否する | ラベルを暗黙転置せず、表示・編集・保存の画素座標を一意にする。未選択入力の寸法検査または暗黙resizeがあれば差戻す |
| fallback snapshot・decision.flex.output-fallback-snapshot | adopted | 不正出力からINPUTへ切り替える許可を出力snapshotに結び付け、同じsnapshotでは再確認せず、変更時だけ再検査する | 許可を永続path権限へ格上げせず、同一内容への反復確認も避ける。変更後に旧許可を流用したら差戻す |
| 読込失敗範囲・decision.flex.open-error-scope | adopted | preflightと前後移動は不正候補をmodalなしで飛ばし、直接指定だけ一回通知する。出力由来・分類不能の失敗は恒久的な画像対cacheへ入れない | 一件の一時的出力失敗で画像対全体を失わず、探索中のmodal連打を避ける。再試行不能または重複通知があれば差戻す |
| 保存源基準・decision.flex.save-source-baseline | adopted | 保存前は原画像、選択ラベル源、出力先snapshotだけを再検査する。OUTPUT再開では未使用入力を基準にせず、INPUT開始では入力の厳格基準を保つ | 未使用入力の変更・破損で保存済み作業を閉じ込めない。入力源開始の変更検出または出力競合検査を失ったら差戻す |
| 下端保護・decision.flex.protected-bottom-by-height | adopted | `H>100`は末尾100行、`H<=100`は保護なしとし、読込・編集・解析・保存で同じ算出規則を使う | 小画像全域を編集不能にせず、通常画像では従来の末尾100行を保つ。`H=100/101`境界の不一致があれば差戻す |

## マウス入力割当追補で採用する判断

この節は `TIE-ADD-PTR-001` に属する。v1.5本文へ遡及して書き換えた判断ではない。

| 判断参照 | 状態 | 内容 | 根拠と差戻し条件 |
| --- | --- | --- | --- |
| 追補優先境界・decision.pointer.addendum-precedence | adopted | KEY-001、固定入力、AT-078、対象外一覧のマウス割当部分だけを追補で上書きし、v1.5 HTMLとhashを保持する | 要求身元と変更履歴を保存する。ほかのv1.5契約との衝突を発見したら公開を止める |
| 操作同一性維持・decision.pointer.shared-operation-registry | adopted | マウス入力割当自体はv1.5の38操作を増やさず、その主・副割当と競合規則へポインタtokenを加える | 入力方式を操作そのものへ昇格させない。後続の39件目は表示比較追補に属し、ポインタ追補の要求または証拠へ遡及混入させない |
| ポインタ表現・decision.pointer.canonical-token | adopted | 七基底tokenへCtrl/Alt/Shiftだけを許し、この順の文字列表現で保存・比較する | 機器button番号や表示名を永続identityにしない。Windows実eventに齟齬があればmappingを差戻す |
| Canvas入力境界・decision.pointer.canvas-scope | adopted | ポインタ割当は主画像Canvas上だけで発火し、設定画面と一般UIを奪わない | 応用全体やOS全域の捕捉は権限・誤操作範囲を不必要に広げる |
| 固定操作との優先・decision.pointer.exact-override | adopted | 一時パン中の左button、割当済み完全一致、未割当固定操作の順を明示し、割当操作が無効でもfallbackしない | 同じ物理入力から意図しない別操作が発火するのを避ける。固定操作を失う割当前には確認する |
| HOLD解放・decision.pointer.latched-release | adopted | 押下時tokenを物理buttonへlatchし、解放時修飾状態に依存せず解除する。非活性化・焦点・捕捉喪失・設定適用では全解除する | stuck状態を避ける。modalを含むWindows event経路に齟齬があれば公開判断を保留する |
| 描画所有権・decision.pointer.stroke-ownership | adopted | 描画中は完成・取消だけを許し、ほかのポインタ入力を発火も予約もせず消費する | `decision.stroke.atomic-cancel`をポインタ割当より優先し、一筆を一取引として保つ |
| 設定移行・decision.pointer.settings-schema-v2 | adopted | 既存pathを維持してschema 2へ上げ、schema 0/1の鍵盤割当を無警告で保持する。破損欄は低優先で既定復元し、別欄の正常な明示割当と競合する時は未割当にして正常値を保つ | 追補追加や破損一欄を、既存設定または別欄の正常値を失う理由にしない。実設定移行失敗なら差戻す |

## 表示比較（暗）追補で採用する判断

この節は `TIE-ADD-DISP-CMP-001` に属する。v1.5本文へ遡及して書き換えた判断ではない。

| 判断参照 | 状態 | 内容 | 根拠と差戻し条件 |
| --- | --- | --- | --- |
| 追補優先境界・decision.display-comparison.addendum-precedence | adopted | 表示合成、表示設定、操作件数だけを追補で上書きし、v1.5 HTMLと既存二追補のhashを保持する | 要求身元を保つ。列挙外の入力・編集・保存契約へ作用したら差戻す |
| 原解像度比較暗・decision.display-comparison.native-darken | adopted | 両層表示時だけ原解像度の各RGB成分へQtのDarken合成を適用し、完成像を一度だけ拡縮する | `decision.display.native-first`を維持する。中間不透明度は8-bit量子化誤差2以内、端点は完全一致。Windows描画器で超えたら差戻す |
| 既定表示維持・decision.display-comparison.default-off | adopted | 既定無効とし、無効時は保存色のLighten、疑似色のSourceOverを維持する | 既存利用者の表示を黙って変えない。ON→OFFで初回OFF画素へ戻らなければ差戻す |
| 表示専用状態・decision.display-comparison.view-only | adopted | 状態変更は表示用cache、チェック状態、QSettingsだけへ通し、ラベル、履歴、未保存判定、保存PNGへ通さない | 表示と画像内容を分離する。切替でsession改訂または保存内容が変われば差戻す |
| 操作台帳追加・decision.display-comparison.operation-registry | adopted | `view.toggle-darken-comparison`を既定割当なしの39件目として既存Action Registryへ加える | 台帳外QActionを作らず一操作一表示面を保つ。別の操作増加は新要求なしに行わない |
| 設定schema据置・decision.display-comparison.settings-v2 | adopted | `view/darkenComparison`を既定falseの加算真偽値としてschema 2へ保存する | 欠損・破損をfalseへ退避できるためschemaを上げない。旧設定読込を壊したら差戻す |

## 置換済み判断

履歴を消すと、旧試験や説明がなぜ無効になったか判らなくなるため、置換済みとして残す。

| 判断参照 | 状態 | 旧内容 | 置換先 |
| --- | --- | --- | --- |
| 偶数径筆・decision.brush.continuous-center | superseded-by-v1.5 | 連続画像座標と画素中心距離または半開矩形で筆領域を決める | `decision.brush.discrete-dxd-mask`。EDIT-008が離散 `D×D` マスクを規範化した |
| 筆取引・decision.stroke.fixed-controls | superseded-by-v1.5 | DPI変化等で閾値未達になった地点までの筆跡を確定する | `decision.stroke.atomic-cancel`。EDIT-010が非活性化・捕捉喪失時の全取消を規範化した |
| 下端保護・decision.labels.protected-bottom | superseded-by-flex-addendum | 固定寸法の下端100行を0へ正規化し、全変更算法で対象外化し、保存用複製でも再正規化する | `decision.flex.protected-bottom-by-height`が任意寸法の境界へ置換 |
| 編集元優先・decision.flex.existing-output-precedence | superseded-by-flex-v1.2 | 正常な既存出力を無対話で優先するが、未選択入力の形式・寸法・内容指紋も検査する | `decision.flex.selected-label-source-boundary`と`decision.flex.output-fallback-snapshot`が選択源と許可寿命を分離 |
| 寸法境界・decision.flex.pair-relative-size | superseded-by-flex-v1.2 | 固定寸法を撤廃し、原・入力同寸と、既存出力もその対と同寸であることを常に要求する | `decision.flex.selected-label-orientation-size`が原画像と選択ラベル源だけの寸法・Orientation契約へ置換 |

## 残危険

| 危険参照 | 現在の抑止 | 未保証 | 判断門 |
| --- | --- | --- | --- |
| 非協調保存窓・risk.save.noncooperative-writer-cas-window | 本アプリおよび同じ側車lock規約に従う協調writerは検査から置換まで排他。非協調変更もSHA再検査と置換後検査で多くを検出する | lockに従わない別アプリが最後の出力照合と `os.replace` 呼出しの間だけで更新した場合の内容条件付き置換 | 同一出力への非協調同時書込を運用禁止するか、Windows固有の条件付き置換相当を追加するかを人間が決める |
| Windowsロック意味差・risk.save.windows-lock-semantics | POSIX開発環境で非待機排他・安定inode・失敗時不変を自動検証 | Windows 10/11での実プロセス間 `msvcrt` lock、強制終了後回復、共有フォルダ差 | Windows AT-070を実施 |
| IME・配列差・risk.keys.windows-ime-layout | PortableText正規化とNativeText変換を局所検証 | 日本語入力方式ON/OFF、JIS/US配列、予約キーのWindows実挙動 | Windows AT-050を実施 |
| 小寸法アイコン・risk.packaging.small-icon-optics | 1024px編集正本から16/32/48/64/128/256pxをICOへ収載し、64px以上の図柄同一性を局所確認 | 16/32pxで観察窓、境界画素、正方形筆頭の全意味を同時に識別できること | WindowsのExplorer、タスクバー、ウィンドウで実表示し、必要なら小寸法光学別稿を作る |
| Windowsポインタevent差・risk.pointer.windows-event-semantics | token正規化、Canvas限定、button解放・応用非活性化・設定適用によるHOLD解除を局所自動検証。FocusOut・UngrabMouseは実装証拠まで | Back/Forwardの機器差、precision touchpadの分割・inertia、modal中release、schema 0/1実設定保持 | Windows PTR-AT-011を実施し、未解放または過剰起動があれば配布を止める |
| 自然順誤対応・risk.flex.natural-order-mispair | 全対応表を導入前に毎回表示し、取消を既定とする | 同じ位置に並んだ画像内容が正しい対であることは自動証明しない | 実データ全行を人間が照合し、不明な行があれば自然順を受理しない |
| JPEG情報喪失・risk.flex.jpeg-label-recovery | 変換式を固定し、JPEG一件ごとに不可逆変換を警告し、入力を不変に保つ | JPEG圧縮前のラベルと最近傍三値化後のラベルが一致すること | 変換後を原画像と目視比較し、必要なら編集してから明示保存する |
| 任意寸法資源量・risk.flex.unbounded-positive-size | 正寸法と復号器の過大画像防護を維持し、性能例を実測する | 明示的な最大幅・高さを契約しておらず、極大画像の処理時間とメモリを一律保証しない | 対象業務寸法で反復測定し、上限が必要なら別要求として決める |
| ICC変換環境差・risk.flex.icc-runtime | ICC不正を拒否し、変換後sRGBに同じ三値化式を適用する | Windows配布物の色管理ライブラリで各実ICCが同じ業務結果になること | 代表ICC付きJPEGをWindows候補で照合する |

## 保留中の人間判断

| 判断参照 | owner | needed_for | blocking_status | next_action | review_at | evidence_ref |
| --- | --- | --- | --- | --- | --- | --- |
| Windows高DPI受理・decision.windows-hidpi-acceptance | human | 最終公開受理 | local実装にはnonblocking、公開にはblocking | AT-030/074を100/125/150/200%と実モニター移動で実行 | Windows候補構築後・公開判断前 | `windows-acceptance-checklist.md` |
| Windowsキー受理・decision.windows-key-acceptance | human | v1.5操作割当受理 | local実装にはnonblocking、公開にはblocking | AT-050をIME ON/OFF、JIS/US配列で実行 | Windows候補構築後・公開判断前 | `windows-acceptance-checklist.md` |
| Windows性能受理・decision.windows-performance-acceptance | human | 最終公開受理 | local実装にはnonblocking、公開にはblocking | 仕様14.3を対象機で反復測定 | 対象PC確定後・公開判断前 | `local-verification-2026-08-18.md`, 仕様14.3 |
| 配布形式・decision.windows-distribution | human | 配布 | 初期機能にはnonblocking | 機能受理後に署名・installer要否を決める | exe起動受理後 | `windows-acceptance-checklist.md` |
| 非協調writer競合・decision.windows-save-race | human | 外部アプリ併用時の公開受理 | 本アプリ多重起動にはnonblocking、同一出力への非協調同時書込運用にはblocking | 競合注入結果を見て運用禁止または追加補償を選ぶ | 外部アプリ併用運用を認める前 | `requirements-traceability.md`, `windows-acceptance-checklist.md` |
| Windowsアプリケーションアイコン受理・decision.windows-application-icon-acceptance | human | 配布物の視覚受理 | local実装にはnonblocking、配布受理にはblocking | Explorer、タスクバー、主windowを16/32pxと各DPIで確認し、同一図案か、既定アイコンへ戻っていないかを記録 | Windows候補構築後・配布判断前 | `windows-acceptance-checklist.md` |
| Windowsポインタ割当受理・decision.windows-pointer-acceptance | human | マウス入力割当追補の配布受理 | local実装にはnonblocking、追補の配布受理にはblocking | PTR-AT-011の四項目を実機で記録する | Windows候補構築後・配布判断前 | `mouse-input-bindings-addendum.md`, `requirements-traceability.md` |
| Windows柔軟入力受理・decision.windows-flexible-input-acceptance | human | 柔軟入力・対応付け追補の配布受理 | local実装にはnonblocking、追補の配布受理にはblocking | 自然順全表、JPEG警告・ICC、選択源別の入力不変・寸法・Orientation・fallback通知・保存基準、`H=100/101`を実機で記録する | Windows候補構築後・配布判断前 | `flexible-input-pairing-addendum.md`, `windows-acceptance-checklist.md` |
| Windows表示比較受理・decision.windows-display-comparison-acceptance | human | 表示比較（暗）追補の配布受理 | local実装にはnonblocking、追補の配布受理にはblocking | Darken画素、疑似色、片層表示、各DPI、操作割当、再起動復元、保存PNG不変を実機で記録する | Windows候補構築後・配布判断前 | `display-comparison-addendum.md`, `windows-acceptance-checklist.md` |
