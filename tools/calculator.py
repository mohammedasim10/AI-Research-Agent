"""
tools/calculator.py - Safe AST-based Mathematical and Statistical Calculator Tool.
Performs deterministic mathematical operations without eval() or exec().
"""

import ast
import math
import operator
from typing import Any, Dict, List, Optional, Union
from tools.base import BaseTool, ToolParameter


class SafeMathEvaluator:
    """Safe AST visitor for evaluating mathematical expressions."""

    ALLOWED_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    ALLOWED_FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "sqrt": math.sqrt,
        "pow": math.pow,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "ceil": math.ceil,
        "floor": math.floor,
        "mean": lambda vals: sum(vals) / len(vals) if vals else 0.0,
        "pct_change": lambda old, new: ((new - old) / old * 100.0) if old != 0 else 0.0,
    }

    ALLOWED_CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
    }

    def evaluate(self, expr: str) -> Union[int, float]:
        """Parses and securely computes arithmetic expressions."""
        if not expr or not isinstance(expr, str):
            raise ValueError("Expression must be a non-empty string")

        # Parse into AST
        try:
            node = ast.parse(expr.strip(), mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid math syntax: {e}")

        return self._eval_node(node.body)

    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

        elif isinstance(node, ast.Name):
            name = node.id.lower()
            if name in self.ALLOWED_CONSTANTS:
                return self.ALLOWED_CONSTANTS[name]
            raise ValueError(f"Unknown variable or constant: '{node.id}'")

        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in self.ALLOWED_OPERATORS:
                val = self._eval_node(node.operand)
                return self.ALLOWED_OPERATORS[op_type](val)
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")

        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type in self.ALLOWED_OPERATORS:
                left = self._eval_node(node.left)
                right = self._eval_node(node.right)
                # Guard against huge power operations leading to Denial of Service
                if op_type == ast.Pow:
                    if abs(right) > 1000 or (isinstance(left, (int, float)) and abs(left) > 1e10 and right > 10):
                        raise ValueError("Exponent too large (DoS prevention)")
                return self.ALLOWED_OPERATORS[op_type](left, right)
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id.lower()
                if func_name in self.ALLOWED_FUNCTIONS:
                    args = [self._eval_node(arg) for arg in node.args]
                    return self.ALLOWED_FUNCTIONS[func_name](*args)
            raise ValueError(f"Unsupported function call in math expression")

        elif isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]

        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt) for elt in node.elts)

        raise ValueError(f"Unsupported expression construct: {type(node).__name__}")


class CalculatorTool(BaseTool):
    """Executes deterministic mathematical and statistical calculations."""

    def __init__(self):
        super().__init__(
            name="calculator",
            description="Evaluates mathematical, percentage, and statistical expressions safely without eval().",
            parameters=[
                ToolParameter(
                    name="expression",
                    type_name="string",
                    description="The mathematical expression to evaluate (e.g. '(1500 - 1200) / 1200 * 100', 'sqrt(144) * 2.5', 'pct_change(80, 100)').",
                    required=True,
                )
            ],
        )
        self.evaluator = SafeMathEvaluator()

    def _run(self, expression: str) -> Dict[str, Any]:
        result = self.evaluator.evaluate(expression)
        return {
            "expression": expression,
            "result": result,
            "formatted": f"{result:,.4f}".rstrip("0").rstrip(".") if isinstance(result, float) else str(result),
        }
