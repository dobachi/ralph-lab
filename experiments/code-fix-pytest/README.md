# experiments/code-fix-pytest/

**Ralph-lab が code 領域でも動くこと**を実証する mini project。

## Layout

```
code-fix-pytest/
├── src/calc.py         わざと 5 個のバグを仕込んだ電卓モジュール
├── tests/test_calc.py  各バグを pin-point する 15 test
├── gate.sh             pytest を tempdir に layout 組んで走らせる gate
└── README.md
```

## 仕込んだバグ

| 関数 | Bug | 正解 |
|---|---|---|
| `add(a, b)` | `return a * b` | `return a + b` |
| `subtract(a, b)` | `return b - a` | `return a - b` |
| `multiply(a, b)` | `return a + b` | `return a * b` |
| `divide(a, b)` | `b == 0` 未チェック | ZeroDivisionError を出す |
| `factorial(n)` | 負数未対応、0 が 0 を返す | 負数で ValueError、0 と 1 で 1 |

## Gate の設計

ralph-lab の workspace は 1 file (`current.py`) しかコピーしないので、
gate.sh 側で **tempdir に完全 layout を組み直して** pytest を走らせる:

```
$(mktemp -d)/
├── src/calc.py       ← CURRENT からコピー
└── tests/test_calc.py ← project の tests/ からコピー
```

これで pytest が import できる状態になる。副作用は tempdir 内に閉じる。

## 使い方

```bash
# 単体で gate.sh を試す
./gate.sh src/calc.py   # 現状は 12 failed / 3 passed で exit 1

# ralph-lab で自動 fix (aider + gpt-4.1-mini via OpenRouter)
uv run ralph run goals/examples/code-fix-pytest.yaml --pretty
```

## 実測 (2026-09-06)

`aider + openrouter/openai/gpt-4.1-mini` で 5 iter 回した結果:

- **status: max_iterations** (5 iter で pass せず)
- Agent が add を `return 5` に書き換える等の **hack 型 pass 挙動**
- v1 P4 の S-99 捏造、v2 P7 の再現に続く **Goodhart 型行動の 3 度目の観察**

詳細: [docs/experiments/2026-09-06-p9-code-fix-pytest.md](../../docs/experiments/2026-09-06-p9-code-fix-pytest.md)

## Reset

修正済み current.py を元に戻すには git で戻す:

```bash
git checkout src/calc.py
```
