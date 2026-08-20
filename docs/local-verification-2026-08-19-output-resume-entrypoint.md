# 保存済み出力優先入口 ローカル検証記録

- 対象応用版: `0.6.1`
- 対象追補: `TIE-ADD-FLEX-001` version 1.2
- 追補SHA-256: `a2d8a8c1c1c6202a770bac69f14f5cfed71f8f1428e9ffee49b4a06875849798`
- 実施日: 2026-08-19（Asia/Tokyo）
- 環境: macOS、Python 3.11、Qt画面外基盤

## 確定した不一致

通常GUIの起動時再読込、フォルダ選択、再走査、一覧選択、前後移動は、正常な既存出力があれば
既に出力を選んでいた。一方、試験・埋込み用の公開入口`MainWindow.open_pair(index)`だけは、編集元を
省略すると`INPUT`を固定既定にしており、同じ優先規則を迂回していた。

修正前の基線へ、入力ラベルを全無、出力ラベルを全境界とした一組を渡す回帰試験を加えると、
編集元が`EditSource.INPUT`となって失敗した。版0.6.1では編集元省略時だけ共通の選択処理を使い、
明示した`EditSource.INPUT`と`EditSource.OUTPUT`は従来どおり尊重する。

公開入口`open_pair(index: int, source: EditSource | None = None) -> bool`の返値は従来どおり成否を表し、
範囲外indexは`False`、競合中は`BusyError`とする。
構造化出力、CLI、MCP、保存形式、公開エラー形式は変更していない。編集元を省略してINPUT固定に
依存していた呼出しだけが意図した互換性変更の対象であり、INPUT固定が必要な呼出しは明示指定できる。

## 固定した回帰境界

- 編集元省略＋正常出力: 出力を開く。
- 編集元省略＋出力なし: 入力を開く。
- 明示INPUT: 正常出力が存在しても入力を開く。
- 編集元省略＋不正出力: 直接入口の既存fallback確認と取消境界を維持する。
- 厳格対応＋三値入力JPEG＋正常出力: 冷間起動でJPEG確認・三値化を行わず出力を開く。

## 自動検証

全試験は417件、公開取得物へ収載する三試験は73件が成功した。公開試験の内訳は、柔軟入力契約
64件、表示比較契約5件、包装契約4件である。

```text
QT_QPA_PLATFORM=offscreen uv run pytest -q
417 passed in 4.27s

QT_QPA_PLATFORM=offscreen uv run pytest -q \
  tests/test_flexible_input_contract.py \
  tests/test_display_comparison_contract.py \
  tests/test_packaging.py
73 passed in 1.14s
```

試験枠外でも一時フォルダへ厳格名の原画像・入力PNG・全境界の正常出力PNGを作り、`MainWindow`を
表示してQt事象処理後に冷間起動と`open_pair(0)`を実行した。双方で出力ラベルの完全一致を確認した。
初回の診断用試行はQt事象処理前に初期状態を検査して失敗したため、実起動と同じ事象処理境界へ直して
再実行した。

```text
QT_QPA_PLATFORM=offscreen uv run python <代表煙試験>
cold_start_source=output direct_source=output labels=boundary status=ok
```

静的検査、依存固定、差分形式、包装構築も成功した。

```text
uv run ruff check .
All checks passed!

uv lock --check
Resolved 24 packages

git diff --check
exit 0

uv build --out-dir <一時フォルダ>
ternary_image_editor-0.6.1.tar.gz
ternary_image_editor-0.6.1-py3-none-any.whl
```

## 入出力・構成影響

- 新しい依存、永続設定、通信、認証、外部logを追加していない。
- 原画像と入力三値画像は読取専用で、保存先と保存形式を変更していない。
- `pyproject.toml`、package版、`uv.lock`の応用版metadataだけを`0.6.1`へ同期した。
- lock内の外部package名・版・hash、Python要件、構築入口は変更していない。`uv lock --check`で
  固定関係を再検査した。
- 実装差分は編集元選択と公開回帰に限り、認証、認可、秘密情報、入力pathの外部送信、log保存、
  `image_io`、保存処理、協調lock、構築scriptへ変更を加えていない。
- 仕様正本と三追補の内容・版・固定hashは変更していない。

## 閉じていない判断門

- Windows 10/11配布候補からの冷間起動、再走査、Unicode path、権限、file lock。
- 利用現場の原画像名、三値画像名、出力名、画像形式、表示寸法、Orientationを使った再現。
- 通常GUIの冷間起動は修正前の局所probeでも出力優先に成功した。従って、今回確定した直接入口の
  不一致がWindows上の元報告の唯一の原因だったとは断定しない。
- 入力三値ファイル自体が欠ける場合は、正常出力だけあっても非零同数門を通らない。これは現行の
  対応身元契約であり、変更するなら別の要求判断が要る。

版0.6.1はローカル統合済みだが、Windows配布受理済みとは扱わない。
