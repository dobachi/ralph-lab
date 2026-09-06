"""Small calculator module with intentional bugs.

Ralph loop の agent が pytest を通すまで fix する対象。
Bugs (5 個仕込んでいる、fix 内容は tests/test_calc.py から読み取れる):
- add: 引数を掛けている (2 * 3 = 6 になっている、正解は 5)
- subtract: 順序を逆にしている
- multiply: 引数を足している
- divide: ゼロ除算チェックがない
- factorial: 負数への対応がない、0 が 0 を返す (正しくは 1)

各 test は 1 個の bug を pin-point する形で書いた。
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    return a * b  # BUG: should be a + b


def subtract(a: int, b: int) -> int:
    return b - a  # BUG: should be a - b


def multiply(a: int, b: int) -> int:
    return a + b  # BUG: should be a * b


def divide(a: int, b: int) -> float:
    # BUG: no zero-division check
    return a / b


def factorial(n: int) -> int:
    # BUG: no negative handling, and 0 returns 0 (should be 1)
    if n < 2:
        return 0
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
