"""
Excel Formula Engine
====================
Evaluates Excel-style formulas entered by admin for terminal columns.

Supported syntax (same as Excel):
  Cell references: C4, D4, K4 mapped to field names
  IF(condition, true_val, false_val)
  AND(cond1, cond2), OR(cond1, cond2)
  Math: +, -, *, /, (, )
  Functions: AVERAGE(), MAX(), MIN(), ABS(), ROUND(), SQRT(), POWER(), IFERROR(), AVERAGE.WEIGHTED()
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
    "E": "p_close",
    "F": "p_high",
    "G": "p_low",
    "H": "ltp",
    "I": "trend",
    "J": "gann",
    "K": "kd",
    "L": "supersignal",
    "M": "ohlsignal",
    "N": "intrasignal",
    "O": "entry",
    "P": "sl",
    "Q": "tgt1",
    "R": "tgt2",
    "S": "tgt3",
    "T": "tgt4",
    "U": "tgt5",
    "V": "bt1",
    "W": "bt2",
    "X": "bt3",
    "Y": "bt4",
    "Z": "bt5",
    "AA": "diff",
    "AB": "st1",
    "AC": "st2",
    "AD": "st3",
    "AE": "st4",
    "AF": "st5",
    "AG": "pp",
    "AH": "vwap",
    "AI": "volume",
    "AJ": "vwapsignal",
    "AK": "belowsell_abovebuy",
    "AL": "abovebuy_belowsell",
    "AM": "possible_tgt",
    "AN": "s3",
    "AO": "s2",
    "AP": "s1",
    "AQ": "r1",
    "AR": "r2",
    "AS": "r3",
}


class ExcelFormulaEngine:
    """
    Evaluates Excel-style formulas against live tick data.
    Admin enters formulas exactly as they appear in Excel.
    """

    def __init__(self):
        self._compiled: dict[str, str] = {}  # cache: raw -> python expr

    def evaluate(self, formula: str, tick: dict) -> Any:
        """
        Evaluate an Excel formula against a live tick dict.
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
            "p_close": 101.0, "p_high": 106.0, "p_low": 97.0,
            "p_vwap": 101.0, "p_volume": 450000,
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

        # Strip dollar sign prefixes from variable / cell references ($ENTRY -> entry)
        expr = re.sub(r'\$([A-Za-z_]\w*)', r'\1', expr)

        # Handle dot-notation for previous day OHLC (P.CLOSE, P.HIGH, P.LOW, P.VWAP, P.VOLUME)
        expr = re.sub(r'\bP\.CLOSE\b', 'p_close', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bP\.HIGH\b', 'p_high', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bP\.LOW\b', 'p_low', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bP\.VWAP\b', 'p_vwap', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bP\.VOLUME\b', 'p_volume', expr, flags=re.IGNORECASE)

        # Handle hyphenated & combined column aliases
        expr = re.sub(r'\bBELOWSELL-ABOVEBUY\b', 'belowsell_abovebuy', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bABOVEBUY-BELOWSELL\b', 'abovebuy_belowsell', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bABOVE\s+BUY-BELOW\s+SELL\b', 'abovebuy_belowsell', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bPOSSIBLETGT\b', 'possible_tgt', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bPOSSIBLE_TGT\b', 'possible_tgt', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bS-SIGNAL\b', 'supersignal', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bSSIG\b', 'supersignal', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bOHL\b', 'ohlsignal', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bOHLSIG\b', 'ohlsignal', expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bSIGNAL\b', 'intrasignal', expr, flags=re.IGNORECASE)

        # Preserve formula identifiers so they match safe namespace variables
        for alias in (
            "supersignal", "ohlsignal", "intrasignal", "vwapsignal", "trend",
            "entry", "sl", "diff", "gann", "kd", "pp",
            "bt1", "bt2", "bt3", "bt4", "bt5",
            "st1", "st2", "st3", "st4", "st5",
            "tgt1", "tgt2", "tgt3", "tgt4", "tgt5",
            "s1", "s2", "s3", "r1", "r2", "r3",
            "belowsell_abovebuy", "abovebuy_belowsell", "possible_tgt",
            "vwap", "volume",
        ):
            expr = re.sub(rf'\b{alias}\b', alias, expr, flags=re.IGNORECASE)

        # Replace named market data fields with numeric values if present
        named_fields = [
            "open", "high", "low", "close", "vwap", "ltp",
            "volume", "oi", "bp1", "sp1", "atp", "change_pct",
            "p_close", "p_high", "p_low", "p_vwap", "p_volume",
        ]
        for field in named_fields:
            if field in tick and tick[field] is not None:
                val = float(tick.get(field, 0) or 0)
                expr = re.sub(rf'\b{field}\b', str(val), expr, flags=re.IGNORECASE)

        # Replace cell references like C4, D4, K4, AA4 -> data values
        def replace_cell(m):
            col_letter = m.group(1).upper()
            field = COLUMN_MAP.get(col_letter)
            if field and field in tick:
                val = tick.get(field, 0) or 0
                return str(float(val))
            return "0"

        expr = re.sub(r'\b([A-Z]{1,2})\d+\b', replace_cell, expr)

        # Excel functions -> Python
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
        expr = re.sub(r'\bSQRT\s*\(',    'sqrt(',     expr, flags=re.IGNORECASE)
        expr = re.sub(r'\bPOWER\s*\(',   '_POW(',     expr, flags=re.IGNORECASE)

        # Excel string comparison: "DOWN" -> 'DOWN'
        expr = expr.replace('"', "'")

        # Excel uses <> for not-equal, Python uses !=
        expr = expr.replace('<>', '!=')
        # ^ is power in Excel -> Python **
        expr = re.sub(r'\^', '**', expr)
        # 0.5% -> 0.005, 0.1% -> 0.001, 0.005% -> 0.00005 (percentage literal)
        expr = re.sub(r'(\d+\.?\d*)\s*%', lambda m: str(float(m.group(1)) / 100), expr)
        # Excel = is equality (not assignment) — convert single = to ==
        # but not <=, >=, !=, == (already doubled)
        expr = re.sub(r'(?<![<>!=])=(?!=)', '==', expr)

        return expr

    def _safe_ns(self, tick: dict) -> dict:
        """Safe execution namespace for formula evaluation."""
        ns = {
            "sqrt":   math.sqrt,
            "_IF":    lambda cond, t, f='': t if cond else f,
            "_AND":   lambda *args: all(args),
            "_OR":    lambda *args: any(args),
            "_AVG":   lambda *args: sum(args) / len(args) if args else 0,
            "_AVG_WEIGHTED": lambda val, vol=1: round(float(val), 2),
            "_ROUND":  lambda v, d=0: round(float(v), int(d)) if (v is not None and v != '' and str(v).replace('.','',1).replace('-','',1).isdigit()) else v,
            "_IFERROR": lambda v, fallback='': (v if not (v is None or v != v or v == '') else fallback),
            "_POW":   lambda base, exp: math.pow(base, exp),
            "abs":    abs, "max": max, "min": min,
            # Direct field access as variables
            **{k: float(v) if isinstance(v, (int, float)) else v
               for k, v in tick.items()},
        }

        # Safe defaults for all standard formula and market fields
        ns.setdefault("trend", "")
        ns.setdefault("gann", 0.0)
        ns.setdefault("ohlsignal", "")
        ns.setdefault("supersignal", "")
        ns.setdefault("intrasignal", "")
        ns.setdefault("signal", "")
        ns.setdefault("entry", 0.0)
        ns.setdefault("sl", 0.0)
        ns.setdefault("tgt1", 0.0)
        ns.setdefault("tgt2", 0.0)
        ns.setdefault("tgt3", 0.0)
        ns.setdefault("tgt4", 0.0)
        ns.setdefault("tgt5", 0.0)
        ns.setdefault("diff", 0.0)
        ns.setdefault("bt1", 0.0)
        ns.setdefault("bt2", 0.0)
        ns.setdefault("bt3", 0.0)
        ns.setdefault("bt4", 0.0)
        ns.setdefault("bt5", 0.0)
        ns.setdefault("st1", 0.0)
        ns.setdefault("st2", 0.0)
        ns.setdefault("st3", 0.0)
        ns.setdefault("st4", 0.0)
        ns.setdefault("st5", 0.0)
        ns.setdefault("pp", 0.0)
        ns.setdefault("vwap", float(tick.get("vwap") or tick.get("ltp") or 0.0))
        ns.setdefault("volume", float(tick.get("volume") or 0.0))
        ns.setdefault("kd", 0.0)
        ns.setdefault("vwapsignal", "")
        ns.setdefault("belowsell_abovebuy", 0.0)
        ns.setdefault("abovebuy_belowsell", 0.0)
        ns.setdefault("possible_tgt", 0.0)
        ns.setdefault("possibletgt", 0.0)
        ns.setdefault("s3", 0.0)
        ns.setdefault("s2", 0.0)
        ns.setdefault("s1", 0.0)
        ns.setdefault("r1", 0.0)
        ns.setdefault("r2", 0.0)
        ns.setdefault("r3", 0.0)
        ns.setdefault("p_close", float(tick.get("p_close") or tick.get("close") or tick.get("ltp") or 0.0))
        ns.setdefault("p_high", float(tick.get("p_high") or tick.get("high") or tick.get("ltp") or 0.0))
        ns.setdefault("p_low", float(tick.get("p_low") or tick.get("low") or tick.get("ltp") or 0.0))
        ns.setdefault("p_vwap", float(tick.get("p_vwap") or tick.get("vwap") or tick.get("ltp") or 0.0))
        ns.setdefault("p_volume", float(tick.get("p_volume") or tick.get("volume") or 0.0))
        return ns


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = ExcelFormulaEngine()

def evaluate_formula(formula: str, tick: dict) -> Any:
    return _engine.evaluate(formula, tick)

def validate_formula_excel(formula: str) -> tuple[bool, str]:
    return _engine.validate(formula)

def formula_for_book(name: str, formula: str, book: str) -> str:
    """Return standard formula across all books without alteration."""
    return formula


def evaluate_columns_in_order(columns: list[dict], tick: dict) -> dict:
    """
    Evaluate formula columns in order, passing each result into the next
    column's context. Supports cascading cross-column references (DIFF -> BT/ST -> TGT -> SL).
    Runs a multi-pass convergence loop (up to 4 passes) so upstream dependencies resolve completely.
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
    if "p_vwap" not in enriched or enriched["p_vwap"] is None:
        enriched["p_vwap"] = float(enriched.get("vwap") or enriched.get("ltp") or 0)
    if "p_volume" not in enriched or enriched["p_volume"] is None:
        enriched["p_volume"] = float(enriched.get("volume") or 0)

    # If previous day range is flat, fallback to today's high and low for DIFF
    if float(enriched.get("p_high", 0)) <= float(enriched.get("p_low", 0)):
        if tick.get("high") and tick.get("low") and float(tick["high"]) > float(tick["low"]):
            enriched["p_high"] = float(tick["high"])
            enriched["p_low"] = float(tick["low"])

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
            if result is not None and result != " ":
                if results.get(raw_key) != result:
                    changed = True
                results[raw_key] = result
                results[alias_key] = result
                enriched[raw_key] = result
                enriched[alias_key] = result

                # Common aliases
                if raw_key in ("intrasignal", "signal"):
                    enriched["signal"] = result
                    enriched["intrasignal"] = result
                if raw_key in ("supersignal", "s_signal", "ssig"):
                    enriched["supersignal"] = result
                if raw_key in ("ohlsignal", "ohlsig", "ohl"):
                    enriched["ohlsignal"] = result
                if raw_key == "entry":
                    enriched["entry"] = result
                if raw_key == "trend":
                    enriched["trend"] = result
                if raw_key == "diff":
                    enriched["diff"] = result
                if raw_key == "pp":
                    enriched["pp"] = result
                if raw_key == "vwap":
                    enriched["vwap"] = result
                if raw_key == "possible_tgt":
                    enriched["possibletgt"] = result
        if not changed:
            break

    return results
