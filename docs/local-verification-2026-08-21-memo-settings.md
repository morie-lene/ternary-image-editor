# 一時メモ設定・設定入口・ローカル検証記録

## 記録範囲

- 日付: 2026-08-21（Asia/Tokyo）
- アプリケーション版: `0.9.0`
- 直前基線: Git `9789fc0b488be94cdfd441210a5e5f9da8c10dff`（版0.8.0）
- 対象: `TIE-ADD-MEMO-001` version 1.1、`MEMO-AT-011`〜`MEMO-AT-012`
- 規範SHA-256: `151cd712ecef775c3a513a3c8bbcf7df13806e34c42aaaffb7c52d3eab9f08f7`
- 環境: macOS開発環境、Python 3.11、Qt画面外描画
- 受理境界: Windows 10 / 11、物理マウス、実モニター、PyInstaller配布候補の人間受理ではない

この記録は、右クリック一時メモの生成可否と記入色、設定の適用・取消・永続化、設定入口の移動を
局所検証した証拠である。版0.8.0までの試験記録を上書きせず、Windows判断門も閉じない。

## 実装境界

- 既定で、完全一致割当のない右クリックだけを一時メモへ渡す。生成設定を無効にした時は、この
  fallbackだけを停止し、完全一致割当の優先順位を変えない。
- 記入色は`#RRGGBB`としてQSettingsの`memo/color`へ、生成可否は`memo/enabled`へ保存する。
  欠損・破損値は`#FFD640`と有効へそれぞれ退避する。
- 色変更は以後の一筆とメモ中ポインタへ反映し、既存メモ画素と履歴を再着色しない。黒い外線と
  透過度は固定する。メモ画素とメモ履歴自体は引き続き永続化しない。
- 既存`app.open-settings`の表示名を「設定」とし、file menuから除いてmenu barの「ヘルプ」直前へ
  配置する。主toolbarとcontrol panelの既存入口は維持する。

## 自動検査

同じ作業木で次を実行した。

```text
uv run --python 3.11 ruff check .
QT_QPA_PLATFORM=offscreen uv run --python 3.11 pytest -q
QT_QPA_PLATFORM=offscreen uv run --python 3.11 pytest -q $(git ls-files 'tests/test_*.py')
uv lock --check
uv run --python 3.11 python -m compileall -q src
git diff --check
uv build --out-dir <一時directory>
uv run --locked python scripts/verify_isolated_workflow.py <wheel> \
  --version 0.9.0 --expected-wheel-sha256 <wheel-sha256>
```

結果は次のとおりである。

- 全試験: `540 passed in 7.95s`
- Git追跡済み公開九試験: `153 passed in 2.43s`
- Ruff、固定lock、bytecode compile、差分形式: 成功
- 版0.9.0 sdist / wheel構築: 成功
- 隔離wheel経路: 八検査すべて`true`、`status: ok`
- `uv.lock` SHA-256: `2ac442a289a37806a2ec0ce0ab6747834d7aa6172ff795a5dda70a2a56666306`
- 機能差分SHA-256: `9f5aadba53e1c800d2d035d676d6cadacb15aacc13ded317c82e015576bc44d2`
- 検査済みwheel SHA-256: `3b643c3138b72994f159d41960e1d4c46d586fc321edf440824af7bb271b53a6`
- 同時構築sdist SHA-256: `ed17e6003f64deb23baff004cca5e58ee37b27340cac59f7cfcd5c103f38c8a7`

機能差分は`git diff --binary | shasum -a 256`で算出した。この検証記録自体は未追跡であり、自己参照を
避けるため機能差分identityに含めていない。wheelとsdistのhashは、この記録へ構築物hashを追記する
直前に一時directoryへ生成して隔離検査した離脱物のidentityである。従ってsdist hashは当該離脱物を
識別するが、追記後の資料集合を再構築した時の再現hashとは主張しない。

公開`tests/test_transient_memo_layer_contract.py`は、生成無効時の右クリック、将来筆跡だけへの色反映、
既存画素不変、設定往復・破損退避、適用・取消・既定復元、適用または保存の故障時の復元、主窓反映、
表示名、menu構造、toolbar入口を検査する。実Qt信号経路への故障注入では、主窓反映中またはQSettings
保存中の例外後に、control、canvas、状態表示、folder、永続値、反映済み標識を直前状態へ戻し、成功後だけ
通知と小領域解析要求を一度発行することを検査した。非公開開発作業場の設定・主窓回帰は、設定適用が
ラベル、保存基準、未保存状態、履歴位置を変更しないことも検査する。

## 代表実行

一時INI形式QSettingsを与えた実`MainWindow`をQt画面外で表示し、`settings_action.trigger()`から
modal `SettingsDialog`を開いて適用した。出力契約はJSON一行とし、次を観測した。

- menu bar: `ファイル | 画像移動 | 編集 | 表示 | 境界生成 | 設定 | ヘルプ`
- dialog title: `設定`
- 初期値: 生成有効、`#FFD640`
- 適用値: 生成無効、`#2468AC`
- 同じ値がCanvas、QSettings、同じINIから作った新MainWindowで一致
- 終了状態: `status: ok`

これは実QAction、modal dialog、Apply、QSettings保存、再読込を通す代表煙試験である。ただしQt画面外の
計画入力であり、物理pointer、Windows、OS色選択部品、PyInstaller launcherの代表実行ではない。

## 互換性・安全性・構成

- 設定schemaは2のままとし、`memo/enabled`と`memo/color`を欠損可能な既定付き鍵として加えた。
  旧設定は移行操作なしで既定値を補い、不正な局所値だけを退避する。
- 操作実体のIDは`app.open-settings`、既定割当は`Ctrl+,`のまま保ち、「設定」への変更は表示名だけに
  限った。新しい操作ID、入力token、権限は追加していない。
- `pyproject.toml`と`uv.lock`の差分は応用版0.9.0とsdist検証記録の収載だけで、依存package、版範囲、
  Python範囲を変更していない。`uv lock --check`と隔離wheel導入で構成を再検査した。
- 新しい画像入出力、network通信、認証、認可、秘密情報、clipboard、telemetry、外部logを追加して
  いない。新しい永続書込は既存QSettings内の上記二鍵だけで、メモ画素・履歴・保存PNGの所属は
  変えていない。
- 追加状態は生成真偽値とRGB三成分だけで、既存の色検証、QColorDialog、QAction、QSettingsを再利用した。
  メモ操作IDや履歴変換を増やさず、既存メモ非再着色によって変更範囲を閉じた。

## 画面外Qt描画の観測

主窓と設定画面を通常寸法で描画して目視した。

- menu bar順序: `ファイル | 画像移動 | 編集 | 表示 | 境界生成 | 設定 | ヘルプ`
- 設定画面: `980×650`。一般頁を縦scroll可能にし、初期位置で一時メモの有効欄と記入色欄を表示した。
- 「設定」の主toolbar表示も維持した。

最初の実装では設定頁の内容高が865画素となり、低い画面で下端が届かない危険を描画観測で検出した。
一般頁をscroll領域へ変更し、要求欄を疑似色より前へ移した後に上記寸法と可視性を再検査した。
この観測はmacOSのQt画面外pluginと代替書体によるもので、Windowsの字幅、色選択部品、DPI、
実入力を保証しない。

## 残リスク・未完了境界

残リスクあり。次の対象はこの局所検証では受理していない。

- Windows 10 / 11でのmenu bar配置、工具列、設定画面の字切れとscroll操作。
- OSの実色選択部品、実描画器での任意色・固定黒外線の視認性。
- 物理右buttonでの生成有効・無効、完全一致割当優先、drag中のポインタ色。
- 応用再起動後のQSettings復元と、既存メモ非再着色を組み合わせた実操作。
- PyInstaller one-folder候補の構築、Explorer起動、設定保存、終了・再起動。

最終判断は`docs/windows-acceptance-checklist.md`へ実結果を記録した人間が
`accept / reject / hold`として行う。
