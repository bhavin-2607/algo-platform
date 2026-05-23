"""
Excel Formula Engine
====================
Evaluates Excel-style formulas entered by admin for terminal columns.

Supported syntax (same as Excel):
  Cell references: C4, D4, K4 → mapped to field names
  IF(condition, true_val, false_val)
  AND(cond1, cond2), OR(cond1, cond2)
  Math: +, -, *, /, (, )
  Functions: AVERAGE(), MAX(), MIN(), ABS(), ROUND()

Field mapping (column letter → data field):
  B = open, C = high, D = low, E = close
  F = vwap, K = ltp, I = volume, J = oi
  L = change_pct, G = bp1 (best buy), H = sp1 (best sell)

Examples:
  TREND:  =IF((C4+D4+E4)/3>K4,"DOWN","UP")
  HCG:    =C4-E4
  OCG:    =B4-E4
  LCG:    =E4-D4
  KD:     =(E4-D4)/(C4-D4)*100
"""
import re
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# Maps Excel column letters to live data field names
COLUMN_MAP = {
    "B": "open",
    "C": "high",
    "D": "low",
    "E": "close",
    "F": "vwap",
    "G": "bp1",
    "H": "sp1",
    "I": "volume",
    "J": "oi",
    "K": "ltp",
    "L": "change_pct",
}


class ExcelFormulaEngine:
    """
    Evaluates Excel-style formulas against live tick data.
    Admin enters formulas exactly as they appear in Excel.
    """

    def __init__(self):
        self._compiled: dict[str, str] = {}  # cache: raw → python expr

    def evaluate(self, formula: str, tick: dict) -> Any:
        """
        Evaluate an Excel formula against a live tick dict.
        
        tick keys: open, high, low, close, vwap, ltp, volume, oi,
                   change_pct, bp1, sp1, atp
        Returns: string, float, int, or None
        """
        if not formula:
            return None

        formula = formula.strip()
        if formula.startswith("="):
            formula = formula[1:]

        try:
            py_expr = self._to_python(formula, tick)
            result  = eval(py_expr, {"__builtins__": {}}, self._safe_ns(tick))
            # Round floats to 2 decimals
            if isinstance(result, float):
                return round(result, 2)
            return result
        except ZeroDivisionError:
            return None
        except Exception as e:
            logger.debug(f"Formula eval error [{formula}]: {e}")
            return None

    def validate(self, formula: str) -> tuple[bool, str]:
        """Validate a formula without running it. Returns (ok, error_msg)."""
        if not formula or not formula.strip():
            return False, "Formula cannot be empty"

        dummy_tick = {
            "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0,
            "vwap": 101.0, "ltp": 103.0, "volume": 500000, "oi": 1000,
            "change_pct": 1.5, "bp1": 102.5, "sp1": 103.0, "atp": 101.5,
        }
        try:
            result = self.evaluate(formula, dummy_tick)
            return True, f"OK — sample result: {result}"
        except Exception as e:
            return False, str(e)

    def _to_python(self, formula: str, tick: dict) -> str:
        """Convert Excel formula to Python expression."""
        expr = formula

        # Replace named field references first (e.g. high, low, close, ltp)
        named_fields = [
            "open", "high", "low", "close", "vwap", "ltp",
            "volume", "oi", "bp1", "sp1", "atp", "change_pct",
        ]
        for field in named_fields:
            val = float(tick.get(field, 0) or 0)
            expr = re.sub(rf'\b{field}\b', str(val), expr, flags=re.IGNORECASE)

        # Replace cell refs like C4, D4, K4 → data values
        def replace_cell(m):
            col_letter = m.group(1).upper()
            field = COLUMN_MAP.get(col_letter)
            if field and field in tick:
                val = tick.get(field, 0) or 0
                return str(float(val))
            return "0"

        expr = re.sub(r'\b([A-Z]{1,2})\d+\b', replace_cell, expr)

        # Excel functions → Python
        expr = re.sub(r'\bIF\s*\(',      '_IF(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bAND\s*\(',     '_AND(',     expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bOR\s*\(',      '_OR(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bAVERAGE\s*\(', '_AVG(',     expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bMAX\s*\(',     'max(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bMIN\s*\(',     'min(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bABS\s*\(',     'abs(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bROUND\s*\(',   '_ROUND(',   expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bIFERROR\s*\(', '_IFERROR(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bSQRT\s*\(',    'math.sqrt(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bPOWER\s*\(',   '_POW(',     expr, flags=re.IGNORECASE)

        # Excel string comparison: "DOWN" → 'DOWN'
        expr = expr.replace('"', "'")

        # Excel uses <> for not-equal, Python uses !=
        expr = expr.replace('<>', '!=')
        # ^ is power in Excel (not XOR) → Python **
        expr = re.sub(r'\^', '**', expr)
        # 0.5% → 0.005 (percentage literal)
        expr = re.sub(r'(\d+\.?\d*)\s*%', lambda m: str(float(m.group(1)) / 100), expr)
        # Excel = is equality (not assignment) — convert single = to ==
        # but not <=, >=, !=, == (already doubled)
        expr = re.sub(r'(?<![<>!=])=(?!=)', '==', expr)

        return expr

    def _safe_ns(self, tick: dict) -> dict:
        """Safe namespace for eval."""
        return {
            "math": math,
            # Excel helper functions
            "_IF":    lambda cond, t, f: t if cond else f,
            "_AND":   lambda *args: all(args),
            "_OR":    lambda *args: any(args),
            "_AVG":   lambda *args: sum(args) / len(args) if args else 0,
            "_ROUND":  lambda v, d=0: round(v, int(d)),
            "_IFERROR": lambda v, fallback="": (v if not (v is None or v != v) else fallback),
            "_POW":   lambda base, exp: math.pow(base, exp),
            "abs":    abs, "max": max, "min": min,
            # Direct field access as variables too
            **{k: float(v) if isinstance(v, (int, float)) else v
               for k, v in tick.items()},
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = ExcelFormulaEngine()

def evaluate_formula(formula: str, tick: dict) -> Any:
    return _engine.evaluate(formula, tick)

def validate_formula_excel(formula: str) -> tuple[bool, str]:
    return _engine.validate(formula)


def evaluate_columns_in_order(columns: list[dict], tick: dict) -> dict:
    """
    Evaluate multiple formula columns in order, passing each result
    into the next column's context. Supports cross-column references
    like SIGNAL, ENTRY in SL/Target formulas.

    columns: [{"name": "SIGNAL", "formula": "=IF(ltp>open,'BUY','SELL')"}, ...]
    tick: live market data dict
    Returns: dict of {column_name_lower: result}
    """
    results = {}
    enriched = {**tick}

    for col in columns:
        formula = col.get("formula")
        name    = col.get("name", "").lower()
        if not formula:
            continue
        result = evaluate_formula(formula, enriched)
        if result is not None and result not in (" ", ""):
            results[name] = result
            enriched[name] = result   # inject into next col's context
            # Common aliases
            if name == "signal": enriched["signal"] = result
            if name == "entry":  enriched["entry"]  = result
            if name == "trend":  enriched["trend"]  = result

    return results
