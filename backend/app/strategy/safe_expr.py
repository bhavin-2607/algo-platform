"""Evaluate user formulas with an AST allow-list.

Names and function calls must already be in the namespace the caller built.
Attribute access, subscripts, imports, and lambdas are rejected.
"""
from __future__ import annotations

import ast
import operator
from typing import Any, Mapping

MAX_EXPR_LEN = 500
MAX_NODES = 200
MAX_POW = 6

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_CMPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


class FormulaError(ValueError):
    """Raised when a formula is empty, too large, or uses a disallowed form."""


def evaluate_expression(expr: str, namespace: Mapping[str, Any]) -> Any:
    if expr is None or not str(expr).strip():
        raise FormulaError("Expression cannot be empty")
    expr = str(expr)
    if len(expr) > MAX_EXPR_LEN:
        raise FormulaError(f"Expression longer than {MAX_EXPR_LEN} characters")

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Invalid expression: {exc.msg}") from exc

    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise FormulaError(f"Expression has more than {MAX_NODES} nodes")

    return _eval(tree.body, namespace)


def _eval(node: ast.AST, ns: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, str, bool)) or node.value is None:
            return node.value
        raise FormulaError("Constant type is not allowed")

    if isinstance(node, ast.Name):
        if node.id not in ns:
            raise FormulaError(f"Unknown name: {node.id}")
        return ns[node.id]

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
        value = _eval(node.operand, ns)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return -value
        return +value

    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _eval(node.left, ns)
        right = _eval(node.right, ns)
        return _BINOPS[type(node.op)](left, right)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        left = _eval(node.left, ns)
        right = _eval(node.right, ns)
        if isinstance(right, bool) or not isinstance(right, (int, float)) or abs(right) > MAX_POW:
            raise FormulaError(f"Power exponent must be a number between -{MAX_POW} and {MAX_POW}")
        return left ** right

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for value in node.values:
                result = _eval(value, ns)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value in node.values:
                result = _eval(value, ns)
                if result:
                    return result
            return result

    if isinstance(node, ast.Compare):
        left = _eval(node.left, ns)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in _CMPS:
                raise FormulaError("Comparison operator is not allowed")
            right = _eval(comparator, ns)
            if not _CMPS[type(op)](left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("Only direct function calls are allowed")
        if node.keywords:
            raise FormulaError("Keyword arguments are not allowed")
        fn = ns.get(node.func.id)
        if not callable(fn):
            raise FormulaError(f"Unknown function: {node.func.id}")
        args = [_eval(arg, ns) for arg in node.args]
        return fn(*args)

    raise FormulaError(f"Disallowed syntax: {type(node).__name__}")
