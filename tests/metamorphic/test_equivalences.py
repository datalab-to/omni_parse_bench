"""Relations of the equivalences the scorer folds: spellings of one equation (M76 to M79), a raised decimal
point (M80 to M82) and a script written as maths or as markup (M83 to M87), each with both directions:
spellings that render alike keep every verdict, and spellings that do not stay apart. The equation test
grades the rendered symbols (`equations.symbols`), so two spellings of one symbol are one answer, and two
symbols that look alike but are not the same stay two. Each relation below checks a fold both ways: an
equivalence is tried with the gold in each spelling against the page in each other spelling, and a
distinction fails in both orders."""

from __future__ import annotations

import re
import string

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from test_properties import TESTS

from metamorphic.common import HOLDS, escaped, every_real_test, passes, relation
from omni_parse_bench.normalize import fold
from omni_parse_bench.scorers.unit_tests import runners

# ----------------------------------------------------------------------------------------- equations


def latex(tex: str, page_tex: str, display: bool = False) -> bool:
    """Whether the equation test for `tex` passes on a page that writes `page_tex` as maths."""
    wrapped = f"$${escaped(page_tex)}$$" if display else f"${escaped(page_tex)}$"
    return passes(runners.Present(runners.Latex(tex)), f"<p>{wrapped}</p>")


# One entry per fold: the spellings that render as one answer (a display one needs `$$`).
EQUIVALENT: dict[str, tuple[list[str], bool]] = {
    "transpose": (
        [r"A^\top", "A^T", r"A^\intercal", r"A^{\top}", "A^{T}", r"A^{\mathsf T}", r"A^{\mathrm{T}}"],
        False,
    ),
    "transpose in an exponent": ([r"A^{-T}", r"A^{-\top}", r"A^{-\intercal}"], False),
    "transposes and indices": ([r"(AB)^\top = B^\top A^\top + C_i^\top", "(AB)^T = B^T A^T + C_i^T"], False),
    "double bars": (["||x||", r"\|x\|", r"\lVert x\rVert", "‖x‖"], False),
    "adjacent bars": (["|a||b|", r"\lvert a\rvert\lvert b\rvert"], False),
    "double brackets": (r"W\llbracket z\rrbracket|W[[z]]|W[\![z]\!]|W⟦z⟧".split("|"), False),
    "bar": ([r"\bar{x}", r"\overline{x}"], False),
    "vector arrow": ([r"\vec{x}", r"\overrightarrow{x}"], False),
    "long right arrow": (["→", "⟶", r"\rightarrow", r"\longrightarrow"], False),
    "long maps-to arrow": (["↦", "⟼", r"\mapsto", r"\longmapsto"], False),
    "long left arrow": (["←", "⟵", r"\leftarrow", r"\longleftarrow"], False),
    "long right double arrow": (["⇒", "⟹", r"\Rightarrow", r"\Longrightarrow"], False),
    "long left double arrow": (["⇐", "⟸", r"\Leftarrow", r"\Longleftarrow"], False),
    "long double arrow": (["⇔", "⟺", r"\Leftrightarrow", r"\Longleftrightarrow"], False),
    "long two-way arrow": (["↔", "⟷", r"\leftrightarrow", r"\longleftrightarrow"], False),
    "union with a limit": (["∪_i", "⋃_i", r"\cup_i", r"\bigcup_i"], False),
    "intersection with a limit": (["∩_i", "⋂_i", r"\cap_i", r"\bigcap_i"], False),
    "direct sum with a limit": (["⊕_i", "⨁_i", r"\oplus_i", r"\bigoplus_i"], False),
    "tensor product with a limit": (["⊗_i", "⨂_i", r"\otimes_i", r"\bigotimes_i"], False),
    "circled dot with a limit": (["⊙_i", "⨀_i", r"\odot_i", r"\bigodot_i"], False),
    "or with a limit": (["∨_i", "⋁_i", r"\vee_i", r"\bigvee_i"], False),
    "and with a limit": (["∧_i", "⋀_i", r"\wedge_i", r"\bigwedge_i"], False),
    "square union with a limit": (["⊔_i", "⨆_i", r"\sqcup_i", r"\bigsqcup_i"], False),
    "sum with a relation in its limit": (
        [r"\Sigma_{i=1}^n", r"\sum_{i=1}^n", "∑_{i=1}^n", "Σ_{i=1}^n"],
        False,
    ),
    "product with a relation in its limit": (
        [r"\Pi_{i=1}^n", r"\prod_{i=1}^n", "∏_{i=1}^n", "Π_{i=1}^n"],
        False,
    ),
    "sum over a non-member": (
        [r"\sum_{i\not\in S}x_i", r"\sum_{i\notin S}x_i", r"\Sigma_{i\not\in S}x_i"],
        False,
    ),
    "left triangle": (["⊲", "◃"], False),
    "right triangle": (["⊳", "▹"], False),
    "proper subset": (["⊊", "⫋"], False),
    "proper superset": (["⊋", "⫌"], False),
    "subset or equal": (["⊆", "⫅"], False),
    "superset or equal": (["⊇", "⫆"], False),
    "divides": ([r"a\mid b", r"a\vert b"], False),
    "degrees": ([r"30^\circ", "30°"], False),
    "angle fences": ([r"\left<x\right>", r"\bigl<x\bigr>", r"\langle x\rangle", "〈x〉", "⟨x⟩"], False),
    "blackboard R": ([r"\mathbb{R}", "ℝ", r"\mathds{R}"], False),
    "blackboard N": ([r"\mathbb{N}", "ℕ"], False),
    "blackboard one": ([r"\mathbb{1}", "𝟙"], False),
    "fraktur g": ([r"\mathfrak{g}", "𝔤"], False),
    "Unicode maths letters": (["x", "𝑥", "𝐱"], False),
    "prime": (["x'", "x′", r"x^\prime"], False),
    "double prime": (["x''", "x″"], False),
    "triple prime": (["x'''", "x‴"], False),
    "rho": ([r"\rho", "ϱ"], False),
    "pi": ([r"\pi", "ϖ"], False),
    "kappa": ([r"\kappa", "ϰ"], False),
    "double integral": ([r"\iint f", r"\int\!\int f"], False),
    "triple integral": ([r"\iiint f", r"\int\int\int f"], False),
    "empty superscript": (["x", "x^{}", "x_{}"], False),
    "empty script before a script": ([r"x_{}^2", "x^2"], False),
    "text in a box": ([r"\mbox{hi}", r"\text{hi}"], False),
    "top-level row break": ([r"a=b\\c=d", r"\begin{aligned}a&=b\\c&=d\end{aligned}"], True),
    "raw percent": ([r"5\%+3", "5%+\n3"], True),
}

# Where the fold sits in an equation: alone, after a term, before a relation, inside a call.
CONTEXTS = ["@", "z + @", "@ = 0", "f(@) + 1"]


def in_context(context: str, spelling: str) -> str:
    return context.replace("@", spelling)


@relation(HOLDS, domain=f"{len(EQUIVALENT)} folds, each spelling as the gold and as the page, 4 contexts")
@pytest.mark.parametrize("fold", list(EQUIVALENT))
def test_equation_spellings_that_render_alike_pass_each_others_tests(fold):
    """For each of 50 folds of the equation test (transposes, double bars and brackets, bars and arrows over a
    symbol, long arrows, binary and big operators with limits, Σ and Π with a relation in the lower limit,
    triangles, subsets, angle fences, Unicode letters and primes, Greek variants, double integrals, top-level
    row breaks, empty scripts, a raw percent), a test written with any spelling passes on a page written with
    any other, alone and inside a term, a relation or a call. [M76]
    Why it matters for a score: a system is graded on the equation it printed, not on which of the encodings
    that draw the same symbols it chose."""
    # Given the spellings of one fold; When each is the gold and each other the page, in four contexts
    spellings, display = EQUIVALENT[fold]
    for context in CONTEXTS if not display else ["@"]:
        for gold in spellings:
            for written in spellings:
                # Then the test passes
                assert latex(in_context(context, gold), in_context(context, written), display), (
                    fold,
                    context,
                    gold,
                    written,
                )


# Spellings that look alike but are different symbols, or a different reading: each pair must stay apart.
DISTINCT: list[tuple[str, str]] = [
    (r"A^\top", r"A^{\mathbb{T}}"),
    (r"A^\top", r"A^{\mathcal{T}}"),
    (r"A^\top", r"A^{\mathfrak{T}}"),
    (r"A^{T_1}", r"A^{\top_1}"),
    (r"A^{x_T}", r"A^{x_\top}"),
    (r"\top \land p", r"T \land p"),
    (r"A^{\mathbb{T}x}", r"A^{Tx}"),
    (r"T+x", r"\top+x"),
    ("[[x,y],z]", "[x,[y,z]]"),
    (r"\llbracket x,y\rrbracket", "[[x,y],z]"),
    (r"\bar{x}", r"\overline{xy}"),
    (r"\bar{xy}", r"\overline{xy}"),
    (r"\vec{xy}", r"\overrightarrow{xy}"),
    (r"\vec{1}", r"\overrightarrow{1}"),
    (r"A\cup B", r"A\bigcup B"),
    (r"A\cap B", r"A\bigcap B"),
    (r"A\oplus B", r"A\bigoplus B"),
    (r"A\otimes B", r"A\bigotimes B"),
    ("a∪b", "a⋃b"),
    ("a⊕b", "a⨁b"),
    (r"\Sigma_i", r"\sum_i"),
    (r"\Sigma_{xy}", r"\sum_{xy}"),
    (r"\Pi(x)", r"\prod(x)"),
    (r"\Sigma^{-1}\mu", r"\sum^{-1}\mu"),
    (r"\mathcal{A}", "A"),
    (r"\mathbb{A}", "A"),
    (r"\mathfrak{A}", "A"),
    ("v", "υ"),
    ("w", "ω"),
    ("a", "α"),
    ("ı", "ι"),
    ("ε", "∈"),
    ("=", "≡"),
    ("1", "𝟙"),
    ("Δ", "△"),
    (r"\langle x,y\rangle", "<x,y>"),
    ("ℓ", "l"),
    ("·", "•"),
    ("⊴", "⊵"),
    (r"a\cdot b", r"a\bullet b"),
    (r"\check{x}", r"\breve{x}"),
    ("⊲", "⊳"),
    ("⊊", "⊆"),
    (r"x^2", r"x_2"),
    (r"x^3", r"x^2"),
    ("x'", "x''"),
]
# Pairs where the test for the first must fail on the second, but not the other way: the second holds the
# first as a part (`[z,w]` is a nested sub-expression of `[[z,w]]`), and a test passes on a part of a page.
DISTINCT_ONE_WAY: list[tuple[str, str]] = [
    ("[[z,w]]", "[z,w]"),
    ("30°", "30"),
    (r"\iint f", r"\int f"),
    ("x''", "x'"),
]


@relation(
    HOLDS,
    domain=f"{len(DISTINCT)} pairs of look-alike symbols in both orders and {len(DISTINCT_ONE_WAY)} in "
    "one order, 2 contexts",
)
@pytest.mark.parametrize(
    "pair", [*DISTINCT, *DISTINCT_ONE_WAY], ids=[f"{a}|{b}" for a, b in [*DISTINCT, *DISTINCT_ONE_WAY]]
)
def test_equation_spellings_that_render_differently_fail_each_others_tests(pair):
    """A test for one of two look-alike but different spellings fails on a page that writes the other, in
    both orders and in two contexts: a script, blackboard or fraktur T for a transpose; one bracket for
    two; a bar over two symbols for one; a binary operator for a big one; Σ or Π as a variable for a sum
    or product; Greek and Latin letters, a dot and a bullet, a left and a right triangle, one prime for
    two. [M77]
    Why it matters for a score: the folds that join look-alike spellings must not join two answers a
    reader tells apart, or a page with the wrong symbol would pass. (Where one page holds the other as a
    part, as `[[z,w]]` holds `[z,w]`, only the longer test must fail on the shorter page.)"""
    left, right = pair
    # Given two spellings of different symbols; When each is the gold and the other the page, in 2 contexts
    orders = ((left, right), (right, left)) if pair in DISTINCT else ((left, right),)
    for context in ("@", "z + @"):
        for gold, written in orders:
            # Then the test fails
            assert not latex(in_context(context, gold), in_context(context, written)), (
                context,
                gold,
                written,
            )


def _rewrite(pattern: str, repl: str):
    """A rewrite of a gold equation: `pattern` replaced by `repl`, None when nothing matches."""
    rx = re.compile(pattern)

    def apply(tex: str) -> str | None:
        out = rx.sub(repl, tex)
        return out if out != tex else None

    return apply


def _all(*rewrites):
    def apply(tex: str) -> str | None:
        out = tex
        for r in rewrites:
            out = r(out) or out
        return out if out != tex else None

    return apply


def _empty_script(tex: str) -> str | None:
    """`tex` with an empty subscript after its last symbol, when that symbol carries no script already."""
    last = re.search(r"(?:\\[A-Za-z]+|[A-Za-z0-9])$", tex)
    if not last or "%" in tex or (last.start() and tex[last.start() - 1] in "_^{"):
        return None
    return tex + "_{}"


def _limit(tex: str, at: int) -> str:
    """The lower limit after the operator that ends at `at`: a balanced `{..}`, one character or a command."""
    if tex[at : at + 1] != "_":
        return ""
    at += 1
    if tex[at : at + 1] != "{":
        return re.match(r"\\[A-Za-z]+|.", tex[at:])[0] if tex[at:] else ""
    depth = 0
    for i in range(at, len(tex)):
        depth += {"{": 1, "}": -1}.get(tex[i], 0)
        if depth == 0:
            return tex[at : i + 1]
    return tex[at:]


def _big(command: str, target: str, with_relation: bool):
    r"""A rewrite of `\sum` or `\prod` to Σ or Π: only the operators whose lower limit holds a relation of the
    scorer's list (`with_relation`), or only those whose limit holds none (nor any other relation sign)."""

    def apply(tex: str) -> str | None:
        out, last = [], 0
        for m in re.finditer(rf"\\{command}(?![A-Za-z])", tex):
            limit = _limit(tex, m.end())
            has = bool(re.search(RELATION, limit))
            other = bool(re.search(OTHER_RELATION, limit)) or tex.startswith("\\limits", m.end())
            if has if with_relation else not (has or other):
                out += [tex[last : m.start()], target]
                last = m.end()
        out.append(tex[last:])
        return "".join(out) if last else None

    return apply


NOT_A_LETTER = r"(?![A-Za-z])"
# Not after a delimiter size (`\left\langle` is `\left<`, and `\left‖` is not TeX), nor inside a comment.
NOT_SIZED = "".join(
    f"(?<!\\\\{w}{gap})"
    for gap in ("", " ")
    for w in ("left", "right", "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "big", "Big", "bigg", "Bigg")
)
# The relations the scorer reads in a sum's or product's lower limit to make Σ and ∑ one symbol:
# `=`, `\neq`, `\in`, `\notin`, `\not\in`, `\leq`, `\geq` (docs/scoring/present-latex.md).
RELATION = r"(?:=|\\(?:neq|ne|in|notin|not|leq|le|geq|ge)(?![A-Za-z]))"
# Not a relation to the scorer, but one to a reader (`<`, `\sim`, `\subset`): left out of the rewrites that
# turn a sum with no relation into Σ, since the verdict there is the scorer's to give.
OTHER_RELATION = (
    r"(?:<|>|\\(?:sim|subset|supset|approx|equiv|to|mid|perp|prec|succ|simeq|cong|propto|l|g|sub|sup)"
    r"(?![A-Za-z]))"
)
# Note: the rewrites below
EQUIVALENT_REWRITES = {
    "a transpose T as \\top": _rewrite(r"\^(?:T|\{T\})(?![A-Za-z0-9_\\{^])", r"^{\\top}"),
    "a transpose \\top as T": _rewrite(r"\^(?:\\top|\{\\top\})(?![A-Za-z0-9_\\{^])", "^{T}"),
    "a transpose as \\intercal": _rewrite(r"\^(?:\\top|\{\\top\})(?![A-Za-z0-9_\\{^])", r"^{\\intercal}"),
    "a double bar as ‖": _rewrite(NOT_SIZED + r"\\\|", "‖"),
    "double brackets as ⟦ ⟧": _all(_rewrite(r"\\llbracket", "⟦"), _rewrite(r"\\rrbracket", "⟧")),
    "\\bar over one symbol as \\overline": _rewrite(r"\\bar\{([A-Za-z0-9])\}", r"\\overline{\1}"),
    "\\overline over one symbol as \\bar": _rewrite(r"\\overline\{([A-Za-z0-9])\}", r"\\bar{\1}"),
    "\\vec over one symbol as \\overrightarrow": _rewrite(r"\\vec\{([A-Za-z0-9])\}", r"\\overrightarrow{\1}"),
    "a long arrow as a short one": _rewrite(
        r"\\long(rightarrow|mapsto|leftarrow|leftrightarrow)" + NOT_A_LETTER, r"\\\1"
    ),
    "a short arrow as a long one": _rewrite(
        r"\\(rightarrow|mapsto|leftarrow|leftrightarrow)" + NOT_A_LETTER, r"\\long\1"
    ),
    "a big operator with a limit as binary": _rewrite(
        r"\\big(cup|cap|oplus|otimes|odot|vee|wedge|sqcup)(?=_)", r"\\\1"
    ),
    "a binary operator with a limit as big": _rewrite(
        r"\\(cup|cap|oplus|otimes|odot|vee|wedge|sqcup)(?=_)", r"\\big\1"
    ),
    "a sum with a relation as Σ": _big("sum", "\\Sigma", True),
    "a product with a relation as Π": _big("prod", "\\Pi", True),
    "\\not\\in as \\notin": _rewrite(r"\\not\\in" + NOT_A_LETTER, r"\\notin"),
    "\\triangleleft as ⊲": _rewrite(r"\\triangleleft" + NOT_A_LETTER, "⊲"),
    "\\subsetneq as ⊊": _rewrite(r"\\subsetneq(?![A-Za-z])", "⊊"),
    "\\supsetneq as ⊋": _rewrite(r"\\supsetneq(?![A-Za-z])", "⊋"),
    "\\subseteq as ⊆": _rewrite(r"\\subseteq(?![A-Za-z])", "⊆"),
    "\\supseteq as ⊇": _rewrite(r"\\supseteq(?![A-Za-z])", "⊇"),
    "\\left< \\right> as \\langle \\rangle": _all(
        _rewrite(r"\\left<", r"\\langle "), _rewrite(r"\\right>", r"\\rangle ")
    ),
    "\\mathbb as a letter": _rewrite(r"\\mathbb\{R\}", "ℝ"),
    "\\mathfrak{g} as 𝔤": _rewrite(r"\\mathfrak\{g\}", "𝔤"),
    "an apostrophe as a prime": _rewrite(r"(?<=[A-Za-z0-9])'(?![A-Za-z'_^])", "′"),
    "\\rho as ϱ": _rewrite(r"\\rho" + NOT_A_LETTER, "ϱ"),
    "\\pi as ϖ": _rewrite(r"\\pi" + NOT_A_LETTER, "ϖ"),
    "\\kappa as ϰ": _rewrite(r"\\kappa" + NOT_A_LETTER, "ϰ"),
    "\\iint as two integrals": _rewrite(r"\\iint" + NOT_A_LETTER, r"\\int\\!\\int "),
    "\\mbox as \\text": _rewrite(r"\\mbox\{", r"\\text{"),
    "\\mid as \\vert": _rewrite(r"\\mid" + NOT_A_LETTER, r"\\vert "),
    "an empty subscript added": lambda tex: _empty_script(tex),
}
# The rewrites that change the symbols, and so must fail the test.
DISTINCT_REWRITES = {
    "a transpose T as a blackboard T": _rewrite(r"\^(?:T|\{T\})(?![A-Za-z0-9_\\{^])", r"^{\\mathbb{T}}"),
    "a transpose T as a script T": _rewrite(r"\^(?:T|\{T\})(?![A-Za-z0-9_\\{^])", r"^{\\mathcal{T}}"),
    "a transpose \\top as a fraktur T": _rewrite(
        r"\^(?:\\top|\{\\top\})(?![A-Za-z0-9_\\{^])", r"^{\\mathfrak{T}}"
    ),
    "\\bar over two symbols as \\overline": _rewrite(r"\\bar\{([A-Za-z0-9]{2,})\}", r"\\overline{\1}"),
    "\\overline over two symbols as \\bar": _rewrite(r"\\overline\{([A-Za-z0-9]{2,})\}", r"\\bar{\1}"),
    "\\cup with no limit as \\bigcup": _rewrite(r"\\cup(?![A-Za-z_])", r"\\bigcup"),
    "\\cap with no limit as \\bigcap": _rewrite(r"\\cap(?![A-Za-z_])", r"\\bigcap"),
    "\\bigcup with no limit as \\cup": _rewrite(r"\\bigcup(?![A-Za-z_])", r"\\cup"),
    "\\sum with no relation as Σ": _big("sum", "\\Sigma", False),
    "a blackboard letter as a plain one": _rewrite(r"\\mathbb\{([A-Z])\}", r"\1"),
    "a script letter as a plain one": _rewrite(r"\\mathcal\{([A-Z])\}", r"\1"),
    "a fraktur letter as a plain one": _rewrite(r"\\mathfrak\{([a-zA-Z])\}", r"\1"),
    "\\alpha as a": _rewrite(r"\\alpha" + NOT_A_LETTER, "a"),
    "\\ell as l": _rewrite(r"\\ell" + NOT_A_LETTER, "l"),
    "\\langle \\rangle as < >": _all(
        _rewrite(NOT_SIZED + r"\\langle" + NOT_A_LETTER, "<"),
        _rewrite(NOT_SIZED + r"\\rangle" + NOT_A_LETTER, ">"),
    ),
    "\\cdot as \\bullet": _rewrite(r"\\cdot" + NOT_A_LETTER, r"\\bullet"),
}
# One gold equation for each rewrite, so that a run on the fixtures (three equations) is not vacuous.
FIXED_LATEX = [
    r"A^T x + b",
    r"A^{\top} B",
    r"\|x\| + \|y\|",
    r"W\llbracket z \rrbracket",
    r"\bar{x} + \overline{y}",
    r"\vec{v} \cdot \vec{w}",
    r"f \longrightarrow g",
    r"x \mapsto y",
    r"\bigcup_{i} A_i",
    r"\cup_{i} A_i",
    r"\sum_{i=1}^{n} x_i",
    r"\prod_{i=1}^n a_i",
    r"\sum_{i \not\in S} x_i",
    r"a \triangleleft b",
    r"A \subsetneq B",
    r"A \supsetneq B",
    r"A \subseteq B",
    r"A \supseteq B",
    r"\left<x, y\right>",
    r"\mathbb{R}^n",
    r"\mathfrak{g} \otimes V",
    r"f'(x)",
    r"\rho + \pi + \kappa",
    r"\iint f \, dA",
    r"\mbox{hi} x",
    r"a \mid b",
    r"x_1 + y",
    r"A^{\mathcal{T}} + B",
    r"\bar{xy} + \overline{zw}",
    r"A \cup B \cap C",
    r"\sum x_i + \Sigma_y",
    r"\bigcup A",
    r"\mathbb{N} \to \mathcal{A}",
    r"\alpha \ell",
    r"\langle x, y \rangle \cdot z",
]
LATEX = [
    t for t in TESTS if isinstance(t.params, runners.Present) and isinstance(t.params.content, runners.Latex)
]


def _skipped(tex: str) -> bool:
    """A gold the rewrites leave alone: a TeX comment (`%`) hides what follows it, so a symbol after one is
    not on the page."""
    return "%" in tex


def _applies(rewrites: dict, expect: bool):
    """Runs every rewrite on the loaded equations and on FIXED_LATEX, in both directions (the gold rewritten,
    the page rewritten); returns how many rewrites ran and the failures."""
    ran, bad = 0, []
    golds = [(t.id, t.params.content.latex) for t in LATEX] + [
        (f"fixed {i}", g) for i, g in enumerate(FIXED_LATEX)
    ]
    for name, rewrite in rewrites.items():
        for tid, tex in golds:
            alt = None if _skipped(tex) else rewrite(tex)
            if alt is None:
                continue
            ran += 1
            original = runners.Present(runners.Latex(tex))
            both = (
                passes(runners.Present(runners.Latex(alt)), f"<p>$${escaped(tex)}$$</p>"),
                passes(original, f"<p>$${escaped(alt)}$$</p>"),
            )
            if both != (expect, expect):
                bad.append((name, tid, tex[:60], alt[:60], both))
    return ran, bad


def _fixed_cover(rewrites: dict) -> int:
    """How many of the rewrites apply to some equation of FIXED_LATEX (every one should)."""
    return sum(any(rw(g) is not None for g in FIXED_LATEX) for rw in rewrites.values())


@relation(
    HOLDS,
    domain=f"{len(EQUIVALENT_REWRITES)} rewrites on every loaded equation and {len(FIXED_LATEX)} fixed ones",
    pool="latex",
)
def test_rewriting_an_equation_into_an_equivalent_spelling_keeps_its_verdict():
    r"""Each rewrite that keeps the rendered symbols (a transpose, a norm bar, double brackets, a bar or
    vector arrow over one symbol, a long arrow, a binary or big operator with limits, Σ or Π over a
    relation, a triangle, a subset, an angle fence, a blackboard or fraktur letter, a prime, a Greek
    variant, a double integral, `\mbox`, `\mid`, an empty script), applied to a loaded equation test's
    gold or to the page that writes its answer, leaves the test passing. [M78]
    Why it matters for a score: the real equations of the dataset are written in one spelling, and a
    system that writes the other must be graded the same."""
    # Given each loaded equation test (the gold, and the page that holds exactly its answer), and each rewrite
    ran, bad = _applies(EQUIVALENT_REWRITES, True)
    # When the rewrite changes the gold or the page; Then the test still passes in both
    assert not bad, bad[:5]
    assert ran >= _fixed_cover(EQUIVALENT_REWRITES) and _fixed_cover(EQUIVALENT_REWRITES) == len(
        EQUIVALENT_REWRITES
    ), "every rewrite applies to some fixed equation"


@relation(
    HOLDS,
    domain=f"{len(DISTINCT_REWRITES)} rewrites on every loaded equation and {len(FIXED_LATEX)} fixed ones",
    pool="latex",
)
def test_rewriting_an_equation_into_a_different_symbol_fails_its_test():
    """Each rewrite that changes the rendered symbols (a transpose into a blackboard, script or fraktur T, a
    bar over two symbols into a long overline, a binary operator into a big one with no limit, a Σ for a
    sum with no relation, a blackboard, script or fraktur letter into a plain one, α into a, ℓ into l,
    angle fences into signs, a dot into a bullet), applied to a loaded equation test's gold or to the page
    that writes its answer, makes the test fail. [M79]
    Why it matters for a score: it is the other half of M78: a fold that joined these would pass a page
    with the wrong symbol."""
    # Given each loaded equation test, and each rewrite that changes a symbol
    ran, bad = _applies(DISTINCT_REWRITES, False)
    # When the rewrite changes the gold or the page; Then the test fails in both
    assert not bad, bad[:5]
    assert _fixed_cover(DISTINCT_REWRITES) == len(DISTINCT_REWRITES), (
        "every rewrite applies to some fixed equation"
    )
    assert ran


# ------------------------------------------------------------------------------------ raised decimals

# What may stand before a leading raised decimal: the start, a space, an opening bracket, a sign, a currency
# symbol, a relation or an operator, a quote. After a letter, a digit or a closing bracket the dot separates.
BEFORE_A_DECIMAL = [
    "",
    " ",
    "(",
    "[",
    "{",
    "+",
    "-",
    "−",
    "±",
    "$",
    "£",
    "€",
    "¥",
    "<",
    "=",
    "≈",
    "~",
    "×",
    "/",
    ":",
    '"',
    "%",
    "p<",
    "r=",
    " p = ",
]
BEFORE_A_SEPARATOR = ["A", "(a)", "x)", "x]", "x}", "ab", "太原", "Ö", "Vol"]
DIGITS = st.text(string.digits, min_size=1, max_size=8)
SHOWN = st.text(string.ascii_lowercase, min_size=3, max_size=6)


def text_test(text: str):
    return runners.Present(runners.Text(text, 0))


@relation(HOLDS, domain=f"{len(BEFORE_A_DECIMAL)} openings x both orders, digits drawn by Hypothesis")
@example(opening="", digits="79", shown="word")
@given(st.sampled_from(BEFORE_A_DECIMAL), DIGITS, SHOWN)
def test_a_leading_raised_decimal_point_is_a_full_stop_in_either_order(opening, digits, shown):
    """A text test for a leading decimal written with a full stop (`.79`, `p<.05`, `(.5)`, `-.25`, `£.5`)
    passes on a page that writes it with a raised dot (`·`), and the other way round, after the start of
    the text, a space, an opening bracket, a sign, a currency symbol, a relation or an operator. [M80]
    Why it matters for a score: older scans print the point raised, and a gold or a model may write
    either."""
    # Given a leading decimal with an opening before it, in the gold with a full stop, in the page with a dot
    # (preceded by a word and a space, so the opening is not at the start of the text)
    for lead in ("", f"{shown} "):
        stop, raised = f"{lead}{opening}.{digits}", f"{lead}{opening}·{digits}"
        # When each is the gold and the other the page; Then the test passes
        assert passes(text_test(stop), f"<p>{escaped(raised)}</p>"), (stop, raised)
        assert passes(text_test(raised), f"<p>{escaped(stop)}</p>"), (raised, stop)
        # And a text test with its own spelling passes (so the fold does not lose the digits)
        assert passes(text_test(raised), f"<p>{escaped(raised)}</p>")


@relation(
    HOLDS, domain=f"{len(BEFORE_A_SEPARATOR)} words and brackets x both orders, digits drawn by Hypothesis"
)
@example(before="A", digits="1")
@given(st.sampled_from(BEFORE_A_SEPARATOR), DIGITS)
def test_a_raised_dot_after_a_letter_or_a_closing_bracket_is_not_a_decimal_point(before, digits):
    """A text test for `A·1`, `(a)·1`, `x)·2`, `x]·2`, `x}·2`, `ab·5`, `太原·2020` fails on a page that writes
    the same with a full stop, and the other way round: after a letter, a digit-less word or a closing
    bracket the dot separates or multiplies, and is not a decimal point. [M81]
    Why it matters for a score: it is the other half of M80: `太原·2020` is a place and a year, not a
    number."""
    # Given a raised dot after a letter or a closing bracket; When the gold has the dot, the page a full stop
    raised, stop = f"{before}·{digits}", f"{before}.{digits}"
    # Then the test fails in both orders, and passes on its own spelling
    assert not passes(text_test(stop), f"<p>{escaped(raised)}</p>"), (stop, raised)
    assert not passes(text_test(raised), f"<p>{escaped(stop)}</p>"), (raised, stop)
    assert passes(text_test(raised), f"<p>{escaped(raised)}</p>")


@relation(HOLDS, domain="digits drawn by Hypothesis, 2 numbers x raised and full stop, 6 openings")
@example(whole="0", fraction="79", opening="")
@given(st.text(string.digits, min_size=1, max_size=4), DIGITS, st.sampled_from(["", " ", "(", "£", "p<"]))
def test_a_number_test_reads_a_raised_dot_like_a_full_stop(whole, fraction, opening):
    """A number test for `0.79` passes on a page that writes `0·79` and one for `79` has the same verdict on
    `·79` as on `.79`, after any opening a text test accepts. [M82]
    Why it matters for a score: the number tests read the page through the same fold, so a raised point is a
    decimal point there too."""
    # Given a number written with a decimal point and the pages that write the point raised and flat
    # When the tests run; Then the whole number passes on the raised page, and the digits alone agree
    n = runners.Present(runners.Number(f"{whole}.{fraction}"))
    assert passes(n, f"<p>{escaped(opening)}{whole}·{fraction}</p>")
    d = runners.Present(runners.Number(fraction))
    assert passes(d, f"<p>{escaped(opening)}·{fraction}</p>") == passes(
        d, f"<p>{escaped(opening)}.{fraction}</p>"
    )


@every_real_test("text strings")
def test_every_real_text_string_beside_a_leading_decimal_or_a_separator_dot_keeps_its_relation():
    """After each real text string, a raised dot and digits: a test for the string with a full stop passes on
    the page with a raised dot when the string ends in a space or an opening bracket, sign or operator,
    and fails when it ends in a letter, a digit or a closing bracket (and the other way round). [M80, M81]
    Why it matters for a score: it is M80 and M81 on the dataset's own strings, so the fold meets real
    text, not only generated words."""
    # Given every real text string, with its end classified
    n, bad = 0, []
    for t in TESTS:
        if not isinstance(t.params, runners.Present) or not isinstance(t.params.content, runners.Text):
            continue
        x = t.params.content.text
        # (a string with a dollar, a backslash or a tag would be read as maths or markup, not as text)
        if not x or re.search(r"[$\\<>&]", x) or x[-1] in "·∙.":
            continue
        n += 1
        # When a decimal with a raised dot follows the string; Then the relation holds, by its last character
        # a digit or a letter before it, the tail of a longer number (`3.` `·5`) and a space are other cases
        # (the character the dot meets, read through the fold: a trailing space or a run of underscores is
        # whitespace by then; the bar after x keeps it from being trimmed)
        shown = fold(x + "|")
        last = shown[-2:-1] if shown.endswith("|") else ""
        if not last:
            continue
        joined = last.isalnum() or last in ")]}"
        stop, raised = f"{x}.5", f"{x}·5"
        got = (
            passes(text_test(stop), f"<p>{escaped(raised)}</p>"),
            passes(text_test(raised), f"<p>{escaped(stop)}</p>"),
        )
        if last.isdigit():
            continue  # `3·5` is the number 3.5 either way (a digit before the dot)
        if got != ((not joined),) * 2:
            bad.append((x[-20:], got))
    assert n and not bad, f"{len(bad)}/{n} real strings: {bad[:6]}"


# ------------------------------------------------------------------------------------- maths scripts

BASES = ["V", "x", "LC", "T", "H", "W"]
WORDS = st.text(string.ascii_lowercase, min_size=3, max_size=7)
SCRIPT = st.text(string.digits, min_size=1, max_size=3)
# How an output writes a script in maths, by the mark: the base and the script.
MATHS = {
    "sub": [
        "${b}_{{{s}}}$",
        "\\({b}_{{{s}}}\\)",
        "$${b}_{{{s}}}$$",
        "\\[{b}_{{{s}}}\\]",
        "$\\mathrm{{{b}}}_{{{s}}}$",
        "$\\mathrm{{{b}_{{{s}}}}}$",
        "$\\text{{{b}}}_{{{s}}}$",
        "$ {b} _ {{{s}}} $",
    ],
    "sup": [
        "${b}^{{{s}}}$",
        "\\({b}^{{{s}}}\\)",
        "$${b}^{{{s}}}$$",
        "\\[{b}^{{{s}}}\\]",
        "$\\mathrm{{{b}}}^{{{s}}}$",
        "$\\mathrm{{{b}^{{{s}}}}}$",
        "$\\text{{{b}}}^{{{s}}}$",
        "$ {b} ^ {{{s}}} $",
    ],
}
MARKUP = {"sub": "{b}<sub>{s}</sub>", "sup": "{b}<sup>{s}</sup>"}
OTHER = {"sub": "sup", "sup": "sub"}


def format_test(before: str, span: str, after: str, marks=(), absent=()):
    return runners.Format(before, span, after, 0, tuple(marks), tuple(absent))


@relation(
    HOLDS,
    domain=f"{sum(len(v) for v in MATHS.values())} maths spellings x 6 bases, drawn scripts and words",
)
@example(words=("the volume ", " was"), base="V", script="1", kind="sub")
@given(
    st.tuples(WORDS.map(lambda w: w + " "), WORDS.map(lambda w: " " + w)),
    st.sampled_from(BASES),
    SCRIPT,
    st.sampled_from(["sub", "sup"]),
)
def test_a_script_written_in_maths_gets_the_verdicts_of_the_same_script_in_markup(words, base, script, kind):
    r"""A format test for a subscript or a superscript (`V` then `1` as `$V_1$`, `x^{2}`, `\(..\)`, `$$..$$`,
    `\[..\]`, a `\mathrm` or `\text` base, spaces around the operator) has on the maths page the verdict
    it has on the same text in `<sub>` or `<sup>`: pass for its own kind, fail for the other kind, and the
    same verdict for each negative test. [M83]
    Why it matters for a score: a system that writes an index as maths is as right as one that writes
    markup."""
    # Given words around a base and a script, written in maths and in markup
    before, after = words
    markup = f"<p>{before}{MARKUP[kind].format(b=base, s=script)}{after}</p>"
    tests = [
        format_test(before + base, script, after, marks=[kind]),
        format_test(before + base, script, after, marks=[OTHER[kind]]),
        format_test(before + base, script, after, absent=[kind]),
        format_test(before + base, script, after, absent=[OTHER[kind]]),
    ]
    expected = [passes(p, markup) for p in tests]
    assert expected == [True, False, False, True], expected
    for spelling in MATHS[kind]:
        # When the same script is written in maths; Then each test has the verdict it has on the markup
        page = f"<p>{before}{spelling.format(b=base, s=script)}{after}</p>"
        assert [passes(p, page) for p in tests] == expected, spelling


@relation(HOLDS, domain="3 fixed cases: a script with no base, a letter script, a symbol before the script")
@pytest.mark.parametrize(
    "maths, markup, before, span, after, kind",
    [
        ("word${}^{a}$ note", "word<sup>a</sup> note", "word", "a", " note", "sup"),
        ("$0.06^{a}$ m", "0.06<sup>a</sup> m", "0.06", "a", " m", "sup"),
        ("${}^{14}\\mathrm{C}$", "<sup>14</sup>C", "", "14", "C", "sup"),
        ("$E_{c}$ is", "E<sub>c</sub> is", "E", "c", " is", "sub"),
        (r"$\mathrm{H_2O}$", "H<sub>2</sub>O", "H", "2", "O", "sub"),
        (r"$1.5 \times 10^{-3}$ m", "1.5×10<sup>-3</sup> m", "1.5×10", "-3", " m", "sup"),
        (r"$\Delta T_c$", "ΔT<sub>c</sub>", "ΔT", "c", "", "sub"),
        (r"$\epsilon_r$ and", "ε<sub>r</sub> and", "ε", "r", " and", "sub"),
        (r"$\mu_0 x$", "μ<sub>0</sub>x", "μ", "0", "x", "sub"),
        (r"$\left( x^2 \right)$", "(x<sup>2</sup>)", "(x", "2", ")", "sup"),
    ],
)
def test_a_footnote_mark_an_isotope_or_a_symbol_script_in_maths_matches_its_markup(
    maths, markup, before, span, after, kind
):
    r"""A script after an empty base (`${}^{a}$`, `${}^{14}\mathrm{C}$`), inside a font group
    (`\mathrm{H_2O}`) or beside a symbol command (`\times`, `\Delta`, `\epsilon`, `\mu`, `\left(`) has the
    verdicts of the same text in markup, for the test of its kind and the negative test of its kind. [M84]
    Why it matters for a score: footnote marks, isotopes, chemical formulas and physical quantities are
    what format tests of scripts hold."""
    # Given the same text in maths and in markup; When the positive and the negative test run on both
    for p in (
        format_test(before, span, after, marks=[kind]),
        format_test(before, span, after, absent=[kind]),
        format_test(before, span, after, marks=[OTHER[kind]]),
    ):
        # Then the verdicts agree, and the positive one passes
        assert passes(p, f"<p>{escaped_maths(maths)}</p>") == passes(p, f"<p>{markup}</p>"), (maths, p)
    assert passes(format_test(before, span, after, marks=[kind]), f"<p>{escaped_maths(maths)}</p>")


def escaped_maths(s: str) -> str:
    """Maths as a page holds it: `<` and `&` escaped, so the page is the text."""
    return s.replace("&", "&amp;").replace("<", "&lt;")


KINDS_OF_MARK = ("bold", "italic", "underline", "strike")
V1 = ("the volume V", "1", " was")


@relation(
    HOLDS, domain="4 marks x 8 maths pages, positive and negative, and 6 distinctions of the script itself"
)
@pytest.mark.parametrize("kind", KINDS_OF_MARK)
def test_maths_never_satisfies_a_bold_italic_underline_or_strike_test(kind):
    r"""A bold, italic, underline or strikethrough test fails on a page whose only marks are scripts or fonts
    written in maths (`$V_1$`, `$\mathbf{V}_1$`, `$\mathit{1}$`, `\(V^{2}\)`), and the negative test for
    the mark fails there too, because a page whose only marks come from maths is a page with none. [M85]
    Why it matters for a score: maths is not bold or italic markup, and a plain-text system must not earn
    the negative tests of every mark by writing an index as maths."""
    # Given pages that write the span's script, a bold letter or an italic one in maths and nothing in markup
    pages = [
        "<p>the volume $V_1$ was</p>",
        "<p>the volume $\\mathbf{V}_1$ was</p>",
        "<p>the volume $\\mathit{V}_{1}$ was</p>",
        "<p>the volume \\(V_1\\) was</p>",
        "<p>the volume $$V_1$$ was</p>",
        "<p>the volume $V^{1}$ was</p>",
        "<p>the volume $\\mathrm{V}_1$ was</p>",
        "<p>the volume $\\textbf{V}_1$ was</p>",
    ]
    for page in pages:
        # When the positive test and the negative test of the mark run; Then both fail
        assert not passes(format_test(*V1, marks=[kind]), page), page
        assert not passes(format_test(*V1, absent=[kind]), page), page


@relation(
    HOLDS,
    domain="9 distinctions of the script: another index, a swapped script, a fraction, a root, code, a price",
)
@pytest.mark.parametrize(
    "page, marks, absent",
    [
        ("<p>the volume $V_2$ was</p>", ["sub"], []),
        ("<p>the volume $V_{12}$ was</p>", ["sub"], []),
        ("<p>the volume $V^1$ was</p>", ["sub"], []),
        ("<p>the volume $V_1$ was</p>", ["sup"], []),
        ("<p>the volume $\\frac{V}{2}_1$ was</p>", ["sub"], []),
        ("<p>the volume $\\sqrt{V}_1$ was</p>", ["sub"], []),
        ("<p>the volume $V_{1_2}$ was</p>", ["sub"], []),
        ("<p>the volume <code>$V_1$</code> was</p>", ["sub"], []),
        ("<p>the volume V1 was</p><pre>$a_2$</pre>", [], ["sub"]),
        ("<p>the volume $V_1$ was</p>", [], ["sub"]),
        ("<p>the volume $V^1$ was</p>", [], ["sup"]),
        ("<p>it cost $5 and then $6_1, so the volume V1 was</p>", ["sub"], []),
    ],
)
def test_a_script_that_is_not_the_span_or_not_a_script_does_not_pass_a_script_test(page, marks, absent):
    """A subscript test for span `1` fails on `$V_2$` and `$V_{12}$`, on a superscript, on a script after a
    fraction or a root or inside another script, on maths in `<code>`, and on a price; the superscript
    test fails on a subscript; the negative tests for `sub` or `sup` fail on a page that writes that
    script in maths, and a negative test fails on a page whose only maths is in code (a page with no
    marks). [M86]
    Why it matters for a score: it is the other half of M83 and M85: the fold of a script must not read a
    script that is not there, nor read the wrong one."""
    # Given a page that does not write the span as the mark the test asks for
    # When the test runs; Then it fails
    assert not passes(format_test(*V1, marks=marks, absent=absent), page), page


@relation(HOLDS, domain="3 pages: maths in code, in a pre block, and outside code beside it")
def test_maths_in_code_is_not_read_as_a_script_and_maths_beside_it_is():
    """A negative test for `sub` fails on a page whose only maths is in `<code>`, `<pre>` or `<kbd>` (no mark
    is on the page) and passes once the same maths stands outside code, where its script is a mark; a
    positive test for `sub` passes only on that page. [M87]
    Why it matters for a score: a shell variable in a listing is not a subscript, and a script printed as
    running text is one."""
    # Given a context with no script of its own, and maths with a script in code or beside the code
    negative, positive = (
        format_test("the volume V", "1", " was", absent=["sub"]),
        format_test("the volume V", "1", " was", marks=["sub"]),
    )
    for code in ("<code>$a_2$</code>", "<pre>$a_2$</pre>", "<kbd>\\(a_2\\)</kbd>"):
        assert not passes(negative, f"<p>the volume V1 was</p>{code}"), code
        # When the maths stands outside the code; Then it is a mark on the page, so the negative test can pass
        assert passes(negative, "<p>the volume V1 was</p><p>$a_2$</p>")
    assert not passes(positive, "<p>the volume <code>$V_1$</code> was</p>")
    assert passes(positive, "<p>the volume $V_1$ was</p>")


@every_real_test("text strings")
def test_every_real_text_string_as_the_base_of_a_script_in_maths_or_markup_gives_the_same_verdicts():
    """After each real text string, a script `2` written in maths (`$_{2}$`) or in markup (`<sub>2</sub>`)
    gets the same verdict from a subscript test, a superscript test and the negative test for each; and
    the script `2` after it is a subscript only as the string's own last letters before it. [M83]
    Why it matters for a score: it is M83 on the dataset's own contexts, so the reader of scripts meets
    real text, not only generated words."""
    # Given every real text string that can be a context (no dollar, tag, backslash or entity in it)
    n, bad = 0, []
    for t in TESTS:
        if not isinstance(t.params, runners.Present) or not isinstance(t.params.content, runners.Text):
            continue
        x = t.params.content.text
        if not x or re.search(r"[$\\<>&]", x) or not re.search(r"[A-Za-z]", x):
            continue
        before = x.strip()
        n += 1
        for kind, tag in (("sub", "_"), ("sup", "^")):
            maths, markup = (
                f"<p>{escaped(before)}${tag}{{2}}$</p>",
                f"<p>{escaped(before)}<{kind}>2</{kind}></p>",
            )
            for p in (
                format_test(before, "2", "", marks=[kind]),
                format_test(before, "2", "", marks=[OTHER[kind]]),
                format_test(before, "2", "", absent=[kind]),
                format_test(before, "2", "", absent=[OTHER[kind]]),
            ):
                if passes(p, maths) != passes(p, markup):
                    bad.append((before[-20:], kind, p.marks, p.absent))
    assert n and not bad, f"{len(bad)}/{n} real strings: {bad[:6]}"


@every_real_test("latex tests")
def test_every_real_equation_passes_on_its_answer_in_each_equivalent_spelling_and_fails_in_a_different_one():
    """Every real equation test passes on the page holding exactly its answer (the loaded equations of M78),
    and for each rewrite of M78 and M79 that applies to its gold, the rewritten gold passes on that page
    and the page rewritten passes the gold when the rewrite keeps the symbols and neither when it changes
    them; every rewrite applies to at least one real equation. [M78, M79]
    Why it matters for a score: M78 and M79 run on the fixtures in CI; this runs them on all the dataset's
    equations, so a fold cannot break a real answer."""
    # Given the real equation tests; When each rewrite is tried on each gold, in both directions
    for rewrites, expect in ((EQUIVALENT_REWRITES, True), (DISTINCT_REWRITES, False)):
        ran, bad = _applies(rewrites, expect)
        # Then the verdicts are as M78 and M79 say
        assert not bad, bad[:5]
        used = [name for name, rw in rewrites.items() if any(rw(t.params.content.latex) for t in LATEX)]
        assert ran and len(used) >= len(rewrites) // 2, (len(used), len(rewrites))
    for t in LATEX:
        assert passes(t.params, f"<p>$${escaped(t.params.content.latex)}$$</p>"), t.id
