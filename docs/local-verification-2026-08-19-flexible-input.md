# 柔軟入力・対応付けローカル検証記録

- 記録日: 2026-08-19（Asia/Tokyo）
- 対象応用版: `0.4.0`
- 対象branch: `agent/flexible-input-pairing`
- 基点commit: `2a2c2c6b21e9`
- 作業状態: 未commitの統合作業木
- platform: macOS 26.5.2（25F84）、arm64
- Python: 3.11.15
- uv: 0.10.10
- Ruff: 0.16.3
- 要求範囲: `TIE-ADD-FLEX-001`、`FLEX-AT-001`〜`FLEX-AT-009`

## 1. 証拠境界

この記録は、現在のmacOS作業木で再現した自動試験、静的検査、Python包装、画面外GUI起動を
示す。Windows 10 / 11、PowerShell構築制御流、PyInstaller成果物、実マウス・タッチパッド、実ICC
付き三値JPEG、対象業務PC性能の最終受理を示さない。自動結果を人間の配布判断へ昇格させない。

`2048×1536`は対象用途と性能測定の代表実寸であり、アプリケーションの読込要件ではない。本検証で
確認した読込契約は、任意の正寸法、原画像と三値画像の対ごとの同寸、既存出力と画像対の同寸である。

## 2. 公開入力契約試験

実行命令:

```sh
QT_QPA_PLATFORM=offscreen uv run pytest -q tests/test_flexible_input_contract.py
```

結果:

```text
.......................                                                  [100%]
23 passed
```

この公開試験は次を直接検査した。

- 両方式に共通する候補数不一致門と、対応外拡張子の候補数除外
- 両群0件の候補数診断と、診断時に出力先をprobe・作成しないこと
- NFKC互換文字と数字列による自然順、厳格方式との分離、Windows出力名衝突時の全計画拒否
- 確認前に出力フォルダを作らない二相対応計画と、自然順確認取消時の主画面状態不変
- RGB / L JPEGの入力不変、Orientation / CMYK / 偽JPEG拒否、PNG厳格三色経路の非量子化
- `SAVE_RGB`へのRGB二乗距離最小と同距離時の小ラベル選択
- JPEG取込の明示許可、取込直後の未保存、明示保存後の同寸RGB PNG、入力hash不変
- 任意同寸画像対、対寸法不一致時の取引的失敗と既存セッション維持
- `H=80/100/101/1536`の保護開始行、読込正規化、四近傍塗り潰し
- JPEG警告取消が未保存解決より先に働き、現在編集を保つこと
- フォルダ変更を別`ImageSession`でpreflightし、JPEG取消または全候補失敗なら旧session、pairs、
  folders、入力hash、出力先を保つこと
- 出力probeを読込preflight、JPEG確認、未保存判断の後へ遅延し、blocking count診断も現在状態を
  置換せず表示すること

この23件だけでは、自然順表の起動時・手動再走査ごとの実dialog表示、JPEG警告buttonのEscape操作、
実ICC付き三値JPEG、既存出力寸法不一致のGUI fallback、全編集算法の`H=100/101`境界を端から端まで
閉じない。再走査・起動時再読込はフォルダ変更と同じpreflight導入経路を使うが、Windows実dialogは
未受理である。要求追跡表では該当行を`automated-partial`のまま残す。

## 3. 局所全試験

実行命令:

```sh
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -p no:cacheprovider -q
```

結果:

```text
367 passed in 4.01s
```

旧v1.5、版0.3.0のポインタ入力割当、公開包装、今回の柔軟入力と査読後の読込preflight取引境界を
同じ作業木で実行し、回帰不合格はなかった。試験数の増加は要求充足率ではなく、実行した試験項目数
だけを表す。

## 4. 静的検査

実行命令:

```sh
.venv/bin/ruff check .
```

結果:

```text
All checks passed!
```

上記は読込preflight、取消rollback、公開回帰追加を含む統合差分全体へ再実行した結果である。

## 5. Python包装

一時フォルダを`--out-dir`へ指定して実行した。

```sh
uv build --out-dir <mktempで作成した一時フォルダ>
```

結果:

- `ternary_image_editor-0.4.0.tar.gz`を生成した。
- `ternary_image_editor-0.4.0-py3-none-any.whl`を生成した。
- 構築処理は終了符号0で完了した。
- 公開包装試験は、v1.5仕様書、柔軟入力・対応付け追補、マウス入力割当追補、
  `tests/test_flexible_input_contract.py`、`tests/test_packaging.py`のsdist収載を検査した。

この結果はPythonのsdist / wheelを対象とし、Windowsのone-folder配布候補やexe起動を証明しない。

## 6. 画面外GUI煙試験

一時QSettingsを使い、次の条件で主windowを生成、表示処理、閉鎖した。

```sh
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ternary_image_editor import __version__
from ternary_image_editor.main_window import MainWindow

app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory() as directory:
    settings = QSettings(
        str(Path(directory) / "settings.ini"),
        QSettings.Format.IniFormat,
    )
    window = MainWindow(settings=settings)
    window.show()
    app.processEvents()
    print(f"version={__version__}")
    print(f"expected_size={window.expected_size!r}")
    window._allow_close_once = True
    window.close()
    app.processEvents()
print("startup_shutdown=ok")
PY
```

観測結果:

```text
version=0.4.0
expected_size=None
startup_shutdown=ok
```

`expected_size=None`は、主windowの既定読込経路に`2048×1536`等の固定寸法を注入していないことを
示す。Qtの画面外pluginは`propagateSizeHints()`非対応警告を出したが、起動・閉鎖は正常終了した。
この煙試験は画面配置、全対応表の可読性、実マウス入力、高DPIを目視受理しない。

## 7. 要求正本の不変性

実行命令:

```sh
shasum -a 256 \
  docs/ternary_image_editor_spec_v1_5.html \
  docs/flexible-input-pairing-addendum.md
```

結果:

```text
ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497  docs/ternary_image_editor_spec_v1_5.html
9f21514f8abdc473a56184514d6499985f893797c274c1b74cc79f6796034384  docs/flexible-input-pairing-addendum.md
```

v1.5 HTMLは従来hashを維持した。今回範囲の衝突時だけ、別identityの
`TIE-ADD-FLEX-001`を優先する。

## 8. 構成・安全境界

- `git diff -- pyproject.toml uv.lock`で、両ファイルの差分が応用版`0.3.0`から`0.4.0`への同期だけで
  あり、依存packageの追加、削除、版範囲変更がないことを確認した。
- 認証、認可、秘密情報、network通信、telemetry、外部log出力を追加していない。永続設定へ加えた
  値は対応方式の列挙値だけで、不明値は厳格方式へ戻す。
- 原画像と入力三値画像は読取snapshotとして扱う。公開試験はJPEG成功・失敗・取消とPNG経路で
  入力hash不変を検査し、書込先を確認後の出力PNGと一時probeに限定した。probeは取消可能な判断門を
  通過するまで実行しない。
- 公開契約変更は版`0.4.0`、README、別identityの追補、要求追跡表へ明記した。NFKCは自然順の
  表示順だけに使い、厳格対応identityのNFC規則や物理ファイル名を変更しない。

これは入力・永続化・構成面の変更確認であり、Windows ACL、悪意ある画像decoder入力、供給網を
対象にした独立の安全性査読ではない。

## 9. 未完了の判断門

- Windows上の`scripts/build_windows.ps1`実行とPowerShell終了符号伝播
- PyInstaller one-folder成果物の配置、MZ先頭、固定hash、Explorerからの起動
- Windows 10 / 11、高DPI、実ファイル名、自然順全表、JPEG警告、実ICCの目視・内容照合
- 対象業務PCと代表実寸データによる反復性能
- `FLEX-AT-*`で`automated-partial`に残した端から端の分岐

これらは[Windows最終受入チェックリスト](windows-acceptance-checklist.md)へ結果を記録し、人間が
`accept / reject / hold`を決めるまで`windows-pending`とする。
