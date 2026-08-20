# 用途指向試験補強・ローカル検証記録

## 記録範囲

- 日付: 2026-08-20（Asia/Tokyo）
- アプリケーション版: `0.8.0`
- 作業枝: `codex/local-acceptance-and-test-strategy`
- 基線commit: `6eb283c391f2d78e4542c2b1058759ae5f0fcac4`
- 作業木資料集合: 64 file、`ternary-image-editor-source-snapshot-v1` SHA-256
  `6c60923e40926112bf9576e48f93bae0073ed0d3afe439fa5fbf8c73d2b00ea6`
- 直前基線: 一時メモ層を含む同一0.8.0作業木の全520試験・公開六試験133件
- 環境: macOS 26.5.2 arm64、Python 3.11.15、PySide6 6.11.1、NumPy 2.4.6
- 自動GUI条件: `QT_QPA_PLATFORM=offscreen`
- 受理境界: Windows 10 / 11、物理入力、画面有り描画、PyInstaller配布候補の人間受理ではない

この記録は、単体機能の網羅数だけでは用途上の正常性を示せないという問題に対し、実利用へ近い
組合せ、別process、構築物隔離の三層を追加した証拠である。新しい機能要求や固定画像寸法を導入する
ものではない。試験を選ぶ規則と保証限界は[試験戦略](test-strategy.md)を正本とする。

作業木資料集合は、基線commit上で`git ls-files`と`git ls-files --others --exclude-standard`の和を
path昇順に並べ、通常fileなら`F<TAB>path<TAB>SHA-256(byte列)`、symbolic linkなら
`L<TAB>path<TAB>SHA-256(link先文字列)`を一行とし、先頭へ
`ternary-image-editor-source-snapshot-v1`を置いたmanifestのSHA-256である。自己参照を避けるため、
本記録file一つだけを資料集合から除外した。これは未commit作業木の時点識別子であり、commit IDや
公開済みrevisionへ偽装しない。

## 追加した公開検査面

| 検査面 | 実物 | 支える主張 | 支えない主張 |
| --- | --- | --- | --- |
| 代表寸法・長筆・疎履歴 | `tests/test_real_size_workflow.py` | 2048×1536の長筆で局所更新と全表示像が一致し、メモ複合履歴と200件の疎履歴をUndo・Redoできる | 2048×1536がアプリ要件であること、対象PCの入力対光子時間 |
| 別process競合 | `tests/test_external_process_conflicts.py` | 子processが保持する協調lockと出力置換を検出し、外部出力と未保存編集を壊さない | Windows固有lock・ACL、最終照合後へ割り込む非協調writer |
| 隔離配布物 | `scripts/verify_isolated_workflow.py`、`tests/test_isolated_distribution_workflow.py` | 同梱`uv.lock`からhash付き本番依存を書き出し、offline cacheから完全一致導入した一時環境で、作業木外import、実PNG読込、計画的編集、保存、同一process新sessionのOUTPUT優先再開を全ラベル配列で検査 | 宣言launcher実行、OS通信隔離、OS process再起動、画面有り描画、物理入力、PyInstaller候補 |
| 包装 | `tests/test_packaging.py` | 上記script・文書・九公開試験をsdistへ収載し、Windows構築入口が九試験を必須入力にする | PowerShell・PyInstallerをWindows上で実行したこと |

2048×1536は現在の用途を代表する試験資料であり、読込可能寸法を制限する規範ではない。寸法契約は
従来どおり、正の幅と高さを持ち、対応する原画像と選択ラベル源の幅・高さが完全一致することである。

## 実行結果

### 全体と公開取得物

```text
QT_QPA_PLATFORM=offscreen uv run --locked pytest -q

QT_QPA_PLATFORM=offscreen uv run --locked pytest -q \
  tests/test_flexible_input_contract.py \
  tests/test_display_comparison_contract.py \
  tests/test_brush_responsiveness_contract.py \
  tests/test_memo_history.py \
  tests/test_transient_memo_layer_contract.py \
  tests/test_real_size_workflow.py \
  tests/test_external_process_conflicts.py \
  tests/test_isolated_distribution_workflow.py \
  tests/test_packaging.py
```

- 全試験: `529 passed in 5.89s`
- 公開九試験: `142 passed in 2.02s`
- 直前記録からの増分: 9件。全試験と公開試験の双方へ同じ9件を追加
- 別process競合二件: 単独成功後、同じ二件を五反復して全反復成功

件数は収集単位であって保証率ではない。直前の520件・133件も、その時点の履歴証拠として保持する。

同じ64 file作業木資料集合から構築したsdistを別の一時directoryへ展開し、次も実行した。本記録自身は
上記資料集合から除外しているため、事後記入で試験対象のsource snapshotを変えない。

```text
UV_OFFLINE=1 uv sync --locked --offline --python 3.11
QT_QPA_PLATFORM=offscreen UV_OFFLINE=1 uv run --locked --offline pytest -q
```

- 展開sdistの公開九試験: `142 passed in 6.98s`
- Python 3.11.15、固定lockの21 packageをoffline cacheから導入
- 作業木の非公開試験や親directoryのimportへ依存せず、収載九試験だけを収集

### 構築wheelの隔離利用経路

```text
uv build --out-dir <temporary-build-directory>
uv run --locked python scripts/verify_isolated_workflow.py \
  <wheel-path> --version 0.8.0 \
  --expected-wheel-sha256 <sha256-from-the-same-build>
```

検証scriptはwheelを版metadataで一意に選び、同梱`uv.lock`から本番依存を版・hash付きで書き出す。
これを一時venvへoffline導入し、wheel本体を`--no-deps`で導入して依存整合を検査する。導入後は
当該経路で読み込まれた全`ternary_image_editor.*` moduleが一時`sys.prefix`配下かつ作業木の`src`外で
あることを確認し、実PNGを生成して主窓で読込、計画的編集、非同期保存、同一processの新MainWindow・
新sessionでのOUTPUT優先再開まで行う。保存再読込と再開後は一点でなく全ラベル配列を照合する。

- 終了状態: `status=ok`
- 八検査: `wheel_metadata`、`installed_origin`、`offscreen_main_window_constructed`、`image_loaded`、
  `programmatic_edit_applied`、`saved`、`same_process_new_window_session`、
  `output_priority_resume`の全てが`true`
- 導入元: 一時環境の`lib/python3.11/site-packages/ternary_image_editor/__init__.py`
- 依存解決: `exact_versions_and_hashes_offline_uv_cache`
- `uv.lock` SHA-256: `45647c124e1be19711995c3b432935e20bab7623d8c15203f1364f0bfa59ff6a`
- hash付き本番依存書出しSHA-256:
  `ef543ead8686c6cd25b1825bb2d7e06db8fa24e6da5e19a1fc5a5d98b36af380`
- 実導入版: ternary-image-editor 0.8.0、Python 3.11.15、NumPy 2.4.6、Pillow 12.3.0、
  PySide6 / Addons / Essentials / Shiboken6 6.11.1、SciPy 1.17.1
- OS通信隔離: `false`。応用自体のsocket通信を遮断・観測した試験ではない
- 一時環境: 終了後に削除済み
- 最終wheel SHA-256: `3b6fcb1015ca6acd8d5096e2a7f3a5b7db14480a6e44621441fae335defc0e31`

`declared_entry_point`はwheel metadataを照合しただけで、GUI launcher自体は実行していない。
新sessionは同一OS process内の新MainWindow・新ImageSessionである。実行ファイル終了後の再起動と
同一視しない。操作は私有主窓経路を使う計画的編集であり、物理pointer入力と同一視しない。

### 版0.8.0の筆性能再観測

```text
QT_QPA_PLATFORM=offscreen uv run --locked python scripts/benchmark_brush_responsiveness.py
```

| 条件 | 全画像更新 p50 | 局所更新 p50 | 比 | 減少率 |
| --- | ---: | ---: | ---: | ---: |
| `actual-size-no-grid` | 18.379 ms | 1.470 ms | 12.50倍 | 92.0% |
| `scale-8-auto-grid` | 31.915 ms | 1.635 ms | 19.52倍 | 94.9% |

`actual-size-no-grid`のp95／最大は全画像19.242／20.152 ms、局所1.501／1.533 ms、
`scale-8-auto-grid`は全画像34.710／35.040 ms、局所1.756／1.779 msだった。測定標本がそれぞれ
61件・41件のため、最大値とほぼ同義になるp99は算出欄を設けていない。

同じprocess、同じ生成入力、同じ反復内の比較である。絶対時間の合否門ではなく、macOS画面外描画の
局所退行検出に限る。版0.7.1の原測定JSONは履歴基線として改変しない。

### 品質・包装検査

次を最終作業木で再実行する。

```text
uv lock --check
uv run --locked ruff check .
uv run --locked python -m compileall -q src tests packaging scripts
git diff --check
uv build --out-dir <temporary-build-directory>
```

最終結果は、固定lock、Ruff、bytecode compile、差分形式、sdist / wheel構築の全てが成功した。

## 安全性・外部作用

- `pyproject.toml`と`uv.lock`の差分を照合した。依存名・版・範囲の追加、削除、更新はなく、応用版を
  0.7.0から0.8.0へ更新しただけである。新しいsdist収載物は試験、検証script、公開文書に限る。
- 隔離導入は同梱`uv.lock`からhash付き本番依存を作り、`--offline`、`--no-sources`、`--only-binary`、
  `--require-hashes`で導入する。wheel本体は検査済みSHA-256を強制して`--no-deps`で導入し、最後に
  `uv pip check`を行う。
- verifierと別process試験は`subprocess`へargv列を渡し、shellを介さない。認証、認可、資格情報、
  API key、password、telemetry、clipboard、外部log送信、応用本体のnetwork入口を追加していない。
- verifierの入力画像は一時directory内で生成する。利用者画像、個人情報、機密、外部資料を読まず、
  一時venv・設定・画像・出力は`TemporaryDirectory`終了時に削除する。
- 成功JSONの`wheel.path`と失敗時の`error.details`は局所絶対pathを含み得る。生JSONを無加工で公開せず、
  公開記録にはartifact hash、相対module path、版、境界だけを採る。本記録へ私有絶対pathは収載していない。
- `os_network_sandboxed: false`のとおり、応用processのOS水準通信遮断は証明していない。この未検証を
  offline依存導入の成功へ混ぜない。

## 画面有り観測

生成した色付き原画像と三値画像を通常Qt窓へ読み込む準備までは行った。しかし、macOS実機が施錠中で
自動操作系も解錠できず、窓の目視、物理ポインタ、画面有り描画を観測できなかった。この項目は
`blocked by locked host`であり、不合格でも合格でもない。画面外Qtの成功から補完しない。

この停止は本記録時点の履歴である。2026-08-21にsource通常窓の自動pointer操作を続行し、出力優先、
別process再起動、筆、表示比較、一時メモの限定経路を観測した。そこで低倍率の右単一クリック欠陥を
検出・修正している。結果と非物理入力・非Windows境界は
[macOS画面有り利用経路・ローカル検証記録](local-verification-2026-08-21-headed-macos.md)へ分離した。

## 公開保存面

この試験思想、要求追跡、再現script、版別証拠は、公開GitHubリポジトリの`docs/`と`scripts/`を
案件固有の外部参照面にする。READMEを入口とし、本書と[試験戦略](test-strategy.md)を相互に辿れる形に
する。

現時点で、複数案件へ共通する一般化済みの試験知見を置く専用公開リポジトリは存在確認できていない。
従って、この応用に直接結び付く知見だけをここへ置き、一般理論集へ偽装しない。将来、横断知識庫を
設けるなら、ここから安定版参照を張り、案件の要求・証拠は引き続き本リポジトリへ残す。

## 未完了境界

- 画面有りmacOSのsource自動入力は後続記録で限定実施した。物理入力、右drag、中button drag、
  canvas wheel、OSカーソル非表示の視覚受理は未実施。
- Windows 10 / 11の実マウス、DPI遷移、file lock、ACL、長いpath、ウイルス対策ソフトとの干渉は未受理。
- PyInstaller one-folder候補の構築、exe起動、読込、編集、保存、再起動再開は未受理。
- 外部由来の業務画像全集合、実物ICC、破損資料の全類型は網羅していない。
- 長時間連続操作、極端な密筆、対象職場PCの入力対光子時間は未受理。

最終配布判断は[Windows最終受入チェックリスト](windows-acceptance-checklist.md)へ実機結果を記録し、
人間が`accept / reject / hold`として行う。
