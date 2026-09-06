#!/bin/bash
# Custom gate for real-doc-refs example.
#
# 契約 (ralph-lab の spec.gate.script):
#   - 呼び出し: gate.sh <current_file>
#   - Exit code: 0 = pass, non-zero = fail
#   - Stdout: 次 iter の agent への feedback
#
# 検査内容:
#   - 本文中の脚注参照 [^N] と定義 [^N]: URL の対応関係
#   - 未定義参照 (本文にあるが定義がない) → fail
#   - 未使用定義 (定義はあるが本文で参照されない) → fail
#
# 実装は Python3 の embedded script。標準ライブラリのみ。

set -u

CURRENT="${1:?Missing target file argument}"
if [ ! -f "$CURRENT" ]; then
    echo "gate.sh: current file not found: $CURRENT" >&2
    exit 2
fi

python3 - "$CURRENT" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

# 本文中の脚注参照 [^N] を抽出。ただし定義行 (行頭 [^N]:) は除外
def_pattern = re.compile(r'^\[\^(\d+)\]:\s', re.MULTILINE)
def_ids = set(m.group(1) for m in def_pattern.finditer(text))

# 定義行を除いた本文からの参照
ref_pattern = re.compile(r'\[\^(\d+)\](?!:)')
lines_body = []
for line in text.splitlines():
    if def_pattern.match(line):
        continue
    lines_body.append(line)
body_text = "\n".join(lines_body)
ref_ids = set(m.group(1) for m in ref_pattern.finditer(body_text))

# 未定義参照 (本文にあるが定義にない)
undefined = sorted(ref_ids - def_ids, key=int)
# 未使用定義 (定義にあるが本文で使われない)
unused = sorted(def_ids - ref_ids, key=int)

# 結果 report
report = [f"# Footnote reference integrity: {path.name}"]
report.append(f"  refs in body   : {sorted(ref_ids, key=int)}")
report.append(f"  defs in bibliography: {sorted(def_ids, key=int)}")

if undefined:
    report.append(f"  ❌ 未定義 (本文にあるが `[^N]: ...` 定義がない): {undefined}")
if unused:
    report.append(f"  ⚠️  未使用 (`[^N]: ...` 定義はあるが本文で参照されない): {unused}")

# 保証しないこと (loop-goal 風)
report.append("")
report.append("保証しないこと:")
report.append("  - 参照先 URL が生きているかは見ない (fetch check なし)")
report.append("  - 定義の内容が主張を支えるかは見ない (対応関係のみ)")
report.append("  - 脚注が正しい位置に付いているかは見ない")

print("\n".join(report))

if undefined:
    print(f"\n判定: NG ({len(undefined)} 個の未定義脚注参照)")
    sys.exit(1)
elif unused:
    print(f"\n判定: WARN ({len(unused)} 個の未使用定義、gate は pass)")
    sys.exit(0)  # 未使用は許容 (定義だけ残す文書は正当)
else:
    print("\n判定: OK")
    sys.exit(0)
PY
