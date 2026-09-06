"""Tests that pin-point each bug in src/calc.py.

Ralph loop's gate.sh runs pytest on this file. agent (aider / opencode)
must fix src/calc.py until all tests pass.
"""

from __future__ import annotations

import pytest

from calc import add, divide, factorial, multiply, subtract


class TestAdd:
    def test_positive(self):
        assert add(2, 3) == 5

    def test_zero(self):
        assert add(0, 7) == 7

    def test_negative(self):
        assert add(-3, 5) == 2


class TestSubtract:
    def test_basic(self):
        assert subtract(10, 4) == 6

    def test_zero(self):
        assert subtract(5, 0) == 5

    def test_negative_result(self):
        assert subtract(3, 8) == -5


class TestMultiply:
    def test_basic(self):
        assert multiply(3, 4) == 12

    def test_zero(self):
        assert multiply(0, 100) == 0

    def test_negative(self):
        assert multiply(-2, 5) == -10


class TestDivide:
    def test_basic(self):
        assert divide(10, 2) == 5.0

    def test_by_zero_raises(self):
        with pytest.raises(ZeroDivisionError):
            divide(10, 0)


class TestFactorial:
    def test_zero(self):
        assert factorial(0) == 1

    def test_one(self):
        assert factorial(1) == 1

    def test_five(self):
        assert factorial(5) == 120

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            factorial(-1)
