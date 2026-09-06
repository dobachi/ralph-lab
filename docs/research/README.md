# docs/research/

Ralph loop / agent loop の周辺調査。実装から独立した「地図」の記録。

## 現行

- **plan.md** — v1 の初期調査計画 (agent loop landscape)
- **2026-08-05-agent-loop-overview.md** — v1 の初期調査 (Anthropic 公式
  知見、multi-agent 15x token、multi-agent failure taxonomy 等)。ralph-lab
  設計時にも参照する
- **2026-09-06-ralph-loop-landscape.md** — Ralph loop 系の先行実装調査。
  **ralph-lab を作る直接の動機**になった資料。§7 の未解決論点 (検証関数
  設計、drift 制御、コスト設計) が ralph-lab の設計指針

## 位置づけ

これらは **v1 (agent-loop-lab) 時代の調査**を migration したもの。ralph-lab
は v1 の実装は捨てたが調査は継承する。理由:

- Ralph loop 系の landscape 認識は v1/v2 で変わらない
- Anthropic の agent design 原則 (Building effective agents 系) も同じ
- ralph-lab の設計判断は Ralph landscape 調査に依拠している

## 更新方針

- 新規調査を追加するときは `YYYY-MM-DD-<topic>.md` の命名
- 情報が古くなったら「outdated」注記を付けて残す (削除しない、Ralph 系の
  変化速度が速いため updates を追跡する意味あり)
