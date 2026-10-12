"""
Telegram can't render LaTeX, so AI answers like  \\frac{B a^{2}}{\\sqrt{2}}  show up as raw
code. plain_math() turns LaTeX into readable Unicode:  B a² / √2  .
"""
import re

_SUP_TO = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿˣⁱᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷʸᶻ"
_SUB_TO = "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"
_SUP = str.maketrans("0123456789+-=()nxiabcdefghjklmoprstuvwyz", _SUP_TO)
_SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvx", _SUB_TO)

_SYMBOLS = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε", r"\varepsilon": "ε",
    r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ", r"\vartheta": "θ", r"\iota": "ι", r"\kappa": "κ",
    r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ", r"\sigma": "σ",
    r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ", r"\varphi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ", r"\Xi": "Ξ", r"\Pi": "Π",
    r"\Sigma": "Σ", r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\cdot": "·", r"\times": "×", r"\div": "÷", r"\pm": "±", r"\mp": "∓", r"\circ": "°", r"\degree": "°",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\neq": "≠", r"\ne": "≠", r"\approx": "≈",
    r"\equiv": "≡", r"\propto": "∝", r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇", r"\int": "∫",
    r"\sum": "∑", r"\prod": "∏", r"\to": "→", r"\rightarrow": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔", r"\leftrightarrow": "↔",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\cup": "∪", r"\cap": "∩", r"\forall": "∀",
    r"\exists": "∃", r"\therefore": "∴", r"\because": "∵", r"\angle": "∠", r"\perp": "⊥", r"\parallel": "∥",
    r"\hbar": "ħ", r"\ell": "ℓ", r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯", r"\vec": "",
    r"\hat": "", r"\bar": "", r"\overline": "", r"\mathrm": "", r"\mathbf": "", r"\boldsymbol": "",
}
_FUNCS = ("sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "lim", "exp", "max", "min", "det", "arcsin",
          "arccos", "arctan", "sinh", "cosh", "tanh")

_GROUP = r"\{([^{}]*)\}"


def _script(text, table, marker):
    text = text.strip()
    out = text.translate(table)
    allowed = _SUP_TO if marker == "^" else _SUB_TO
    # if some char has no unicode form, keep a readable fallback like ^(a+b)
    return out if all(c in allowed for c in out) else marker + "(" + text + ")"


def _sup(m):
    return _script(m.group(1), _SUP, "^")


def _sub(m):
    return _script(m.group(1), _SUB, "_")


def plain_math(text: str) -> str:
    if not text or ("\\" not in text and "$" not in text and "^{" not in text and "_{" not in text):
        return text
    t = text
    # math delimiters
    t = re.sub(r"\\\[|\\\]|\\\(|\\\)", "", t)
    t = re.sub(r"\$\$?", "", t)
    t = t.replace("\\left", "").replace("\\right", "").replace("\\displaystyle", "").replace("\\big", "")
    t = re.sub(r"\\[,;:! ]|\\quad|\\qquad", " ", t)
    t = t.replace("\\\\", "\n")
    t = re.sub(r"\\(?:text|textbf|textit|mathrm|mathbf|operatorname)\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\lim_" + _GROUP, r"lim(\1)", t)
    t = re.sub(r"\^\s*\{?\\circ\}?", "°", t)
    t = re.sub(r"\^\s*\{?°\}?", "°", t)
    for k in sorted(_SYMBOLS, key=len, reverse=True):
        t = re.sub(re.escape(k) + r"(?![A-Za-z])", _SYMBOLS[k], t)
    t = re.sub(r"([ΔΣ∇∂])\s+(?=\w)", r"\1", t)
    # innermost-first so nesting works
    for _ in range(8):
        before = t
        t = re.sub(r"\\d?frac" + _GROUP + _GROUP, lambda m: _frac(m.group(1), m.group(2)), t)
        t = re.sub(r"\\sqrt\[(\d+)\]" + _GROUP, lambda m: ("∛" if m.group(1) == "3" else "∜" if m.group(1) == "4" else m.group(1) + "√") + _wrap(m.group(2)), t)
        t = re.sub(r"\\sqrt" + _GROUP, lambda m: "√" + _wrap(m.group(1)), t)
        t = re.sub(r"\^" + _GROUP, _sup, t)
        t = re.sub(r"_" + _GROUP, _sub, t)
        if t == before:
            break
    t = re.sub(r"\\sqrt\s*(\w)", r"√\1", t)
    t = re.sub(r"\^(\d)", lambda m: m.group(1).translate(_SUP), t)
    t = re.sub(r"\^([a-z])\b", lambda m: m.group(1).translate(_SUP), t)
    t = re.sub(r"(?<=[A-Za-z\)∫∑∏])_(\d)", lambda m: m.group(1).translate(_SUB), t)
    for f in _FUNCS:
        t = t.replace("\\" + f, f)
    t = t.replace("\\%", "%").replace("\\_", "_").replace("\\&", "&").replace("\\{", "{").replace("\\}", "}")
    t = re.sub(r"\\([A-Za-z]+)", r"\1", t)  # unknown command -> just its name
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" ([.,;:])", r"\1", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _wrap(s):
    s = s.strip()
    return s if re.fullmatch(r"[\w.√°⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ₀-₉Δ]+", s) else "(" + s + ")"


def _frac(a, b):
    return f" {_wrap(a)}/{_wrap(b)} "
