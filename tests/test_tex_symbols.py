"""LaTeX symbols in the text view (`texsymbols`), and the bound on math too deeply nested to render."""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from omni_parse_bench import equations, normalize, texsymbols, views
from omni_parse_bench.scorers.unit_tests import runners


def passes(gold: str, page: str) -> bool:
    return runners.present(runners.Present(runners.Text(gold, 0)), views.html(page))[0]


def test_negation_in_latex_reads_as_the_negation_sign():
    # The case that found it: a gold "¬p" and a model that wrote the negation in LaTeX.
    assert normalize.fold(r"$\neg p$") == normalize.fold(r"$\lnot p$") == "¬p"
    assert passes("¬p", r"<p>$\neg p$</p>")
    assert passes(r"$\neg p$", "<p>¬p</p>")


def test_a_dropped_negation_is_not_the_proposition():
    assert not passes("¬p", "<p>p</p>")
    assert not passes("¬p", r"<p>$p \wedge q$</p>")


@pytest.mark.parametrize("command, char", sorted(texsymbols.SYMBOLS.items()))
def test_every_added_symbol_matches_its_character_both_ways(command, char):
    latex, written = rf"$a \{command} b$", f"a{char}b"
    assert normalize.fold(latex) == normalize.fold(written)
    assert passes(written, f"<p>{latex}</p>")
    assert passes(latex, f"<p>{written}</p>")


@pytest.mark.parametrize("command, other", [
    ("neg", r"\wedge"), ("land", r"\lor"), ("ne", r"\leq"), ("rarr", r"\larr"), ("iff", r"\implies"),
    ("empty", r"\in"), ("sub", r"\supe"), ("infin", r"\partial"),
])
def test_a_different_symbol_still_fails(command, other):
    assert not passes(rf"$a \{command} b$", rf"<p>$a {other} b$</p>")
    assert not passes(rf"$a {other} b$", rf"<p>$a \{command} b$</p>")


def test_the_table_replaces_pylatexenc_only_where_pylatexenc_is_wrong():
    # `\eth` is read as ƪ and `\backslash` as a bare backslash that the residue filter then deletes. Every
    # other command pylatexenc reads is left to it, so a gold in its character still matches.
    from pylatexenc import latex2text

    db = latex2text.get_default_latex_context_db()
    assert {k for k in texsymbols.SYMBOLS if db.get_macro_spec(k) is not None} == {"eth", "backslash"}


@pytest.mark.parametrize("command, char", sorted(texsymbols.SYMBOLS.items()))
def test_every_added_symbol_is_what_the_equation_test_renders(command, char):
    rendered = equations.symbols(rf"a \{command} b")
    assert rendered is not None and len(rendered) == 3, command
    assert normalize.fold(rendered[1]) == normalize.fold(char), (command, rendered[1], char)


@pytest.mark.parametrize("pylatexenc_char, katex_char", [
    ("⟺", "⇔"), ("⟷", "↔"), ("⌅", "⊼")])
def test_a_glyph_pylatexenc_writes_folds_with_the_one_katex_renders(pylatexenc_char, katex_char):
    assert normalize.fold(f"a{pylatexenc_char}b") == normalize.fold(f"a{katex_char}b")


@pytest.mark.parametrize("latex, gold", [(r"\Longleftrightarrow", "⟺"), (r"\Longleftrightarrow", "⇔"),
                                         (r"\blacktriangle", "▴"),
                                         (r"\barwedge", "⌅"), (r"\barwedge", "⊼"), (r"\blacksquare", "▪")])
def test_a_gold_in_either_glyph_of_these_commands_still_passes(latex, gold):
    assert passes(f"a{gold}b", rf"<p>$a {latex} b$</p>")


@pytest.mark.parametrize("command", texsymbols.TEXT)
def test_text_in_math_keeps_its_words(command):
    # As `\text` reads it: the space before a text group renders nothing, the one inside it does.
    assert normalize.fold(rf"$x \{command}{{if }} y$") == normalize.fold(r"$x \text{if } y$") == "xif y"
    assert passes("xif y", rf"<p>$x \{command}{{if }} y$</p>")
    assert not passes("x y", rf"<p>$x \{command}{{if }} y$</p>")


@pytest.mark.parametrize("latex, unicode", [(r"\leqslant", "≤"), (r"\geqslant", "≥"), (r"\leqq", "≤"),
                                            (r"\geqq", "≥"), (r"\subseteqq", "⊆"), (r"\supsetneqq", "⊋")])
def test_slanted_and_double_line_relations_read_as_the_plain_relation(latex, unicode):
    assert passes(f"a{unicode}b", rf"<p>$a {latex} b$</p>")
    assert passes(rf"$a {latex} b$", f"<p>a{unicode}b</p>")
    assert not passes(f"a{unicode}b", r"<p>$a \neq b$</p>")


def test_what_the_table_leaves_alone_is_unchanged():
    # Intended: horizontal dots are leaders, a ring is a degree sign, and \preceq is not \prec.
    assert normalize.fold(r"$a \ldots b$") == normalize.fold("a...b") == "a b"
    assert normalize.fold(r"$30^\circ$") == "30°"
    assert not passes(r"$a \preceq b$", r"<p>$a \prec b$</p>")


# ---------------------------------------------------------------------- math too deeply nested to render
def crashes_in_a_subprocess(code: str) -> subprocess.CompletedProcess:
    # `-I`: the child reads no environment or working directory of ours; the code is ours, not the input's.
    return subprocess.run([sys.executable, "-I", "-c", textwrap.dedent(code)], capture_output=True, text=True,
                          timeout=120)


@pytest.mark.parametrize("span", [
    "'$' + r'\\dots ' * 15000 + '$'",                 # the 73,000-character loop of a real output
    "'$$' + r'\\dots\\dots' * 5000 + '$$'",
    "'$' + '{' * 3000 + 'x' + '}' * 3000 + '$'",
    "r'$\\frac{1}{' * 500 + 'x' + '}$' * 500",
    "'$' + r'\\sqrt' * 3000 + ' x$'",
    "'$' + r'\\left(' * 3000 + 'x' + r'\\right)' * 3000 + '$'",
])
def test_pathological_math_fails_cleanly_instead_of_killing_the_process(span):
    out = crashes_in_a_subprocess(f"""
        from omni_parse_bench import equations
        html = "<p>" + {span} + "</p>"
        print(equations.appears(r"a \\dots b", html))
        print(equations.in_text(r"a \\dots b", html))
        print(equations.spans(html) != [])
    """)
    assert out.returncode == 0, (out.returncode, out.stderr[-300:])
    assert out.stdout.split("\n")[:2] == ["(False, 'no math in the output')", "False"], out.stdout


def test_a_page_that_survives_a_pathological_span_still_scores_its_other_math():
    out = crashes_in_a_subprocess(r"""
        from omni_parse_bench import equations
        html = "<p>$x^2 + y$</p><p>$" + r"\dots " * 15000 + "$</p>"
        print(equations.appears("x^2 + y", html))
    """)
    assert out.returncode == 0, (out.returncode, out.stderr)
    assert out.stdout.strip() == "(True, '')", out.stdout


def test_nesting_at_the_bound_renders_and_one_past_it_does_not():
    def nested(n: int) -> str: return r"\frac{1}{" * n + "x" + "}" * n
    assert equations.symbols(nested(equations.MAX_NESTING)) is not None
    assert equations.symbols(nested(equations.MAX_NESTING + 1)) is None
    assert equations.symbols(r"\left(" * equations.MAX_NESTING + "x" + r"\right)" * equations.MAX_NESTING)
    too_many = equations.MAX_NESTING + 1
    assert equations.symbols("{" * too_many + "x" + "}" * too_many) is None


def test_printed_braces_do_not_count_toward_the_nesting_bound():
    assert equations.symbols(r"\{" * 200 + "x" + r"\}" * 200) is not None


def test_a_test_whose_own_equation_is_too_deep_says_it_does_not_render():
    deep = r"\frac{1}{" * (equations.MAX_NESTING + 1) + "x" + "}" * (equations.MAX_NESTING + 1)
    assert equations.appears(deep, "<p>$x$</p>") == (False, "the test's LaTeX doesn't render")
