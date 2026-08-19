# 表示比較（暗）ローカル検証記録

- 実行日時: `2026-08-19 17:15 JST`
- 対象応用版: `0.6.0`
- 対象要求: `TIE-ADD-DISP-CMP-001` version 1.0、`DISP-CMP-001`〜`DISP-CMP-008`
- 基線commit: `c91dc6155f309b83641759331b32639f8607aebe`
- 作業状態: 基線以後の未commit統合差分。版0.5.1までの既存変更を保持した同一作業木
- 実行環境: macOS 26.5.2 arm64、Python 3.11.15、PySide6 / Qt 6.11.1
- Windows最終受理: 未完了

## 1. 規範文書の内容一致

```text
ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497  docs/ternary_image_editor_spec_v1_5.html
91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba  docs/mouse-input-bindings-addendum.md
a2d8a8c1c1c6202a770bac69f14f5cfed71f8f1428e9ffee49b4a06875849798  docs/flexible-input-pairing-addendum.md
26f1ff442548d51f66bdb518a14d10d92e52e48c10daec877a8ab04ad27e3779  docs/display-comparison-addendum.md
```

v1.5 HTMLと既存二追補は変更せず、表示合成・表示設定・操作件数だけを新しい追補身元へ分離した。

## 2. 実装境界

- `ImageCanvas`へ既定falseの表示状態を加え、切替時は完成表示像cacheだけを無効化する。
- 両層表示時だけ原解像度のQPainter `CompositionMode_Darken`を使う。疑似色無効・有効の双方へ
  現在の三値表示RGBを基底として適用する。
- 無効時は従来の保存色Lighten／疑似色SourceOverを維持する。
- 主操作盤、表示menu、Action Registry、設定画面を一つの操作ID
  `view.toggle-darken-comparison`へ接続した。既定割当は空で、現行操作総数は39。
- `AppSettings` schema 2へ既定falseの`darken_comparison_enabled`を加え、QSettings
  `view/darkenComparison`へ保存する。欠損・破損はfalseへ退避する。
- 画像ラベル、内容基準、履歴、session改訂、未保存判定、保存経路は変更していない。

## 3. 自動試験

### 全試験

```text
QT_QPA_PLATFORM=offscreen uv run pytest -q
415 passed in 4.26s
```

### 公開取得物へ収載する三試験

```text
QT_QPA_PLATFORM=offscreen uv run pytest -q \
  tests/test_flexible_input_contract.py \
  tests/test_display_comparison_contract.py \
  tests/test_packaging.py
71 passed in 1.11s
```

表示比較の公開五試験は、保存色・疑似色、既定無効、ON→OFF、原画像不透明度0/25/50/75/100%、
片層・双方非表示、ラベル不変、操作・チェック・canvas同期、再起動復元、破損設定fallback、
画像状態不変、切替前後の保存PNGバイト同一を検査した。中間不透明度はQtの8-bit量子化を含むため
理想式との差を各成分2以下とし、0%と100%は完全一致を要求した。

### 関連経路の限定回帰

```text
QT_QPA_PLATFORM=offscreen uv run pytest -q \
  tests/test_display_comparison_contract.py tests/test_action_registry.py \
  tests/test_control_panel.py tests/test_settings_model.py \
  tests/test_settings_dialog_v15.py tests/test_v15_main_window.py \
  tests/test_v15_canvas.py
144 passed in 2.83s
```

## 4. 静的検査・依存・包装

```text
uv run ruff check .
All checks passed!

uv lock --check
Resolved 24 packages in 2ms

git diff --check
exit 0

uv build --out-dir <専用一時フォルダ>
Successfully built ternary_image_editor-0.6.0.tar.gz
Successfully built ternary_image_editor-0.6.0-py3-none-any.whl
```

包装試験は、sdistへREADME、入口、四規範文書、三公開試験、Windows構築scriptが入り、wheelへ
応用本体・GUI入口・三形式のicon・版metadataが入ることを実物で検査した。新規公開試験は
`.gitignore`の追跡許可とsdist明示収載の双方へ加えた。Windows構築scriptは新追補と公開試験を
必須入力にし、追補をone-folderの`docs`へ複製して固定SHA-256を照合・表示する。

依存packageの追加・削除・版変更はない。`pyproject.toml`と`uv.lock`のroot応用版だけを0.6.0へ
同期した。認証、認可、秘密情報、network通信、telemetry、外部log、画像入出力権限は追加していない。
永続化変更は既存QSettings内の既定可能な真偽値一項だけである。

## 5. 画面外GUI煙試験

`QT_QPA_PLATFORM=offscreen`で設定を空にした主画面を生成し、比較（暗）操作をQActionから起動した。
チェック欄とcanvas状態が有効になり、Qt event loopが終了符号0で完了した。試験専用QSettingsは
終了後に消去した。

## 6. 自動監査と独立査読

意味監査は、操作ID、表示状態、永続key、文書身元、包装配置を別物として追跡する必要を指摘した。
本差分は設計判断、追補、要求追跡表、公開試験、固定hash検査へその対応を記録した。`pyproject.toml`
検出に伴う依存・安全性警告については、前節のlock検査、依存集合不変、外部作用不増を証拠とする。

読取専用の独立実装査読は、重大・中・軽微の欠陥と要求漏れをいずれも0件と判定した。関連156試験、
全415試験、公開71試験、Ruff、依存固定、差分形式を再確認し、乱数47×61画素・不透明度0〜100%で
理想式との差が最大2、端点0、cache再利用・切替再生成を確認した。

別の独立動的probeは、公開試験関数を呼ばず、画素、疑似色、片層、cache、QAction、設定取引、
再起動、履歴付きsession、実PNG保存を検査した。切替前後の保存PNG SHA-256はともに
`1f061ae3f5be8b4902f50947560096db60f21c8f1b7b001f5197b458d7521c4d`だった。

2048×1536の合成像を12回交互生成したmacOS offscreen上の参考値は、比較（暗）ON中央値1.394ms
（1.329〜1.487ms）、OFF中央値1.360ms（1.334〜1.772ms）、cache hit中央値0.000584msだった。
これは対象業務PC、Windows描画器、実データの性能受理ではない。

読取専用の独立契約・包装査読は、PTR追補の38操作と後続表示追補の39件目、永続設定境界、全8要求の
Windows保留、版、四文書hash、sdist収載、PowerShellの必須入力・複製・照合・報告順を再確認した。
指摘三件を文書上で修正した後の再査読では未解決finding 0件、局所統合`accept`、Windows配布`hold`
という判定だった。

## 7. 未検証と最終判断門

- Windows 10 / 11上のPyInstaller構築とexe起動。
- Windows描画器でのDarken量子化、100%〜200%表示、高DPI・複数monitor移動。
- Explorer、主window、taskbar上の版0.6.0配布候補。
- 対象業務PCの実データでの比較（暗）切替時間、パン・拡縮時間、常用記憶量。
- Windows上の設定Apply/Cancel、任意の鍵盤・実マウス割当、再起動復元。

以上は`windows-acceptance-checklist.md`へ記録し、人間が`accept / reject / hold`を決める。
本記録は局所統合証拠であり、Windows配布受理を代行しない。
