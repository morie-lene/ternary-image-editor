# 設計判断と同一性境界

`notation_profile: entity-reference-notation/v0`

この文書は実装裁量として採った判断を記録する。現行正本
`ternary_image_editor_spec_v1_5.html`を置換せず、自動監査を最終人間受理へ昇格させない。

## 同一性模型

| 参照 | 意味 | 同じ物と判定する根拠 | 混同してはならない物 |
| --- | --- | --- | --- |
| 対応候補キー・identity.pair-key | NFC正規化後の群番号と幹名末尾27コードポイント | 大文字小文字を区別した完全一致 | ファイル身元、画像対身元、一覧位置 |
| 画像対・identity.image-pair | 対応検査後に一対一と確定した原画像と三値画像 | セッション内の画像対識別子 | 対応候補キー、再訪時の編集セッション |
| 編集セッション・identity.edit-session | 一つの画像対を開いてから離れるまで | セッション識別子 | 画像対、画像改訂、現在一覧行 |
| 履歴状態・identity.history-state | Undo・Redo上の一状態 | 単調な状態ID | 基準配列、履歴配列添字、画素内容hash |
| 内容基準・identity.content-baseline | 未保存判定の比較対象 | 読込時は下端正規化前の検証済み配列、正常保存後は保存済み正規化配列 | 履歴上の保存点、現在配列、入力ファイル身元 |
| 画像改訂・identity.image-revision | 同一セッション内の非同期結果順序 | 単調な改訂番号 | 履歴状態、画像対、内容基準 |
| 操作・identity.operation | 主画面命令の永続的同一性 | v1.5操作表の不変操作ID、全38件 | 表示名、既定キー、現在割当、QAction物体 |
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
| 下端保護・decision.labels.protected-bottom | adopted | 全体検証後に下端100行を0へ正規化し、全変更算法で対象外化し、保存用複製でも再正規化する | DAT-004〜007、SAVE-004。読込差分は内容基準との差として未保存にする |
| 未保存遷移・decision.transition.deferred-discard | adopted | 移動先の編集元選択まで確定する前に現在編集の破棄を確定しない | 二段階確認の中止で編集だけ失う事故を防ぐ |
| 小領域解析・decision.component.nonblocking | adopted | 有と境界を別集計し、保護行を除外する。解析中も編集・移動を許し、編集セッションと画像改訂が一致する結果だけを反映する | COMP-004/005、§11.2。古い結果は棄却して現状態を再計算 |
| 長処理排他・decision.activity.exclusive-writes | adopted | 保存、塗り潰し、境界生成中は編集・移動・再読込を止め、パン・ズーム等の読取表示は許す | UI-003、§13.3 |
| 一時パン入力・decision.pan.application-key-state | adopted | 現在割り当てた保持キーの押下・解放を応用全体で観測し、焦点またはwindow活性喪失時は一時状態を解除する | VIEW-003、KEY-023、AT-078。Spaceは固定入力ではなく既定割当 |
| 一時パンGUI latch・decision.pan.gui-latch | adopted | キー未割当でもGUIから保持操作へ到達できるよう、checkable QActionを合成hold tokenのON/OFFとして扱う。再切替、焦点・window活性喪失で解除し、keyboardの「押下中だけ」という意味は変えない | §13.5の全キー割当解除、VIEW-003、KEY-023、AT-049/078。GUI操作を瞬間triggerへ潰さない |
| 操作台帳・decision.actions.registry | adopted | v1.5表の38操作だけを不変IDで登録し、表示名・既定キー・現在割当・QActionを分離する | KEY-001/021。架空の39件目を作らない |
| 設定作業値・decision.settings.work-copy | adopted | 適用済み設定、ダイアログ作業値、画像状態を別物として保持し、競合解決後の完全な候補だけを永続化・反映する | SET-003、KEY-008/019 |
| 論理キー表現・decision.keys.portable-native | adopted | 保存・同一性比較はQt PortableText相当、利用者表示はNativeText相当を用い、物理走査符号を永続化しない | KEY-015。日本語入力方式とWindows配列は実機判断門に残す |
| 上書き権限・decision.save.split-authority | adopted | 入力版から既存出力を置換する許可、外部出力変更を上書きする許可、外部入力変更後に読込済みスナップショットを保存する許可を別々に得る | §5.3、SAVE-008/009を一つのforceへ潰さない |
| 協調保存排他・decision.save.cooperative-lock | adopted | 正式出力ごとの安定側車lockを非待機で取得し、取得後のSHA再検査から一時PNG検証、`os.replace`、置換後検査まで保持する。lockファイル自体は削除せず再利用する | SAVE-007/010、AT-070。Windows実プロセス試験で差戻し可 |
| 原子的保存境界・decision.save.replace-boundary | adopted | 同一フォルダ一時PNGを再読込検証後 `os.replace` し、原画像・入力三値・出力を内容指紋で再検査する | 故障原子性と観測可能な外部変更を守る。非協調writerのCAS極小窓は残危険へ分離 |
| 画面外geometry回復・decision.window.geometry-recovery | adopted | 保存geometryが現在の画面集合と交差しない場合は主画面を既定画面の可視範囲へ戻す | §15.2のウィンドウ位置・寸法、SET-004。複数モニター変更後の到達不能を避ける |
| アプリケーションアイコン資産・decision.packaging.application-icon | adopted | SVGを編集正本、PNGをQt実行時資産、ICOをWindows exe資産として分離し、`QApplication.setWindowIcon`とPyInstaller `--icon`へ同じ図案族を接続する | クリック起動、ウィンドウ、タスクバー、Explorerの視覚同一性を保つ。PNG同梱hashとWindows実表示に齟齬があれば差戻す |

## マウス入力割当追補で採用する判断

この節は `TIE-ADD-PTR-001` に属する。v1.5本文へ遡及して書き換えた判断ではない。

| 判断参照 | 状態 | 内容 | 根拠と差戻し条件 |
| --- | --- | --- | --- |
| 追補優先境界・decision.pointer.addendum-precedence | adopted | KEY-001、固定入力、AT-078、対象外一覧のマウス割当部分だけを追補で上書きし、v1.5 HTMLとhashを保持する | 要求身元と変更履歴を保存する。ほかのv1.5契約との衝突を発見したら公開を止める |
| 操作同一性維持・decision.pointer.shared-operation-registry | adopted | 38操作を増やさず、既存の主・副割当と競合規則へポインタtokenを加える | 入力方式を操作そのものへ昇格させず、架空の39件目を作らない |
| ポインタ表現・decision.pointer.canonical-token | adopted | 七基底tokenへCtrl/Alt/Shiftだけを許し、この順の文字列表現で保存・比較する | 機器button番号や表示名を永続identityにしない。Windows実eventに齟齬があればmappingを差戻す |
| Canvas入力境界・decision.pointer.canvas-scope | adopted | ポインタ割当は主画像Canvas上だけで発火し、設定画面と一般UIを奪わない | 応用全体やOS全域の捕捉は権限・誤操作範囲を不必要に広げる |
| 固定操作との優先・decision.pointer.exact-override | adopted | 一時パン中の左button、割当済み完全一致、未割当固定操作の順を明示し、割当操作が無効でもfallbackしない | 同じ物理入力から意図しない別操作が発火するのを避ける。固定操作を失う割当前には確認する |
| HOLD解放・decision.pointer.latched-release | adopted | 押下時tokenを物理buttonへlatchし、解放時修飾状態に依存せず解除する。非活性化・焦点・捕捉喪失・設定適用では全解除する | stuck状態を避ける。modalを含むWindows event経路に齟齬があれば公開判断を保留する |
| 描画所有権・decision.pointer.stroke-ownership | adopted | 描画中は完成・取消だけを許し、ほかのポインタ入力を発火も予約もせず消費する | `decision.stroke.atomic-cancel`をポインタ割当より優先し、一筆を一取引として保つ |
| 設定移行・decision.pointer.settings-schema-v2 | adopted | 既存pathを維持してschema 2へ上げ、schema 0/1の鍵盤割当を無警告で保持する。破損欄は低優先で既定復元し、別欄の正常な明示割当と競合する時は未割当にして正常値を保つ | 追補追加や破損一欄を、既存設定または別欄の正常値を失う理由にしない。実設定移行失敗なら差戻す |

## 置換済み判断

履歴を消すと、旧試験や説明がなぜ無効になったか判らなくなるため、置換済みとして残す。

| 判断参照 | 状態 | 旧内容 | 置換先 |
| --- | --- | --- | --- |
| 偶数径筆・decision.brush.continuous-center | superseded-by-v1.5 | 連続画像座標と画素中心距離または半開矩形で筆領域を決める | `decision.brush.discrete-dxd-mask`。EDIT-008が離散 `D×D` マスクを規範化した |
| 筆取引・decision.stroke.fixed-controls | superseded-by-v1.5 | DPI変化等で閾値未達になった地点までの筆跡を確定する | `decision.stroke.atomic-cancel`。EDIT-010が非活性化・捕捉喪失時の全取消を規範化した |

## 残危険

| 危険参照 | 現在の抑止 | 未保証 | 判断門 |
| --- | --- | --- | --- |
| 非協調保存窓・risk.save.noncooperative-writer-cas-window | 本アプリおよび同じ側車lock規約に従う協調writerは検査から置換まで排他。非協調変更もSHA再検査と置換後検査で多くを検出する | lockに従わない別アプリが最後の出力照合と `os.replace` 呼出しの間だけで更新した場合の内容条件付き置換 | 同一出力への非協調同時書込を運用禁止するか、Windows固有の条件付き置換相当を追加するかを人間が決める |
| Windowsロック意味差・risk.save.windows-lock-semantics | POSIX開発環境で非待機排他・安定inode・失敗時不変を自動検証 | Windows 10/11での実プロセス間 `msvcrt` lock、強制終了後回復、共有フォルダ差 | Windows AT-070を実施 |
| IME・配列差・risk.keys.windows-ime-layout | PortableText正規化とNativeText変換を局所検証 | 日本語入力方式ON/OFF、JIS/US配列、予約キーのWindows実挙動 | Windows AT-050を実施 |
| 小寸法アイコン・risk.packaging.small-icon-optics | 1024px編集正本から16/32/48/64/128/256pxをICOへ収載し、64px以上の図柄同一性を局所確認 | 16/32pxで観察窓、境界画素、正方形筆頭の全意味を同時に識別できること | WindowsのExplorer、タスクバー、ウィンドウで実表示し、必要なら小寸法光学別稿を作る |
| Windowsポインタevent差・risk.pointer.windows-event-semantics | token正規化、Canvas限定、button解放・応用非活性化・設定適用によるHOLD解除を局所自動検証。FocusOut・UngrabMouseは実装証拠まで | Back/Forwardの機器差、precision touchpadの分割・inertia、modal中release、schema 0/1実設定保持 | Windows PTR-AT-011を実施し、未解放または過剰起動があれば配布を止める |

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
