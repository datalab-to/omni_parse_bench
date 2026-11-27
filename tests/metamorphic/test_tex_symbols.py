"""Relations of LaTeX symbols in the text view (M190, M191), and of math nested too deeply to render (M192,
M193)."""
from __future__ import annotations

import subprocess
import sys

from hypothesis import example, given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, passes, relation
from omni_parse_bench import equations, texsymbols
from omni_parse_bench.scorers.unit_tests import runners

COMMANDS = sorted(texsymbols.SYMBOLS)
WRAPPERS = ["${}$", "$${}$$", "\\({}\\)", "\\[{}\\]"]


def gold(text: str):
    return runners.Present(runners.Text(text, 0))


@relation(HOLDS, domain=f"{len(COMMANDS)} commands x 4 delimiters x 3 operands")
@example(command="neg", wrapper="${}$", operand="p")
@given(st.sampled_from(COMMANDS), st.sampled_from(WRAPPERS), st.sampled_from(["p", "xy", "A"]))
def test_a_symbol_in_latex_and_its_character_are_the_same_to_a_text_test(command, wrapper, operand):
    """A symbol written as a LaTeX command in math (`$\\neg p$`) and as its character (`¬p`) are the same to a
    `present` text test, in either direction, in `$`, `$$`, `\\(` and `\\[` math; the symbol left out, and
    another symbol, still fail. [M190]
    Why it matters for a score: a model that writes a symbol as LaTeX must not fail a gold that has the
    character, nor the other way round; a negation left out of a page is not a faithful reading."""
    # Given a symbol between two operands, written as LaTeX and as its character
    char = texsymbols.SYMBOLS[command]
    latex, written = f"{operand} \\{command} {operand}", f"{operand}{char}{operand}"
    # When a text test with one form as its gold reads a page with the other form; Then it passes
    assert passes(gold(written), f"<p>{wrapper.replace('{}', latex)}</p>")
    assert passes(gold(f"${latex}$"), f"<p>{written}</p>")
    # And it fails when the symbol is left out, or is another one (so the relation is not vacuous)
    assert not passes(gold(written), f"<p>{operand}{operand}</p>")
    other = f"{operand} \\partial {operand}"
    assert not passes(gold(written), f"<p>{wrapper.replace('{}', other)}</p>")


@relation(HOLDS, domain="5 text commands x 4 delimiters x 3 words")
@given(st.sampled_from(list(texsymbols.TEXT)), st.sampled_from(WRAPPERS),
       st.sampled_from(["if", "and", "then"]))
def test_text_in_math_reads_as_text_whatever_the_command(command, wrapper, word):
    """Words in `\\mbox`, `\\texttt`, `\\textsf`, `\\textmd` and `\\textup` in math read as `\\text`
    reads them, in all four delimiters: a text test for the words passes, and fails on a page without
    them. [M191]
    Why it matters for a score: the words are printed on the page; reading them as nothing fails a page
    that kept them."""
    # Given math holding a word in a text command, and the same in \text
    target = f"x{word} y"
    body = f"x \\{command}{{{word} }} y"
    page = f"<p>{wrapper.replace('{}', body)}</p>"
    same = f"<p>{wrapper.replace('{}', body.replace(command, 'text'))}</p>"
    # When a text test for the words reads each; Then both pass
    assert passes(gold(target), same)
    assert passes(gold(target), page)
    # And it fails on a page that dropped the word
    assert not passes(gold(target), "<p>x y</p>")


SPANS = [
    "'$' + r'\\dots ' * 15000 + '$'", "'$$' + r'\\dots\\dots' * 5000 + '$$'",
    "'$' + '{' * 3000 + 'x' + '}' * 3000 + '$'", "r'$\\frac{1}{' * 500 + 'x' + '}$' * 500",
    "'$' + r'\\sqrt' * 3000 + ' x$'", "'$' + r'\\left(' * 3000 + 'x' + r'\\right)' * 3000 + '$'"]


@relation(HOLDS, domain=f"{len(SPANS)} pathological spans, each read in its own process")
@given(st.sampled_from(SPANS))
@example(span=SPANS[0])
def test_math_too_deeply_nested_to_read_fails_that_span_and_nothing_else(span):
    """A math span that nests deeper than the bound (a looping `\\dots`, thousands of braces, `\\frac`,
    `\\sqrt` or `\\left`) neither kills the process nor changes the verdict on the rest of its page: an
    equation test and a text test in their own process return, the span reads as no math, and the page's
    other math still counts. [M192]
    Why it matters for a score: an output that loops must lose that span, not crash the whole run."""
    # Given a page of an ordinary equation, then a pathological span
    code = (f"from omni_parse_bench import equations\n"
            f"html = '<p>$x^2 + y$</p><p>' + {span} + '</p>'\n"
            "print(equations.appears('x^2 + y', html), equations.in_text('x^2 + y', html), "
            "equations.appears('a + b', html)[0])\n")
    # When a process reads it; Then it ends normally, the page's equation is found, a missing one is not
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, (out.returncode, out.stderr[-300:])
    assert out.stdout.strip() == "(True, '') True False", out.stdout


@relation(HOLDS, domain="nesting 1 to 70 of braces, \\left and \\frac")
@given(st.integers(1, 70), st.sampled_from(["brace", "left", "frac"]))
def test_nesting_up_to_the_bound_renders_and_past_it_does_not(depth, shape):
    """Math nested up to `equations.MAX_NESTING` levels renders, and past it does not: the same input gives
    the same verdict every time, whatever the machine's stack. [M193]
    Why it matters for a score: the bound is a documented rule, not an accident of a thread's stack."""
    # Given x nested `depth` levels in one of three shapes
    tex = {"brace": "{" * depth + "x" + "}" * depth, "left": "\\left(" * depth + "x" + "\\right)" * depth,
           "frac": "\\frac{1}{" * depth + "x" + "}" * depth}[shape]
    # When KaTeX reads it; Then it renders exactly when the depth is within the bound
    assert (equations.symbols(tex) is not None) == (depth <= equations.MAX_NESTING)
