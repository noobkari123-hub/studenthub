"""
Deterministic math/calculation engine. Runs BEFORE any web search or topic
classification — a query that's actually a computation ("Solve 2!",
"25 × 18", "x² - 5x + 6 = 0", "derivative of x³ + 2x") gets computed
directly and exactly, instead of being treated as a topic to look up.

Uses sympy's own parser (sympy.parsing.sympy_parser.parse_expr) rather
than Python's eval/exec — parse_expr is given an explicit, restricted
global_dict of safe math names, so it can't reach arbitrary Python
builtins or do anything beyond building a symbolic expression. This is
the standard safe pattern for parsing untrusted math text with sympy.

solve_math(query) returns None for anything that isn't actually a
calculation, so the caller falls through to normal topic search.
"""
import math
import re

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations,
    implicit_multiplication_application, convert_xor,
)

_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application, convert_xor)

# Only these names are reachable from parsed text — parse_expr cannot
# resolve anything outside this dict, so there's no path to arbitrary
# Python execution regardless of what a user types. Integer/Float/
# Rational/Symbol etc. aren't user-facing functions — they're what
# sympy's own transformations (auto_number, auto_symbol) generate
# internally while parsing, so they must be present for parsing itself
# to work, not just for evaluation.
_SAFE_GLOBALS = {
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
    "asin": sympy.asin, "acos": sympy.acos, "atan": sympy.atan,
    "sqrt": sympy.sqrt, "log": sympy.log, "ln": sympy.log, "exp": sympy.exp,
    "pi": sympy.pi, "E": sympy.E, "Abs": sympy.Abs, "abs": sympy.Abs,
    "factorial": sympy.factorial,
    "Integer": sympy.Integer, "Float": sympy.Float, "Rational": sympy.Rational,
    "Symbol": sympy.Symbol, "Function": sympy.Function,
    "oo": sympy.oo, "I": sympy.I, "S": sympy.S,
    # Explicitly empty — without this, Python's eval() silently injects
    # the REAL builtins (open, __import__, exec, ...) into the
    # evaluation namespace by default. This is what actually sandboxes
    # the parse, not just the restricted name list above.
    "__builtins__": {},
}

_MAX_INPUT_LEN = 300
_MAX_FACTORIAL_N = 500  # avoid pathological huge computations

_LEADING_VERBS = (
    r"^(solve|calculate|compute|evaluate|simplify|find|what\s+is|what's|whats)\s+"
)
_KNOWN_FUNC_NAMES = ("sin", "cos", "tan", "asin", "acos", "atan",
                     "sqrt", "log", "ln", "exp", "abs", "factorial")


def _strip_leading_verb(text: str) -> str:
    return re.sub(_LEADING_VERBS, "", text.strip(), flags=re.IGNORECASE).strip()


def _normalize(text: str) -> str:
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
    text = text.replace("²", "**2").replace("³", "**3")
    return text


def _looks_like_expression(text: str) -> bool:
    """Guards the generic 'evaluate this expression' fallback so a plain
    word like 'RAM' (which sympy would happily parse as a bare symbol)
    never gets treated as a solved calculation."""
    t = text
    for name in _KNOWN_FUNC_NAMES:
        t = re.sub(rf"\b{name}\b", "", t, flags=re.IGNORECASE)
    if not re.search(r"\d", t):
        return False
    return bool(re.fullmatch(r"[0-9xyzXYZ\.\+\-\*/\^\(\),%!\s]*", t))


def _safe_parse(expr_text: str):
    if len(expr_text) > _MAX_INPUT_LEN:
        return None
    try:
        return parse_expr(
            expr_text,
            transformations=_TRANSFORMATIONS,
            global_dict=dict(_SAFE_GLOBALS),
            local_dict={},
            evaluate=True,
        )
    except (SyntaxError, TypeError, ValueError, sympy.SympifyError, AttributeError, RecursionError):
        return None


def _pretty(text: str) -> str:
    """Display-only formatting — never re-parsed, so it's safe to make
    this cosmetic (× instead of *, ^ instead of **)."""
    result = str(text).replace("**", "^").replace("*", " × ")
    return re.sub(r"\s+", " ", result).strip()


def _format_result(value):
    try:
        if value.is_Integer or value.is_Rational:
            simplified = sympy.nsimplify(value)
            return str(simplified)
        evalf = value.evalf(10)
        return str(evalf).rstrip("0").rstrip(".") if "." in str(evalf) else str(evalf)
    except Exception:
        return str(value)


# ----------------------------------------------------------------------
# Individual solvers — each returns a result dict or None.
# ----------------------------------------------------------------------
def _try_factorial(query: str, cleaned: str):
    m = re.fullmatch(r"(\d+)\s*!", cleaned.strip())
    if not m:
        m2 = re.search(r"factorial\s+of\s+(\d+)", query, flags=re.IGNORECASE)
        if not m2:
            return None
        n = int(m2.group(1))
    else:
        n = int(m.group(1))
    if n > _MAX_FACTORIAL_N or n < 0:
        return None
    result = math.factorial(n)
    working = " × ".join(str(i) for i in range(n, 1, -1)) if n > 1 else "1 (by definition)"
    return {
        "given": f"{n}!",
        "formula": "n! = n × (n-1) × (n-2) × ... × 1",
        "calculation": f"{n}! = {working}" if n > 1 else f"{n}! = {working}",
        "answer": f"{n}! = {result}",
    }


def _try_percent_of(query: str):
    m = re.search(r"([\d.]+)\s*%\s*of\s*([\d,]+\.?\d*)", query, flags=re.IGNORECASE)
    if not m:
        return None
    pct = float(m.group(1))
    base = float(m.group(2).replace(",", ""))
    result = (pct / 100) * base
    result_str = f"{result:g}"
    return {
        "given": f"{pct:g}% of {base:g}",
        "formula": "percentage of a number = (percent / 100) × number",
        "calculation": f"({pct:g} / 100) × {base:g} = {result_str}",
        "answer": f"{pct:g}% of {base:g} is {result_str}.",
    }


def _try_physics(query: str):
    """A small set of common formula patterns extracted from natural
    language — not a general physics engine, but real, exact computation
    for the patterns it does recognize."""
    q = query.lower()

    # distance = speed × time
    m = re.search(r"([\d.]+)\s*m/s.*?([\d.]+)\s*(seconds|second|s\b|hours|hour|hr)", q)
    if m and ("distance" in q or "how far" in q or "travel" in q):
        speed = float(m.group(1))
        time = float(m.group(2))
        unit = m.group(3)
        if "hour" in unit or unit == "hr":
            time_s = time * 3600
        else:
            time_s = time
        distance = speed * time_s
        return {
            "given": f"speed = {speed:g} m/s, time = {time:g} {unit}",
            "formula": "distance = speed × time",
            "calculation": f"{speed:g} × {time_s:g} = {distance:g} m",
            "answer": f"Distance = {distance:g} m",
        }

    # force = mass × acceleration
    m = re.search(r"mass\s*(?:is|=)?\s*([\d.]+)\s*kg.*?acceleration\s*(?:is|=)?\s*([\d.]+)\s*m/s", q)
    if m:
        mass = float(m.group(1))
        accel = float(m.group(2))
        force = mass * accel
        return {
            "given": f"mass = {mass:g} kg, acceleration = {accel:g} m/s²",
            "formula": "F = m × a",
            "calculation": f"{mass:g} × {accel:g} = {force:g} N",
            "answer": f"Force = {force:g} N",
        }

    return None


def _try_derivative_integral(query: str):
    m = re.search(r"(?:derivative|differentiate)\s+(?:of\s+)?(.+)", query, flags=re.IGNORECASE)
    if m:
        expr_text = _normalize(m.group(1).strip().rstrip("?."))
        expr = _safe_parse(expr_text)
        if expr is None:
            return None
        symbol = _primary_symbol(expr)
        if symbol is None:
            return None
        derivative = sympy.diff(expr, symbol)
        return {
            "given": f"f({symbol}) = {_pretty(expr)}",
            "formula": f"d/d{symbol} [f({symbol})]",
            "calculation": f"d/d{symbol} [{_pretty(expr)}] = {_pretty(derivative)}",
            "answer": f"The derivative is {_pretty(derivative)}",
        }

    m = re.search(r"(?:integral|integrate)\s+(?:of\s+)?(.+)", query, flags=re.IGNORECASE)
    if m:
        expr_text = _normalize(m.group(1).strip().rstrip("?."))
        expr = _safe_parse(expr_text)
        if expr is None:
            return None
        symbol = _primary_symbol(expr)
        if symbol is None:
            return None
        integral = sympy.integrate(expr, symbol)
        steps = None
        # Integration by parts is the clearest student-level method for ln(x)
        # and similar products. Keep these details with the deterministic result
        # so the AI helper can explain the exact calculation instead of jumping
        # straight to SymPy's final expression.
        if expr == sympy.log(symbol):
            steps = [
                f"Use integration by parts: ∫u dv = uv − ∫v du.",
                "Choose u = ln(x) and dv = dx.",
                "Then du = 1/x dx and v = x.",
                "Substitute: ∫ ln(x) dx = x ln(x) − ∫ x(1/x) dx.",
                "Simplify: x(1/x) = 1, so ∫ ln(x) dx = x ln(x) − ∫1 dx.",
                "Integrate 1: ∫1 dx = x.",
                "Therefore, the result is x ln(x) − x + C.",
            ]
        pretty_expr = _pretty(expr)
        pretty_integral = _pretty(integral)
        if expr == sympy.log(symbol):
            pretty_expr = "ln(x)"
            pretty_integral = "x ln(x) − x"
        return {
            "given": f"f({symbol}) = {pretty_expr}",
            "formula": f"∫ f({symbol}) d{symbol}",
            "calculation": f"∫ [{pretty_expr}] d{symbol} = {pretty_integral} + C",
            "answer": f"The integral is {pretty_integral} + C",
            "steps": steps,
        }

    return None


def _primary_symbol(expr):
    symbols = list(expr.free_symbols)
    if not symbols:
        return None
    # Prefer x/y/z if present, otherwise take whatever's there.
    for preferred in (sympy.Symbol("x"), sympy.Symbol("y"), sympy.Symbol("z")):
        if preferred in symbols:
            return preferred
    return symbols[0]


def _try_equation(query: str, cleaned: str):
    if "=" not in cleaned:
        return None
    lhs_text, rhs_text = cleaned.split("=", 1)
    lhs_text, rhs_text = _normalize(lhs_text).strip(), _normalize(rhs_text).strip().rstrip("?.")
    lhs = _safe_parse(lhs_text)
    rhs = _safe_parse(rhs_text) if rhs_text else sympy.Integer(0)
    if lhs is None or rhs is None:
        return None
    symbol = _primary_symbol(lhs) or _primary_symbol(rhs)
    if symbol is None:
        return None
    try:
        solutions = sympy.solve(sympy.Eq(lhs, rhs), symbol)
    except (NotImplementedError, sympy.SympifyError):
        return None
    if not solutions:
        return None
    sol_strs = [str(s) for s in solutions]
    answer = (f"{symbol} = {sol_strs[0]}" if len(sol_strs) == 1
              else " or ".join(f"{symbol} = {s}" for s in sol_strs))
    return {
        "given": _pretty(f"{lhs} = {rhs}"),
        "formula": "Solved algebraically for " + str(symbol),
        "calculation": f"{_pretty(lhs)} = {_pretty(rhs)}  →  {answer}",
        "answer": answer,
    }


def _try_generic_expression(cleaned: str):
    normalized = _normalize(cleaned).strip().rstrip("?.")
    if not _looks_like_expression(normalized):
        return None
    expr = _safe_parse(normalized)
    if expr is None:
        return None
    if expr.free_symbols:
        simplified = sympy.simplify(expr)
        return {
            "given": _pretty(normalized),
            "formula": "Simplified algebraically",
            "calculation": f"{_pretty(expr)} = {_pretty(simplified)}",
            "answer": f"Simplified: {_pretty(simplified)}",
        }
    result_str = _format_result(expr)
    return {
        "given": _pretty(normalized),
        "formula": None,
        "calculation": f"{_pretty(normalized)} = {result_str}",
        "answer": f"{_pretty(normalized)} = {result_str}",
    }


# ----------------------------------------------------------------------
def solve_math(query: str):
    """Returns {"given","formula","calculation","answer"} or None."""
    query = (query or "").strip()
    if not query:
        return None
    cleaned = _strip_leading_verb(query)

    for solver in (
        lambda: _try_factorial(query, cleaned),
        lambda: _try_physics(query),
        lambda: _try_percent_of(query),
        lambda: _try_derivative_integral(cleaned),
        lambda: _try_equation(query, cleaned),
        lambda: _try_generic_expression(cleaned),
    ):
        try:
            result = solver()
        except Exception:
            result = None
        if result:
            return result
    return None
