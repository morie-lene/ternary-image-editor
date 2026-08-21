# パン中再描画・ローカル検証記録

## 記録範囲

- 日付: 2026-08-21（Asia/Tokyo）
- アプリケーション版: `0.9.0`
- 直前基線: Git `9789fc0b488be94cdfd441210a5e5f9da8c10dff`（版0.8.0）
- 対象: `AT-078`、`PTR-AT-006`
- 環境: macOS開発環境、Python 3.11.15、PySide6 / Qt 6.11.1、`QT_QPA_PLATFORM=offscreen`
- 受理境界: Windows 10 / 11、物理マウス、実モニター、PyInstaller配布候補の人間受理ではない

この記録は、中ボタンまたは`Space`保持中の左ボタンで画像を移動した時、表示写像の座標だけ進み、
実表示がドラッグへ追従しない欠陥と、その局所修正を検証した証拠である。メモ設定の同日記録を
上書きせず、Windows判断門も閉じない。

## 欠陥と原因

修正前の320×240 Canvas、512×512画像、原寸表示では、中ボタンを`(100,100)`から`(160,140)`へ
移動すると表示原点自体は`(+60,+40)`進んだ。一方、三値画像層表示時のmove paintは指示位置周辺の
`9×9`だけ、三値画像層非表示時はmove paintがなかった。解放時だけ320×240全域が再描画されるため、
ドラッグ中の局所欠損または無追従と、解放時の跳びが同じ原因から生じていた。

`ImageCanvas.mouseMoveEvent`のパン分岐は、表示原点を変更した後に指示位置の旧・新矩形だけを更新して
いた。パンは原画像、三値画像、格子、上描きの写像を一括して変えるため、通常のポインタ局所更新を
流用できない。

## 修正境界

- `_panning`中の各moveで、原点更新と指示位置更新の後にCanvas全表示域の`update()`を要求する。
- 中ボタンと一時パン中の左ボタンは同じ分岐を通るため、同じ修正を共有する。
- 解放時の既存全域更新は、移動eventを伴わない押下・解放と最終差分の安全網として維持する。
- 通常の筆、メモ、単なるポインタ移動は従来どおり局所矩形だけを更新する。画像内容、履歴、保存PNG、
  入力割当の優先順位、cache identityは変更しない。

## 動的事故回帰

公開`tests/test_brush_responsiveness_contract.py::test_pan_repaints_the_full_canvas_during_each_drag_move`は、
次の四条件を引数化して検査する。

| パン開始 | 三値画像層 | move中の契約 |
| --- | --- | --- |
| 中ボタン | 表示 | 各move後、解放前に実paint領域がCanvas全域を含む |
| 中ボタン | 非表示 | 同上 |
| `Space`保持＋左ボタン | 表示 | 同上 |
| `Space`保持＋左ボタン | 非表示 | 同上 |

各条件で、初期表示と押下後のpaint記録を捨て、二回のmoveごとにQt eventを配送してから`QRegion`を
検査する。従って、修正前から存在した解放時の全域更新だけで試験が通ることはない。二回の合計移動量
`(+60,+40)`、解放後の`_panning == False`と最終位置消去も同時に確認する。

独立probeでは、320×240 Canvas、512×512画像、原寸表示の四条件すべてで、三回のmoveごとに
320×240全域のpaintを観測した。原点は`(-96,-136)`から、移動列`(120,110) → (160,140) →
(130,170)`に従って`(-76,-126) → (-36,-96) → (-66,-66)`となり、解放後も最終原点を維持した。

## 自動検査

最終作業木で次を実行した。

```text
QT_QPA_PLATFORM=offscreen uv run --python 3.11 pytest -q
QT_QPA_PLATFORM=offscreen uv run --python 3.11 pytest -q $(git ls-files 'tests/test_*.py')
uv run --python 3.11 ruff check .
uv lock --check
uv run --python 3.11 python -m compileall -q src
git diff --check
uv build --out-dir <一時directory>
uv run --locked python scripts/verify_isolated_workflow.py <wheel> \
  --version 0.9.0 --expected-wheel-sha256 <wheel-sha256>
```

結果は次のとおりである。

- 対象事故回帰と既存pan回帰: `6 passed in 0.28s`
- 全試験: `544 passed in 8.19s`
- Git追跡済み公開九試験: `157 passed in 2.36s`
- Ruff、固定lock、bytecode compile、差分形式: 成功
- 版0.9.0 sdist / wheel構築: 成功
- 隔離wheel経路: 八検査すべて`true`、`status: ok`
- `uv.lock` SHA-256: `2ac442a289a37806a2ec0ce0ab6747834d7aa6172ff795a5dda70a2a56666306`
- Git追跡済み作業差分SHA-256: `493530c3e379ba85e819420a7c77e10d43b4c5690bee34bbc7ed9fb891af8838`
- 検査済みwheel SHA-256: `5476f79d3c04dd9c38193e1e8212969a0203a62d1f90390262d6cebc02e84118`
- 同時構築sdist SHA-256: `44c8826ff3d61c7e5365c390f2af4891d03783b030ef25103dc9e706dbb472e4`

wheelとsdistは、最終語彙修正後、この記録へ上記hashを追記する直前に一時directoryで再構築した
離脱物である。従ってsdist hashは当該離脱物を識別するが、自己参照となる追記後の資料集合を
再構築したhashとは主張しない。
Git追跡済み作業差分は`git diff --binary | shasum -a 256`で算出した。この記録と同日のメモ設定記録は
未追跡であり、追跡差分identityに含めていない。統合時には両資料を明示的に収載する。

## 構成・安全性

- このパン修正は依存package、Python版範囲、Qt版範囲、lock内容、CI命令を変更しない。
  `pyproject.toml`の対象差分は本検証記録をsdist収載対象へ加える一行だけである。
- `uv lock --check`、固定lockのSHA-256、隔離wheel導入で、依存と実行環境の不意な変更がないことを
  再検査した。
- 新しい画像入力、画像出力、永続設定、network通信、認証、認可、秘密情報、clipboard、telemetry、
  外部logを追加しない。表示原点、画像内容、履歴、保存PNG、既存cache identityも変更しない。
- 追加する実行分岐は、既存`_panning` move中の全表示域更新一件だけである。新しいthread、timer、
  権限、外部状態、失敗復旧経路を持たない。

## 残リスク・未完了境界

残リスクあり。次はこの局所検証では受理していない。

- Windows 10 / 11上の物理中ボタン、`Space`＋左ボタン、マウス捕捉。
- 100%、125%、150%、200%と複数モニター間のDPI遷移。
- 対象PCと実描画器での入力対光子時間、連続性、残像、入力待ち行列。
- 三値画像層の表示切替、比較（暗）、疑似色、格子、一時メモを組み合わせた長時間の実操作。
- PyInstaller one-folder候補の構築、Explorer起動、実画面での最終受入。

最終判断は`docs/windows-acceptance-checklist.md`へ実結果を記録した人間が
`accept / reject / hold`として行う。
