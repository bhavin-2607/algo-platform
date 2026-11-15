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

# Maps Excel column letters to live data field names (supports both default terminal and BSA layout)
COLUMN_MAP = {
    # Default layout
    "B": "open",
    "C": "high",
    "D": "low",
    "E": "p_close",
    "F": "p_high",
    "G": "p_low",
    "H": "ltp",
    "I": "trend",
    "J": "gann",
    "K": "kd",
    "L": "s_signal",
    "M": "ohlsig",
    "N": "intrasignal",
    "O": "entry",
    "P": "sl",
    "Q": "tgt1",
    "R": "tgt2",
    "S": "tgt3",
    "T": "bt1",
    "U": "bt2",
    "V": "bt3",
    "W": "diff",
    "X": "st1",
    "Y": "st2",
    "Z": "st3",
    "AA": "vwap",
    "AB": "volume",
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
            from app.strategy.safe_expr import evaluate_expression

            py_expr = self._to_python(formula, tick)
            result = evaluate_expression(py_expr, self._safe_ns(tick))
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
            from app.strategy.safe_expr import evaluate_expression

            py_expr = self._to_python(formula, dummy_tick)
            result = evaluate_expression(py_expr, self._safe_ns(dummy_tick))
            return True, f"OK — sample result: {result}"
        except Exception as e:
            return False, str(e)

    def _to_python(self, formula: str, tick: dict) -> str:
        """Convert Excel formula to Python expression."""
        expr = formula.strip()
        if expr.startswith("="):
            expr = expr[1:]

        # Handle dot-notation for previous day OHLC (P.CLOSE, P.HIGH, P.LOW)
        expr = re.sub(r'\bP\.CLOSE\b', 'p_close', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bP\.HIGH\b', 'p_high', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bP\.LOW\b', 'p_low', expr, flags=re.IGNORECASE)

        # Handle hyphenated aliases (S-SIGNAL)
        expr = re.sub(r'\bS-SIGNAL\b', 's_signal', expr, flags=re.IGNORECASE)

        # Column results such as SIGNAL are names, not prices. Keep the
        # spelling the namespace uses so signal="BUY" survives validation.
        for alias in (
            "signal", "s_signal", "intrasignal", "ohlsig", "trend",
            "entry", "sl", "diff", "gann", "kd",
            "bt1", "bt2", "bt3", "st1", "st2", "st3",
            "tgt1", "tgt2", "tgt3", "vwap", "volume",
        ):
            expr = re.sub(rf'\b{alias}\b', alias, expr, flags=re.IGNORECASE)

        # Replace named field references first (e.g. high, low, close, ltp)
        named_fields = [
            "open", "high", "low", "close", "vwap", "ltp",
            "volume", "oi", "bp1", "sp1", "atp", "change_pct",
            "p_close", "p_high", "p_low",
        ]
        for field in named_fields:
            if field in tick and tick[field] is not None:
                val = float(tick.get(field, 0) or 0)
                expr = re.sub(rf'\b{field}\b', str(val), expr, flags=re.IGNORECASE)

        # Replace cell refs like C4, D4, K4, AA4 → data values
        def replace_cell(m):
            col_letter = m.group(1).upper()
            field = COLUMN_MAP.get(col_letter)
            if field and field in tick:
                val = tick.get(field, 0) or 0
                return str(float(val))
            return "0"

        expr = re.sub(r'\b([A-Z]{1,2})\d+\b', replace_cell, expr)

        # Excel functions → Python
        expr = re.sub(r'\bAVERAGE\.WEIGHTED\s*\(', '_AVG_WEIGHTED(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bIF\s*\(',      '_IF(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bAND\s*\(',     '_AND(',     expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bOR\s*\(',      '_OR(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bAVERAGE\s*\(', '_AVG(',     expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bMAX\s*\(',     'max(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bMIN\s*\(',     'min(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bABS\s*\(',     'abs(',      expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bROUND\s*\(',   '_ROUND(',   expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bIFERROR\s*\(', '_IFERROR(', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bSQRT\s*\(',    'sqrt(', expr, flags=re.IGNORECASE)
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
        ns = {
            "sqrt":   math.sqrt,
            # Excel helper functions
            "_IF":    lambda cond, t, f: t if cond else f,
            "_AND":   lambda *args: all(args),
            "_OR":    lambda *args: any(args),
            "_AVG":   lambda *args: sum(args) / len(args) if args else 0,
            "_AVG_WEIGHTED": lambda val, vol=1: val,
            "_ROUND":  lambda v, d=0: round(v, int(d)),
            "_IFERROR": lambda v, fallback="": (v if not (v is None or v != v) else fallback),
            "_POW":   lambda base, exp: math.pow(base, exp),
            "abs":    abs, "max": max, "min": min,
            # Direct field access as variables too
            **{k: float(v) if isinstance(v, (int, float)) else v
               for k, v in tick.items()},
        }
        # Filled by an earlier column when that column has a value.
        # Defaults let ENTRY, SL, and Target formulas mention upstream names safely.
        ns.setdefault("signal", "")
        ns.setdefault("s_signal", "")
        ns.setdefault("intrasignal", "")
        ns.setdefault("ohlsig", "")
        ns.setdefault("trend", "")
        ns.setdefault("entry", 0.0)
        ns.setdefault("sl", 0.0)
        ns.setdefault("diff", 0.0)
        ns.setdefault("gann", 0.0)
        ns.setdefault("kd", 0.0)
        ns.setdefault("bt1", 0.0)
        ns.setdefault("bt2", 0.0)
        ns.setdefault("bt3", 0.0)
        ns.setdefault("st1", 0.0)
        ns.setdefault("st2", 0.0)
        ns.setdefault("st3", 0.0)
        ns.setdefault("tgt1", 0.0)
        ns.setdefault("tgt2", 0.0)
        ns.setdefault("tgt3", 0.0)
        ns.setdefault("p_close", float(tick.get("p_close") or tick.get("close") or tick.get("ltp") or 0))
        ns.setdefault("p_high", float(tick.get("p_high") or tick.get("high") or tick.get("ltp") or 0))
        ns.setdefault("p_low", float(tick.get("p_low") or tick.get("low") or tick.get("ltp") or 0))
        return ns


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = ExcelFormulaEngine()

def evaluate_formula(formula: str, tick: dict) -> Any:
    return _engine.evaluate(formula, tick)

def validate_formula_excel(formula: str) -> tuple[bool, str]:
    return _engine.validate(formula)


OPTION_PERCENT_COLUMNS = frozenset({
    "T11.8", "T23.8", "T38.2", "T50", "T61.8", "T78.6", "T100", "T1.618", "T2.618",
})


def formula_for_book(name: str, formula: str, book: str) -> str:
    """Options keep their own saved formula. A new options copy starts at 100x the equity T percent."""
    if book == "option" and name in OPTION_PERCENT_COLUMNS:
        return scale_option_percents(formula)
    return formula


def scale_option_percents(formula: str) -> str:
    """Equity T11.8 uses 0.118%. The options table uses 11.8% for that same column."""
    def wider(match: re.Match) -> str:
        number = float(match.group(1)) * 100
        text = f"{number:.4f}".rstrip("0").rstrip(".")
        return f"{text}%"

    return re.sub(r"(\d+\.?\d*)\s*%", wider, formula)


def evaluate_columns_in_order(columns: list[dict], tick: dict) -> dict:
    """
    Evaluate multiple formula columns in order, passing each result
    into the next column's context. Supports cross-column references
    like SIGNAL, ENTRY, DIFF, BT1-3, ST1-3 in SL/Target formulas.
    Runs a multi-pass convergence loop (up to 4 passes) so upstream
    dependencies (e.g. DIFF -> BT1 -> TGT1) resolve completely.

    columns: [{"name": "SIGNAL", "formula": "=IF(ltp>open,'BUY','SELL')"}, ...]
    tick: live market data dict
    Returns: dict of {column_name_lower: result}
    """
    results = {}
    enriched = {**tick}

    # Ensure previous day OHLC defaults gracefully from current close/high/low/ltp
    if "p_close" not in enriched or enriched["p_close"] is None:
        enriched["p_close"] = float(enriched.get("close") or enriched.get("ltp") or 0)
    if "p_high" not in enriched or enriched["p_high"] is None:
        enriched["p_high"] = float(enriched.get("high") or enriched.get("ltp") or 0)
    if "p_low" not in enriched or enriched["p_low"] is None:
        enriched["p_low"] = float(enriched.get("low") or enriched.get("ltp") or 0)

    # Multi-pass convergence loop (stops early once values stabilize)
    for _ in range(4):
        changed = False
        for col in columns:
            formula = col.get("formula")
            orig_name = col.get("name", "")
            raw_key   = orig_name.lower().strip()
            alias_key = raw_key.replace("-", "_").replace(".", "_")
            if not formula:
                continue

            result = evaluate_formula(formula, enriched)
            if result is not None and result not in (" ", ""):
                if results.get(raw_key) != result:
                    changed = True
                results[raw_key] = result
                results[alias_key] = result
                enriched[raw_key] = result
                enriched[alias_key] = result

                # Common aliases
                if raw_key in ("signal", "s_signal", "intrasignal"):
                    enriched["signal"] = result
                if raw_key == "entry":
                    enriched["entry"] = result
                if raw_key == "trend":
                    enriched["trend"] = result
                if raw_key == "diff":
                    enriched["diff"] = result
                if raw_key == "bt1":
                    enriched["bt1"] = result
                if raw_key == "st1":
                    enriched["st1"] = result
        if not changed:
            break

    return results
