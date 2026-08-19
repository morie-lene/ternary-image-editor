# 保存済み出力再開・選択源境界 ローカル検証記録

- 対象応用版: `0.5.1`
- 対象追補: `TIE-ADD-FLEX-001` version 1.2
- 追補SHA-256: `a2d8a8c1c1c6202a770bac69f14f5cfed71f8f1428e9ffee49b4a06875849798`
- 実施日: 2026-08-19（Asia/Tokyo）
- 環境: macOS、Python 3.11、Qt画面外基盤

## 対象変更

- 正常な編集済み出力を選んだ時は、原画像と出力だけを実編集対として開く。
- 未使用の入力三値画像を復号、色・形式・寸法検査、保存時の変更検査へ用いない。
- `INPUT`を選んだ時の厳格検査は維持する。
- 原画像はEXIF Orientation反映後、選択ラベル源は復号後の幅・高さを完全照合する。
- 入力・出力ラベルPNGのOrientation 2〜8を自動転置せず拒否する。
- preflightと前後移動では不正候補ごとのmodalを出さず、直接指定では対象付き診断を一回だけ出す。
- preflightの全候補が失敗した場合は、各画像名、失敗区分、具体的理由を一件の状態表示へ集約する。
- 不正出力から入力版へのfallback許可を出力snapshotへ限定し、同一snapshotへの再確認を抑止する。
- 出力局所エラーと分類不能例外を画像対全体の恒久的な読込不能cacheへ入れない。

## 自動検証

次を実行し、全410件が成功した。

```text
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -p no:cacheprovider -q
410 passed
```

公開取得物へ収載する二試験だけでは66件が成功した。内訳は柔軟入力契約62件、包装契約4件である。

```text
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/test_flexible_input_contract.py tests/test_packaging.py
66 passed
```

静的検査、差分形式、依存固定も成功した。

```text
.venv/bin/ruff check .
All checks passed!

git diff --check
exit 0

uv lock --check
Resolved 24 packages
```

`uv build --out-dir <一時フォルダ>`で次を生成した。

- `ternary_image_editor-0.5.1.tar.gz`
- `ternary_image_editor-0.5.1-py3-none-any.whl`

## 入出力・構成影響

- 原画像と入力三値画像は引き続き読取専用で、書込先は利用者指定の出力PNGと既存の協調lockに限る。
- 認証、認可、秘密情報、network通信、telemetry、外部log出力を追加していない。
- 依存package集合と永続設定schemaを変更していない。`pyproject.toml`と`uv.lock`の変更は応用版
  metadataの`0.5.1`同期だけである。
- 「画像対」は対応付け上の原画像＋入力三値画像、「編集用画像対」は原画像＋選択ラベル源、
  「出力snapshot」は不正出力fallback許可の寿命として別の身元に保った。
- 運用中の読込失敗は状態欄、対象外一覧、または直接操作時の対象付き診断へ出す。外部logは入力pathを
  不要に持ち出すため追加しない。同一の不正出力snapshotは承認済みfallbackを再利用し、内容変更時は
  再検査する。この通知回数と再試行経路は公開試験で固定した。

Qt画面外基盤では、設定を空にした`MainWindow`の構築、表示、event loop終了が成功した。正常出力、
不正色または別寸法の未使用入力、EXIF方向付き原画像を使う回帰では、出力ラベルの完全復元と未保存なしの
再開を確認した。再開後に未使用入力を置換または削除しても、追加編集の保存が成功した。

## 閉じていない判断門

- Windows 10/11実機での構築、起動、modal、焦点、DPI、Explorer表示。
- 利用現場の実画像そのものを使った再現確認。実ファイルを受領していないため、個別原因は未確定。
- Windows配布候補の人間受理と実データhash記録。
- 非協調外部writerが最終照合と置換の極小区間へ割り込む保存競合。

したがって、版0.5.1はローカル統合済みだが、Windows配布受理済みとは扱わない。
