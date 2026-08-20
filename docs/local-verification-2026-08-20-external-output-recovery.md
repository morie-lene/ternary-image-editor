# 外部出力復旧・preflight退避 ローカル検証記録

- 実施日: 2026-08-20
- 対象branch: `main`
- 実装基線: `26a4285ded1e2c75adf3380ab15c695820d7d344`
- 対象応用版: `0.7.0`
- 要求範囲: `TIE-ADD-FLEX-001` version 1.3、`FLEX-SOURCE-005`、`FLEX-SOURCE-006`、
  `FLEX-AT-017`、`FLEX-AT-018`
- 実施環境: macOS 26.5.2 arm64、Python 3.11.15、NumPy 2.4.6、Pillow 12.3.0、
  PySide6 6.11.1
- Windows最終受入: 未実施

本記録は、外部生成器由来の既存出力PNGを限定的に復旧して作業途中から再開する経路と、復旧不能な
既存出力が初期導入を妨げないpreflight退避を対象とする。Windows配布候補、実業務画像、実物ICC、
画面表示の最終受理は代行しない。

## 1. 実装された境界

- 一回の内容指紋付きsnapshotへ厳格出力検査を先に適用し、失敗した同じsnapshotだけを限定復旧へ渡す。
- 実PNG、原画像と同寸、Orientationなし／1、bit depth 1/2/4/8、mode `1/L/RGB/P/LA/RGBA`、
  実使用画素alpha全255を復旧候補とする。DPI／`pHYs`は受否に使わない。
- ICC変換はbest-effortとし、不正ICCは通常RGBへ退避する。共通のsRGB最近傍規則で三値化し、
  元出力を変更せず`OUTPUT`源の未保存状態で開く。
- 有効ICCを適用する前に、PはRGB、1はL、LAはalpha検査後のL、RGBAはalpha検査後のRGBへsampleを
  展開する。ICC変換失敗をmode不一致で捏造して通常RGB退避へ落とさない。
- 明示保存時だけ同じ出力pathを同寸8-bit RGB、アルファなし、三保存色だけのPNGへ置換する。
- 破損・非PNG、IEND後の余剰データ、寸法差、Orientation 2〜8、16-bit、非不透明alphaは復旧しない。
- 起動、フォルダ選択、手動再走査のpreflightは、復旧不能OUTPUTの同じ対で厳格INPUTを無modalで試す。
  INPUT JPEG確認、直接指定のsnapshot確認、前後移動のmodalなしskipは維持する。
- INPUT PNGの厳格検査、自動拡縮、回転、alpha合成、16-bit縮退は変更しない。
- 直接fallbackの許可は失敗時の内容指紋へ束縛する。失敗後、確認中、仮INPUT読込中のいずれかで
  出力が置換された場合はINPUT導入を確定せず、有限回だけOUTPUTを再検査する。

## 2. 公開契約試験

実行命令:

```sh
QT_QPA_PLATFORM=offscreen uv run --locked pytest -q \
  tests/test_flexible_input_contract.py \
  tests/test_display_comparison_contract.py \
  tests/test_packaging.py
```

結果:

```text
100 passed in 1.52s
```

このうち柔軟入力契約試験は、許可modeとbit depthの行列、完全不透明alphaと`P+tRNS`、透明・半透明、
16-bit、寸法、Orientation、破損、IEND後の余剰、単一snapshot、不正ICC退避、P/LAのICC用sample展開、
72/300 DPI、元hash不変、失敗後・確認中・仮INPUT読込中のsnapshot置換、
`OUTPUT`未保存、明示保存後の厳格PNG、保存競合、要保存表示、起動・フォルダ選択・再走査のINPUT退避、
直接指定と前後移動の既存境界を検査した。

公開試験はsdistへ同梱される通常ファイルであり、包装試験が三試験の存在、構築スクリプトからの実行、
柔軟入力追補の固定hashを検査する。

macOS標準ColorSyncのAdobe RGB (1998) profile付きP PNGとGeneric Gray profile付きLA PNGでも、
sampleをそれぞれRGB／Lへ展開した後の基準CMS変換結果と読込ラベルが一致した。これは局所の実profile
probeであり、Windows配布物や外部生成器固有profileの人間受理は閉じない。

## 3. 全局所回帰

実行命令:

```sh
QT_QPA_PLATFORM=offscreen uv run --locked pytest -q
```

結果:

```text
456 passed in 4.64s
```

全局所回帰には公開三試験に加え、GitHub公開対象外の開発時詳細試験を含む。公開100件と全456件を
同じ証拠集合として数えない。

## 4. 静的検査、依存固定、差分形式

実行命令:

```sh
uv run --locked ruff check .
uv lock --check
git diff --check
```

結果:

```text
All checks passed!
Resolved 24 packages
git diff --check: exit 0
```

`pyproject.toml`、応用版定数、`uv.lock`は`0.7.0`で一致した。依存追加はない。

## 5. 安全性・構成・正本境界

- `pyproject.toml`と`uv.lock`の依存集合は変更せず、応用版metadataだけを0.7.0へ更新した。
- 認証、認可、秘密情報、通信、外部API、遠隔送信、ログ出力、CI構成を変更していない。
- 読込対象は従来どおり利用者が選んだローカル出力pathに限定し、復旧読込は元ファイルへ書き込まない。
  書込は既存の明示保存操作だけが行い、読込時の内容指紋と保存直前の内容を照合する。
- 厳格な保存成果物検証器は緩和せず、編集用の限定復旧入口だけを分離した。この分岐は外部形式互換と
  保存正本の保証を混同しないために必要である。
- 独立査読で検出したP／LAと有効ICCのmode不一致、IEND後置余剰、直接fallbackの三競合窓は、
  修正後の公開回帰で再現不能になった。再査読で検出した明示INPUTへの自動fallback指紋混入も、
  自動選択経路だけに指紋を渡す境界へ修正した。査読前の449件／93件成功は完了証拠として採用しない。
- v1.5 HTMLを変更せず、柔軟入力追補version 1.3だけが外部出力復旧を限定上書きする。応用版、追補版、
  物理保存path、表示上の「要保存」、選択源`OUTPUT`を別の識別子として追跡した。

## 6. sdist / wheel

実行命令:

```sh
uv build
```

結果:

```text
Successfully built dist/ternary_image_editor-0.7.0.tar.gz
Successfully built dist/ternary_image_editor-0.7.0-py3-none-any.whl
```

sdistにREADME、柔軟入力追補、公開三試験が入り、wheelに応用本体、実行入口、三形式のアイコン、
版0.7.0 metadataが入ることを一覧検査した。これはWindows one-folder候補やexe起動を証明しない。

## 7. 画面外GUI煙試験

一時QSettingsと`QT_QPA_PLATFORM=offscreen`で主画面を生成、表示処理、閉鎖した。

```text
version=0.7.0
expected_size=None
startup_shutdown=ok
```

Qt画面外pluginは代替書体と`propagateSizeHints()`非対応の警告を出したが、終了符号0だった。
実画面の警告可読性、高DPI、実マウス入力、Windows eventは受理していない。

## 8. 規範文書hash

```text
ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497  docs/ternary_image_editor_spec_v1_5.html
ce148618e7cf049cbfe2fa13e00fc4f3cb17b4726c4bf8e878bd63edcbb6255c  docs/flexible-input-pairing-addendum.md
91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba  docs/mouse-input-bindings-addendum.md
26f1ff442548d51f66bdb518a14d10d92e52e48c10daec877a8ab04ad27e3779  docs/display-comparison-addendum.md
```

Windows構築スクリプトの柔軟入力追補固定値をversion 1.3のhashへ同期し、公開包装試験で照合した。

## 9. 未受理事項と残危険

- Windows 10 / 11でのone-folder構築、exe起動、実画面の警告と一覧表示。
- 対象職場PC、実業務寸法、外部生成器の実PNG、代表する実物ICCによる読込・保存。
- 最近傍三値化が外部生成器の元ラベル意図を復元すること。これは仕様上も保証しない。
- 非協調外部writerが最終照合と置換の極小窓へ書き込む競合。

以上は[Windows最終受入チェックリスト](windows-acceptance-checklist.md)で人間が判定する。局所試験、
包装検査、意味監査は最終受理を代行しない。
