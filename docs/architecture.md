# アーキテクチャ

ralph-lab の基本コンセプトを図で把握するためのページ。

---

## 1. Ralph loop のコンセプト

**Ralph pattern**: agent CLI を fresh subprocess として繰り返し起動、
gate script による外部判定で「完了」を決める loop パターン。

```mermaid
flowchart LR
    A[spec.yaml<br/>ゴール定義] --> B[Ralph driver]
    B --> C{agent CLI<br/>fresh subprocess}
    C -->|edit| D[current.md]
    D --> E{gate script<br/>exit 0/1}
    E -->|pass| F[完了]
    E -->|fail| G[feedback → next iter]
    G --> C
```

**特徴**:

- **Context 蓄積なし**: 毎 iter で agent は新規 subprocess として起動。長期 context の
  劣化 (100k+ tokens で品質低下) を回避
- **Gate 中立**: gate は任意の bash script、`loop-goal` / `pytest` / `eslint` / `grep -q` 全部使える
- **subprocess を唯一の依存点**に: LLM SDK は agent CLI 側の責任、ralph-lab は起動と JSONL 記録だけ

---

## 2. 4 層防御 (Layer 0 / A / B / C)

Ralph loop での Goodhart hack (agent が「gate は通すが実質壊れた」出力を作る) を
防ぐ多層防御を実装している。

```mermaid
flowchart TB
    subgraph FW[Framework]
        L0[Layer 0: Framework integrity<br/>Workspace.verify_and_restore_base<br/>BASE tamper 検出+復元]
    end
    subgraph GATE[Gate 内]
        LA[Layer A: Syntactic gate<br/>gate.sh の 3 check<br/>対応関係 / 単調性 / 内容 non-empty]
    end
    subgraph DELEG[Delegation]
        LB[Layer B: Delegation<br/>delegate_to: fact-checker / doc-review<br/>特定 skill による狭い判定]
    end
    subgraph JUDGE[Judge]
        LC[Layer C: LLM-as-judge<br/>post_evaluation<br/>総合的な Goodhart 検出]
    end
    L0 --> LA
    LA -->|syntactic pass| LB
    LB -->|delegations pass| LC
    LC -->|final verdict| END[status:<br/>pass / judge_failed /<br/>judge_passed / max_iter]
```

**Layer 別カバレッジ**:

| Layer | 塞ぐ pathology | 実装 | 実測範囲 |
|---|---|---|---|
| 0 | BASE tamper (workspace 前提破壊) | `workspace.py` sha256 + tarfile snapshot | 実測起動事例なし (defense-in-depth) |
| A | 捏造 / 削除 / 内容欠如 | `gate.sh` の 3 check | ~80% |
| B | 逆向き置換 / URL なし dummy | `delegate_to[]` の fact-checker | ~15% |
| C | 迂回 / 洗練された捏造 | `post_evaluation` の LLM judge | ~5% |

「1 層で全部塞ぐ」は不可能、**4 層で 95% を目指す**設計。

---

## 3. 1 iteration の詳細フロー

```mermaid
sequenceDiagram
    participant U as User
    participant D as ralph driver
    participant W as Workspace
    participant A as agent CLI
    participant G as gate script
    participant B as Layer B delegations
    participant J as Layer C judge

    U->>D: uv run ralph run spec.yaml
    D->>W: Workspace.prepare (BASE, current)
    loop max_iterations
        D->>A: render prompt + spawn subprocess
        A->>W: edit current.md
        A-->>D: exit 0 + stdout
        D->>W: verify BASE integrity (Layer 0)
        alt tampered
            D->>W: restore BASE bytes
        end
        D->>G: run gate on current (Layer A)
        G-->>D: exit 0/1 + stdout
        alt gate pass
            D->>B: run delegate_to (Layer B, per retry_aggregate)
            B-->>D: aggregated PASS/FAIL
            alt overall pass
                D->>J: run post_evaluation (Layer C)
                J-->>D: judge PASS/FAIL
                D-->>U: status=pass or judge_failed
            end
        end
        Note over D: JSONL log with stdout_head
    end
    alt max_iterations かつ run_always
        D->>J: 最終 judge を強制実行
        J-->>D: PASS→judge_passed / FAIL→max_iterations
    end
    D-->>U: RalphResult
```

**注目点**:

- **Layer 0 verify** は agent 実行直後、gate 実行直前 (agent が BASE 触っても即復元)
- **Layer B は Layer A pass 後のみ**実行 (fail-fast、cost 節約)
- **Layer C は Ralph pass 後 1 回**、`run_always: true` なら max_iter 到達時も走る
- **JSONL log** に stdout_head 込みで各 layer の結果が残る (P17 で追加)

---

## 4. spec.yaml 構造

spec.yaml が Ralph loop の設計を宣言的に決める。主な field 構造:

```mermaid
graph LR
    S[spec.yaml] --> ID[input_document<br/>+ baseline_document]
    S --> AG[agent:<br/>cmd, args, model, env]
    S --> PR[prompt<br/>agent 用 PROMPT.md]
    S --> GT[gate:<br/>script + delegate_to+]
    GT --> DL[delegate_to N :<br/>cmd, prompt, retries,<br/>retry_aggregate]
    S --> PE[post_evaluation:<br/>cmd, prompt, run_always]
    S --> META[max_iterations,<br/>timeouts, log_path]
```

**必須 field**: `name`, `description`, `input_document`, `agent`, `prompt`, `gate`
**Optional**: `baseline_document`, `gate.delegate_to`, `post_evaluation`, timeouts

詳細は [usage-manual.md](usage-manual.md) の "spec.yaml 完全ガイド" 参照。

---

## 5. ユースケース

想定される 3 種の user persona と代表 workflow。

```mermaid
graph TB
    subgraph U1[persona 1: 文書 curator]
        UC1[自動記事修正<br/>脚注参照の整合性チェック<br/>fact-checker 委譲]
    end
    subgraph U2[persona 2: コード修正エージェント]
        UC2[pytest fail の自動修正<br/>test 期待値保護<br/>削除禁止 prompt]
    end
    subgraph U3[persona 3: framework 研究者]
        UC3[Goodhart 実測<br/>複数 model 比較<br/>予測 vs 実測記録]
    end
```

### ユースケース例

| Persona | 入力 | Gate | Layer B | Layer C |
|---|---|---|---|---|
| 文書 curator | markdown article + baseline | 脚注書式 gate.sh | fact-checker + doc-review | gpt-4o judge |
| コード修正 | Python file + tests dir | `pytest` exit code | (未活用) | (未活用) |
| framework 研究者 | 実験用 fixture | 実験別 gate | 実験別 | Anthropic + OpenAI 比較 |

reference implementation: [`goals/examples/doc-verify-unified.yaml`](https://github.com/dobachi/ralph-lab/blob/main/goals/examples/doc-verify-unified.yaml)。

---

## 6. データフロー: Workspace

Workspace は 1 loop 中に共有される「作業ディレクトリ」。file / dir 両対応 (P9 で拡張)。

```mermaid
graph LR
    subgraph SRC[Sources]
        S1[input_document]
        S2[baseline_document<br/>optional]
    end
    subgraph WS[Workspace root /tmp/ralph-lab-XXX]
        B[BASE / BASE.md<br/>chmod 444 + sha256]
        C[current / current.md<br/>agent が編集]
    end
    S1 -->|copytree| C
    S2 -->|copytree| B
    S1 -.-> |baseline 未指定なら<br/>input を BASE にも| B
```

- **BASE**: source of truth。sha256 と bytes snapshot で integrity 保証 (Layer 0)
- **current**: agent が編集する対象。iter を跨いで累積
- **file 運用**: `BASE.md` / `current.md` 単ファイル
- **dir 運用**: `BASE/` / `current/` 全体を copytree、tarfile snapshot で hash

---

## 7. 関連 ドキュメント

- [getting-started.md](getting-started.md) — 動かすまでの最短経路
- [usage-manual.md](usage-manual.md) — spec.yaml 完全ガイド + 手順
- [knowhow/gate-design-patterns.md](knowhow/gate-design-patterns.md) — Layer A の設計
- [knowhow/gate-delegation-patterns.md](knowhow/gate-delegation-patterns.md) — Layer B/C の設計
- [knowhow/prompt-patterns.md](knowhow/prompt-patterns.md) — prompt 4 pattern
- [CONCLUSIONS.md](CONCLUSIONS.md) — 到達点と残課題
