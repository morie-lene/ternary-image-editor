# マウス入力割当・ローカル検証記録 2026-08-19

## 証拠境界

- 対象版: `0.3.0`
- 対象枝: `agent/add-pointer-bindings`
- 基線仕様SHA-256:
  `ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`
- マウス入力割当追補SHA-256:
  `91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba`
- 環境: macOS 26.5.2、Python 3.11.15、PySide6 / Qt 6.11.1、uv 0.10.10

この記録はmacOS開発作業木の局所証拠であり、Windows配布受理を表さない。試験集合は公開
取得物へ含めないため、公開cloneだけではpytest結果を再現できない。

## 実行結果

```text
uv run pytest
343 passed in 5.34s

uv run ruff check .
All checks passed!

uv lock --check
Resolved 24 packages

git diff --check
差分空白異常なし

QT_QPA_PLATFORM=offscreen uv run python -c '<GUI smoke>'
GUI smoke: window visible, version 0.3.0, clean close
```

GUI煙試験は一時設定領域を使い、実利用設定を読まずに `QApplication` と `MainWindow` を生成、
表示event処理、版 `0.3.0`、正常終了を確認した。画面外platform固有のfont aliasおよび
`propagateSizeHints` 警告は出たが、終了符号は0だった。

`uv build` は次を生成した。

```text
dist/ternary_image_editor-0.3.0.tar.gz
dist/ternary_image_editor-0.3.0-py3-none-any.whl
```

sdistには応用本体、README、v1.1・v1.5仕様、マウス入力割当追補と解説文書が入り、
`tests/`は入っていない。wheelには応用packageとアイコン資産が入り、版metadataは0.3.0で
ある。これらの局所生成物自体はGitHubへ登録しない。

## 重点回帰

- 七基底token、Ctrl / Alt / Shift正規化、Meta拒否、鍵盤割当との競合を検証した。
- Canvas上の完全一致割当だけを配送し、一般UIへ介入しないことを検証した。
- 未割当wheel・中button・左buttonと一時パンを維持し、割当済み無効操作から固定操作へ
  fallbackしないことを検証した。
- button HOLDを押下時tokenで解放し、修飾キー先離し、非活性化、設定適用で残留しないことを
  検証した。
- 同期modalの入れ子event loop中に物理解放と設定変更が起きても、古いbutton latchを後から
  再生成せず、次の未割当中button panが正常解放される回帰を固定した。
- angleDeltaを持たずpixelDeltaだけを持つ縦wheel eventについて、割当配送と未割当拡縮を
  検証した。
- 描画中の別pointer入力を発火も予約もせず、左button解放で一筆が正常確定することを
  検証した。
- schema 0 / 1の鍵盤値、schema 2のpointer値、空文字解除、局所破損を検証した。正常な明示
  割当と欠落既定値・破損fallbackが競合する場合は、正常値を優先する回帰も固定した。
- Windows構築scriptが公開取得物でpytestを警告付き省略し、v1.5仕様とマウス追補を固定hash
  で配布候補へ複製する文字列・順序契約を自動検証した。

## 公開契約・依存・安全境界

- 依存packageとその版指定は基線から変更していない。`pyproject.toml` と `uv.lock` の依存に
  関する差分はなく、lockfile差分は根package版 `0.2.0` から `0.3.0` への更新だけである。
  `uv lock --check` で整合を確認した。
- 公開契約の変更は、応用版 `0.3.0`、設定schema 2、Canvas上のpointer割当に限る。既存の
  38操作ID、CLI入口 `ternary-image-editor`、画像入出力形式、v1.5基線仕様は変更していない。
  schema 0 / 1は鍵盤割当として移行し、schema 2はpointer tokenを往復する。
- `ternary-image-editor` は標準入出力を契約する処理CLIではなくGUI起動入口であり、成功包・
  失敗包などの機械可読出力契約は存在しない。schema 2も公開APIではなく、Qt設定領域に保存
  する内部永続形式である。代表実行は上記GUI煙試験で確認した。
- 認証、認可、秘密情報、通信、記録出力、画像file書込経路、全域mouse hookは加えていない。
  pointer入力の対象は応用内Canvasに限定し、一般UIと他応用の入力へ介入しない。
- 試験sourceは開発作業木にのみ存在し、公開Git取得物・sdist・wheelから意図的に除外している。
  したがって公開clone単独で343件を再現できない一方、上記結果と要求対応は本記録および
  `requirements-traceability.md` に残した。配布archiveに `tests/` がないことも検査した。
- 実装は、永続化時の正規化、実行時のbutton latch、設定画面の入力捕捉を分離した。これは
  schema互換、入れ子event loop、HOLD解放の残留防止という別々の責務による。新しい依存、
  新しい操作ID、全域入力監視は導入していない。

## 未検証・人間判断待ち

- Windows実機のBack / Forward button識別と押下・解放順序
- precision touchpadのevent分割、自然scroll、inertia時の実起動回数
- 実modal画面中にbuttonを解放した際のWindows固有event順序
- 実利用中のschema 0 / 1設定をschema 2へ移行した結果
- 更新後PowerShell構築scriptのWindows実行、0.3.0 exe起動、実配布物への追補同梱

上記は [Windows最終受入チェックリスト](windows-acceptance-checklist.md) のPTR判断門で記録し、
人間が `accept / reject / hold` を決める。
