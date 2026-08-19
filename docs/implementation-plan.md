# 実装計画

## 基線

- 応用版: `0.4.0`
- 基線要求正本: `TIE-SPEC-001` version 1.5
- 基線SHA-256: `ed267bde1634072f1e3249d0c7d0670cdec1dbd08e3130380844cff492c0c497`
- 限定追補: `TIE-ADD-FLEX-001` version 1.0
- 限定追補SHA-256: `9f21514f8abdc473a56184514d6499985f893797c274c1b74cc79f6796034384`
- 限定追補: `TIE-ADD-PTR-001` version 1.0
- 限定追補SHA-256: `91d7fec202e9c211de29fcecab5ba3dd78be539b814fb1a58737b38c40964eba`
- 範囲: v1.5の必須事項、`AT-001`〜`AT-079`、`FLEX-AT-001`〜`FLEX-AT-009`、
  `PTR-AT-001`〜`PTR-AT-011`
- 非目的: v1.5 19節の対象外。ただし柔軟入力・対応付けは`TIE-ADD-FLEX-001`、マウス入力割当は
  `TIE-ADD-PTR-001`が各限定範囲を上書きし、各追補の非目的に従う

v1.1とそのSHA-256は履歴正本であり、現在の実装判断には用いない。WP0〜WP6の番号と成果物は
その履歴から継続した作業包として残し、v1.2〜v1.5で追加した実装を同じ責任範囲へ統合する。

## 本質的な達成状態

人間の目視判断を置換せず、原画像と入力三値画像を不変に保ったまま、誤対応・誤画素・表示像混入を避けて三値編集を検証付き別保存できること。

## 作業包

| ID | 成果物 | 依存 | 検証 |
| --- | --- | --- | --- |
| WP0 | Python 3.11環境、入口、文書骨格 | なし | `uv sync`、import |
| WP1 | 対応付け、画像検査、原子的保存 | WP0 | AT-001〜004、026〜029 |
| WP2 | 表示・編集・境界・成分の純粋演算 | WP0 | AT-005〜023 |
| WP3 | 履歴と編集セッション | WP1、WP2 | 保存点、上限、競合、状態遷移 |
| WP4 | 高DPI対応キャンバス | WP2、WP3 | AT-008〜010、030〜033 |
| WP5 | 操作盤、一覧、非同期処理、確認遷移 | WP1、WP3、WP4 | Qt統合試験 |
| WP6 | 受入対応、Windows配布補助 | WP0〜WP5 | 全ローカル検査、Windows判断門 |
| WP7 | ポインタ入力割当、設定schema 2、追補文書 | WP4〜WP6 | PTR-AT-001〜010の局所検査、PTR-AT-011のWindows判断門 |
| WP8 | 非零同数門、二対応方式、JPEG三値化、任意寸法、動的下端保護、追補文書 | WP1〜WP7 | FLEX-AT-001〜009の局所検査とWindows判断門 |

## 現在状態

| 作業包 | 状態 | 証拠境界 |
| --- | --- | --- |
| WP0 | completed | Python 3.11環境、GUI入口、依存固定 |
| WP1 | completed-local-with-residual | 対応付け・厳格読込・原子的保存の単体/故障注入試験。非協調writerの最終照合後競合は既知残危険 |
| WP2 | completed | 純粋演算試験、独立査読で円筆境界回帰を修正 |
| WP3 | completed | 保存点・未確定筆画・token世代を含むセッション試験 |
| WP4 | completed-local | 座標・DPR閾値・画像外余白の単体/Qt試験。Windows AT-030は未受理 |
| WP5 | completed-local | 主画面の筆、履歴、保存、遷移、解析陳腐化のQt統合試験 |
| WP6 | completed-local | ローカル全検査とsdist/wheel配布補助を完了。Windows構築は成果物の配置・非零長・MZ・一意性・hashを事後検査。Windows実機判断門はpending |
| WP7 | completed-local-with-residual | 既存38操作へ七ポインタtokenを追加し、Canvas限定、固定操作との優先、HOLD解放、schema 2移行を実装。全344試験と `uv run ruff check .` が成功。PTR-AT-002/008/010は自動部分証拠、PTR-AT-011はwindows-pending |
| WP8 | completed-local-with-residual | 実装と`TIE-ADD-FLEX-001`を統合し、全367試験、統合差分全体のRuff、版0.4.0 sdist/wheel、画面外GUI煙試験が成功。個別の`automated-partial`項目とWindows実機判断門はpending |

## 変更統制

仕様追加や19節の対象外機能は現基線へ黙って混ぜず、正本と別identityを持つ追補または後続候補へ
分離する。柔軟入力・対応付けは`TIE-ADD-FLEX-001`と`FLEX-AT-*`、マウス入力割当は
`TIE-ADD-PTR-001`と`PTR-AT-*`に分離済みである。必須要求から逸脱する必要が生じた場合は、影響する
受入試験、代替案、残危険を示し、人間判断まで実装を止める。

## 安全性・依存・構成影響

- 新しい認証、認可、秘密情報、network通信、telemetry、外部log出力は追加しない。入力は読取専用、
  書込先は既存の明示保存で指定した出力PNGと協調lockに限る。
- 依存package集合を追加・削除せず、既存のPillow `ImageCms`、NumPy、Qtを使う。
  `pyproject.toml`と`uv.lock`は応用版metadataだけを`0.4.0`へ同期する。Windows配布候補では
  同梱された色管理経路を別途実機確認する。
- 永続設定には列挙型の対応方式だけを加える。不明・破損値は厳格対応へ戻す。自然順の対応表に
  対する確認結果とJPEG一件ごとの変換許可は永続化しない。
- フォルダ変更・再走査・起動時再読込は別`ImageSession`で全候補を読込preflightし、成功後だけ
  session・pairs・foldersを一括導入する。JPEG取消、全候補失敗、blocking count診断では旧状態を
  保ち、出力probeはpreflight、JPEG確認、未保存判断の後へ遅延する。
- 公開包装とWindows構築は新追補の配置と固定hashを検査対象へ追加する。この検査は機能受入や
  Windows実行を代行しない。

## 判断門

1. 実装開始: 要求・計画監査と限定作業範囲が成立。
2. ローカル統合: Python 3.11で試験・静的検査・画面外起動が成功し、受入追跡表に説明のない空欄が無い。
   版0.3.0のポインタ入力統合では344試験と静的検査の成功を記録した。版0.4.0は全367試験、
   統合差分全体のRuff、sdist/wheel、画面外GUI起動を
   `local-verification-2026-08-19-flexible-input.md`へ記録した。
3. 最終受理: Windows実機、高DPI、実データ、性能、配布物起動、PTR-AT-011、柔軟入力追補を人間が
   確認するまで `pending`。
