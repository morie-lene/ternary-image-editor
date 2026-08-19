# マウス入力割当追補

- 文書ID: `TIE-ADD-PTR-001`
- 版: 1.0
- 制定日: 2026-08-19
- 基線仕様: `ternary_image_editor_spec_v1_5.html`
- 基線SHA-256: `ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`
- 初回実装版: `0.3.0`
- 規範状態: 採用済み要求。実装・検証状態は要求追跡表で別管理

## 0. 読者と用途

本追補は実装者と試験者が、マウス入力割当の範囲、優先順位、移行、受入条件を同じ契約で
照合するための規範文書である。利用者向けの短い操作手順はREADMEに置く。本書の
`PTR-*` は実装が満たすべき状態を表し、現在の実行時保証を単独で主張しない。実装と自動
証拠の現在状態は要求追跡表の `PTR-AT-*` を参照する。

## 1. 適用関係

本追補は、開発仕様書 v1.5 のうち、物理マウス入力を操作割当の対象外とした `KEY-001`、
固定入力の注意書き、`AT-078`、および初期版対象外一覧にあるマウス再割当の記述を、
マウス入力割当に限って上書きする。同じ事項で両者が衝突する場合は本追補を優先し、
それ以外は v1.5 を引き続き基線とする。

固定入力のうちEscによる進行中操作の取消は上書きせず、引き続き固定入力とする。

v1.5 のHTMLと上記SHA-256は変更しない。本追補由来の要求と受入条件には `PTR-` 接頭辞を
付け、v1.5 本文の要求IDおよび `AT-001`〜`AT-079`と混同しない。

## 2. 同一性境界

| 対象 | 同一性 | 混同しない物 |
| --- | --- | --- |
| 操作 | v1.5 操作表の不変操作ID、全38件 | 表示名、現在割当、入力token、物理入力event |
| 入力割当 | 正規化した鍵盤またはポインタtoken | 操作ID、機器button番号、実行中のHOLD状態 |
| 物理入力event | 主画像Canvas上で観測した一回の押下・解放・垂直wheel event | 永続設定、操作そのもの |
| HOLD起動token | 押下時の正規化tokenを解放まで保持した物 | 解放時の修飾キー状態、ほかのHOLD起動token |

本追補は新しい操作を追加しない。既存38操作の主・副割当、自己重複拒否、他操作との競合
移動・取消へ、鍵盤入力と同じ割当候補としてポインタtokenを加える。

## 3. ポインタtoken

### PTR-001 受理する基底token

受理する基底tokenは次の七つに限る。

- `WheelUp`
- `WheelDown`
- `MouseLeft`
- `MouseMiddle`
- `MouseRight`
- `MouseBack`
- `MouseForward`

### PTR-002 修飾キーと正規形

`Ctrl`、`Alt`、`Shift`は単独または複数で基底tokenへ付加できる。保存・競合比較では
`Ctrl`、`Alt`、`Shift`、基底tokenの順へ正規化する。例えば
`Shift+Ctrl+MouseBack` は `Ctrl+Shift+MouseBack` と同じ割当である。

設定値の例:

```text
MouseMiddle
Ctrl+WheelUp
Alt+Shift+MouseForward
```

割当照合は修飾キーを含む完全一致とする。`MouseRight` と `Ctrl+MouseRight` は別の入力で
あり、一方を割り当てても他方を奪わない。

### PTR-003 拒否する入力

次は割当候補として受理しない。

- `Meta` または Windows キーを含む入力
- 修飾キー以外の鍵盤キーとマウスを同時に用いるchord
- 複数マウスbuttonの同時押下を一tokenとする入力
- double-click専用token、drag方向、水平wheel、macro
- 応用外やOS全域で作動するglobal入力

## 4. 設定画面での割当

### PTR-004 捕捉

設定画面の主・副割当欄は、鍵盤chordに加えて、マウスbutton押下または非零の垂直wheel
event一件を一候補として捕捉する。double-clickは専用tokenへせず、設定捕捉では一候補と
して確定する。捕捉中の入力は設定画面の通常操作へ流さない。

### PTR-005 固定操作を失う確認

`MouseLeft`系、`MouseMiddle`系、`WheelUp`系、`WheelDown`系を割り当てる前に、該当する
修飾キー完全一致の入力について、次の固定操作が置換されることを明示し、続行または取消を
選ばせる。

- 左button: 筆または塗り潰し
- 中button: dragによる自由移動
- wheel上・下: ポインタ直下を基準とする一段拡大・縮小

### PTR-006 操作型による制約

- `SINGLE`: button押下または垂直wheel event一件につき一回だけ実行する。
- `STEP`: button押下または垂直wheel event一件につき一段だけ実行する。
- `HOLD`: button押下で開始し、その物理buttonの解放で終了する。
- `WheelUp`系と `WheelDown`系は解放eventを持たないため、`HOLD`操作へ割り当てない。
- `MouseLeft`系は `view.temporary-pan` へ割り当てない。
- `MouseMiddle`、`MouseRight`、`MouseBack`、`MouseForward`系は `HOLD`へ割当可能とする。

制約違反は割当を変更せず、理由を設定画面へ示す。

## 5. 作動範囲と優先順位

### PTR-007 主画像Canvas限定

ポインタ割当は主画像Canvas上の入力だけに作動する。設定画面、一覧、数値欄、button、menu
など一般UIのclickやwheelを操作割当が奪ってはならない。OS全域の入力は観測しない。

### PTR-008 優先順位

主画像Canvas上では次の順に一件だけを適用する。

1. 筆描画が進行中なら、その操作が左buttonの移動・解放またはEscによって
   完成・取消されるまで、ほかのポインタ入力を消費する。ほかの割当操作は発火も予約も
   しない。
2. Spaceによる一時パン、またはGUIの一時パン切替が既に有効なら、左buttonはパンを
   優先する。`MouseLeft`系の割当は発火しない。
3. 修飾キーを含めて完全一致するポインタtokenが割当済みなら、対応操作へ渡して入力を
   消費する。対応操作がその時点で無効でも、固定操作へfallbackしない。
4. 完全一致する割当がなければ、v1.5 の固定操作を保つ。wheel上下は拡大・縮小、中button
   dragは自由移動、左buttonは現在の道具、Space+左buttonは一時パンとして働く。

未割当の右・戻る・進むbuttonには、本追補による固定操作を加えない。

## 6. event回数とHOLD解放

### PTR-009 event単位

実行中のdouble-clickは、同じ基底tokenの独立した物理押下event二件としてdispatchし、
`SINGLE`または `STEP`を二回起動する。垂直wheelは非零event一件ごとに一回起動する。
零の垂直成分および水平wheelだけのeventは割当入力として扱わない。

### PTR-010 HOLD解放

`HOLD`は押下時の完全なtokenと物理buttonを結び付ける。修飾キーを先に離しても、button
解放時には押下時tokenを解放する。同じ操作が複数tokenから保持されている場合は、最後の
tokenが解放されるまで操作状態を保つ。

window非活性化、焦点喪失、マウス捕捉喪失、設定適用時には、残っている全HOLD tokenを
解除する。この処理は重複して呼ばれても安全でなければならない。

## 7. 永続化と移行

### PTR-011 設定schema 2

設定schemaを `2` とし、既存のQSettings組織名・応用名・保存pathを維持する。schema `0`
または `1` の鍵盤割当は警告なしに読み込み、割当内容を保持したschema `2` の作業値へ
移行する。次の正常保存でschema `2`を書き込む。QSettingsは利用者単位の内部永続化に限り、
応用外への公開入出力形式にはしない。

割当pathは次の条件で読む。

- pathがない: 同じ `operation_id` と主・副slotの既定値を用いる。
- pathがあり値が空文字列: 同じslotを未割当値 `None` とする。
- pathがあり値が破損または未受理: 同じslotだけを既定値へ戻して警告する。

欠落または破損slotの既定値が、別slotの正常な明示割当と競合する場合は、正常な明示割当を
優先する。低優先の既定復元側を未割当にして警告し、正常値を既定値で押し退けてはならない。

いずれも、条件に該当しない設定と割当は保持する。保存時はschema `2`と正規化済みtokenを
書き込む。設定適用で割当集合を交換する前に、旧集合で起動中のHOLDを全解除する。

## 8. 非目的

本追補は、global shortcut、複数button chord、double-click専用命令、drag gesture、水平
wheel、macro、機器固有button番号の任意登録を追加しない。これらは実装から偶然利用できても
契約済み機能として扱わない。

既存Qt入力eventの局所処理だけを用いる。応用外連携、常駐監視、追加telemetry、新規依存
package、OS設定変更は本追補の実装範囲に含めない。

## 9. 受入証拠とWindows判断門

追補の受入項目は [要求追跡表](requirements-traceability.md) の `PTR-AT-001` 以降に分離する。
`implemented` または `automated-local` は、実装統合と局所自動試験の証拠を確認してから付す。
公開取得物には試験コードを含めないため、`automated-local` は公開clone単独で再現できるという
意味ではない。

状態を更新する時は、証拠の取得日時と時区、対象platform、commitまたは作業木、実行した
試験、結果を記録する。推測は試験結果へ混ぜず、未確認なら `planned` または
`windows-pending` のままにする。

次は重大な未検証事項として `windows-pending` に残す。

- Windows上の実マウスによるBack・Forward buttonの識別と押下・解放
- precision touchpadのwheel分割、連続event、inertiaによる起動回数
- modal画面が開いた間にbuttonを解放した場合のHOLD解除
- schema `0` / `1` からの実利用設定保持とschema `2`への移行

これらはWindows実機で記録し、人間が配布受理を判断するまで受理済みとしない。
