# ruff: noqa: E501
"""Cases for docs/scoring/internals.md: how an output becomes the text the tests compare."""
import collections
import random

import fuzzysearch
from cases import cell, code, folds, order, reading, repeat, table, text

from omni_parse_bench import markdown, normalize, tables, views, vocab
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as T


def md_text(label, rule, md, expect):
    return reading(label, rule, code(md), expect, lambda: normalize.fold(views.html(markdown.to_html(md)).text))


def md_tables(label, rule, md, expect):
    def run():
        ts = tables.parse(markdown.to_html(md))
        return " / ".join(" | ".join(t.text[c] or "(empty)" for c in sorted(t.text)) for t in ts) or "no table"
    return reading(label, rule, code(md), expect, run)


def seen(label, rule, out, expect):
    return reading(label, rule, code(out), expect, lambda: normalize.fold(views.html(out).seen))


def loads(label, rule, test_type, args, expect, settings=None, show=None):
    """Whether a test with these args loads: "loads", or "refused"."""
    t = {"id": "t", "test_type": test_type, "output_type": vocab.READS[test_type], "derivation": vocab.DERIVATIONS[0],
         "tags": [], "args": args, "settings": settings or {}}

    def run():
        try:
            T.test("page", t)
            return "loads"
        except ValueError:
            return "refused"
    shown = ", ".join(f"{k} {code(v.get('text', v.get('latex', '')))}" + (f" (md {v['max_diffs']})" if "max_diffs" in v else "")
                      for k, v in args.items())
    return reading(label, rule, show or f"{test_type}: {shown}", expect, run)


def edits(k: int, swap: bool):
    """Random needles of 6-24 letters with k edits (substitutions, insertions, deletions, and adjacent swaps when
    `swap`), seed 1: how often `present` passes at max_diffs k when the true edit distance is above k."""
    def run():
        rng = random.Random(1)
        letters = "abcdefghijklmnopqrstuvwxyz"
        counts = collections.Counter()
        for _ in range(4000):
            needle = "".join(rng.choice(letters) for _ in range(rng.randint(6, 24)))
            kinds = [rng.choice(["sub", "ins", "del", "swap"]) for _ in range(k)]
            if ("swap" in kinds) != swap:
                continue
            out = needle
            for kind in kinds:
                i = rng.randrange(len(out) - 1)
                out = {"sub": out[:i] + rng.choice([c for c in letters if c != out[i]]) + out[i + 1:],
                       "ins": out[:i] + rng.choice(letters) + out[i:], "del": out[:i] + out[i + 1:],
                       "swap": out[:i] + out[i + 1] + out[i] + out[i + 2:]}[kind]
            hay = f"zq {out} qz"
            true = min((m.dist for m in fuzzysearch.find_near_matches(needle, hay, max_l_dist=k + 2)), default=99)
            passed = R.found(R.Text(needle, k), views.html(f"<p>{hay}</p>"))[0]
            counts["cases"] += 1
            counts["passed above budget"] += passed and true > k
            counts["failed within budget"] += (not passed) and true <= k
        return ", ".join(f"{n} {what}" for what, n in counts.items())
    what = f"{k} random edit{'s' if k > 1 else ''}, {'with' if swap else 'no'} adjacent swap, `max_diffs` {k}"
    return run, what


def measure(label, k, swap, expect):
    run, what = edits(k, swap)
    return reading(label, what, "4,000 random needles, seed 1", expect, run)


TABLES = [
    table(
        "internals-markdown",
        md_text("md-emphasis", "emphasis and code lose their markup", "**Bold** *it* ~~del~~ `code`", "bold it del code"),
        md_text("md-list", "a list marker stays as text", "29. Item\n\n- bullet", "29. item - bullet"),
        md_text("md-image", "an image becomes its description", "![chart of sales](x.png)", "chart of sales"),
        md_tables("md-table", "a pipe table with a separator row is a table", "| A | B |\n|---|---|\n| 1 | 2 |", "A | B | 1 | 2"),
        md_tables("md-no-separator", "without the separator row it is not", "| A | B |\n| 1 | 2 |", "no table"),
        md_tables("md-amounts", "amounts beside math stay in their cells", "| a | b | c |\n|---|---|---|\n| $5 | x_1 | US$6 |", "a | b | c | $5 | x_1 | US$6"),
        md_tables("md-math-cell", "a math span may cross a pipe", "| a | b |\n|---|---|\n| $x_1 | y$ |", "a | b | $x_1 | y$ | (empty)"),
    ),
    table(
        "internals-views",
        folds("view-tags", "tags are dropped", "<p><b>Total</b> <i>Due</i></p>", "total due"),
        folds("view-sub", "`<sub>` text joins its word", "<p>H<sub>2</sub>O</p>", "h2o"),
        folds("view-sup", "`<sup>` is set apart by a space", "<p>1,240<sup>1</sup></p>", "1,240 1"),
        folds("view-sup-before", "so is `</sup>` before a number", "<p><sup>1</sup>-4.8 and x<sup>2</sup>y</p>", "1 -4.8 and x 2y"),
        folds("view-ol", "an ordered list item gets its number", "<ol start='3'><li>Item</li></ol>", "3. item"),
        folds("view-input", "an input shows its value", "<p>Name: <input value='Bob'></p>", "name: bob"),
        folds("view-checkbox", "a checkbox is a box glyph", "<p><input type=checkbox checked> Yes</p>", "☒ yes"),
        folds("view-hidden", "scripts, styles, comments and `<head>` are not text", "<head><title>T</title></head><script>x</script><!-- c --><p>Body</p>", "body"),
        folds("view-cells", "a table reads cell by cell, row by row", "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td></tr></table>", "a b c"),
        folds("view-alt", "an image reads as its description", "<p>See</p><img alt='Chart'>", "see chart"),
        seen("view-seen", "`repeat` reads the text without descriptions", "<p>See</p><img alt='Chart'>", "see"),
    ),
    table(
        "internals-fold",
        folds("fold-math", "math is read as text", "$c_{\\text{MC}}$ and $$2 . 5 5$$", "cmc and 2.55"),
        folds("fold-hyphen", "a line-end hyphen before a lowercase letter joins", "develop- ers, R- M", "developers, r- m"),
        folds("fold-hyphen-block", "a block break is a line break for a hyphen: it joins, as a `<br>` does", "<p>Head-</p><p>quarters</p><p>develop-<br>ers</p>", "headquarters developers"),
        folds("fold-superscript", "a superscript digit after a digit is set apart", "1,240¹", "1,240 1"),
        folds("fold-nfkc", "compatibility forms (ligatures, full width, sub- and superscripts)", "ﬁnal １２ m² H₂O ½ №", "final 12 m2 h2o 1/2 no"),
        folds("fold-invisible", "zero-width and soft hyphen characters vanish", "a\u200bb a\u00adb", "ab ab", show="`a` U+200B `b a` U+00AD `b`"),
        folds("fold-checkbox", "checkboxes become ☒ or ☐", "[x] Yes [ ] No ☑ ok", "☒ yes ☐ no ☒ ok"),
        folds("fold-footnote", "a bracketed footnote marker becomes a spaced number", "Smith[1] and [12] Jones", "smith 1 and 12 jones"),
        folds("fold-bullet", "a bullet starting a line goes; one inside a line stays", "• one • two", "one • two"),
        folds("fold-leaders", "runs of 3 or more dots, dashes, `_`, `=`, `*` become a space", "Name ........ 5 a --- b ___ c *** d", "name 5 a b c d"),
        folds("fold-leaders-block", "a leader run stops at a block break; a `<br>` does not stop it", "<p>a _</p><p>__</p><p>b _<br>__ c</p>", "a _ __ b c"),
        folds("fold-leader-cjk", "a run of 3 or more ideographic full stops is a leader too", "目次。。。。5 第一章｡｡｡8", "目次 5 第一章 8"),
        folds("fold-leader-sign", "a dash run before a spaced digit keeps its sign", "Revenue ....... -4.8", "revenue -4.8"),
        folds("fold-blank", "two underscores are not a leader", "Name: __", "name: __"),
        folds("fold-typography", "dash, quote, space and arrow families", "a–b a−b it’s «hi» a b ⇒", "a-b a-b it's \"hi\" a b →", show="`a–b a−b it’s «hi» a`(nbsp)`b ⇒`"),
        folds("fold-cjk", "full-width punctuation becomes ASCII", "日本語。３％", "日本語.3%"),
        folds("fold-middot", "a middle dot between digits is a decimal point; `⋅` is not", "2·3 2⋅3", "2.3 2⋅3"),
        folds("fold-case", "case is folded, but no letter is changed into others", "STRASSE straße Α", "strasse straße α"),
        folds("fold-kept", "kept apart: diacritics, punctuation, currency, `**`", "naïve Mr. $5.00 **x**", "naïve mr. $5.00 **x**"),
    ),
    table(
        "internals-dollars",
        folds("dollar-pairs", "neighbouring dollars pair", "$a$ and $b$", "a and b"),
        folds("dollar-price", "a price is a stray dollar", "costs $5 and $x^2$", "costs $5 and x2"),
        folds("dollar-two-prices", "two prices are not a span", "$92,000; Net +$60,000", "$92,000; net +$60,000"),
        folds("dollar-tie", "on a tie the earlier dollar is the stray", "Cost $ and $ x $ now", "cost $ and x now"),
        folds("dollar-block", "a single-dollar span stops at a block", "<p>$a</p><p>b$</p>", "$a b$"),
        folds("dollar-br", "a `<br>` does not stop it", "<p>$x<br>_1$</p>", "x1"),
        folds("dollar-hug", "plain symbols hugging their dollars are math", "$p < 0.05$", "p < 0.05"),
        folds("dollar-padded", "padded symbols are not", "$p < 0.05 $", "$p < 0.05 $"),
        folds("dollar-pad-page", "a padded word is math on a page that pads its math", "$ ab $ and $ x_1 $", "ab and x1"),
        folds("dollar-pad-alone", "but not on its own", "$ ab $", "$ ab $"),
        folds("dollar-prose", "three bare words are prose, not math", "$the quick brown fox$", "$the quick brown fox$"),
        folds("dollar-entity", "a dollar written as an entity is a dollar", "&#36;x^2&#36;", "x2"),
        folds("dollar-escaped", "an escaped dollar is not a delimiter", "x \\$5 and \\$6", "x \\$5 and \\$6"),
        folds("dollar-paren", "a `\\(..\\)` is not inside a dollar span", "$5.00 \\(a_2\\) $", "$5.00 a2 $"),
    ),
    table(
        "internals-hyphen",
        text("hyph-present", "I", "`present`: kept or dropped hyphen, either reading", "self-aware", "self- aware"),
        order("hyph-order", "P", "`order`: the hyphen is dropped", "self-aware", "ZZZ", "<p>self- aware</p><p>ZZZ</p>"),
        repeat("hyph-repeat", "P", "`repeat`: the hyphen is dropped", "self-aware", 1, "self- aware"),
        cell("hyph-cell", "P", "`table_cell`: the hyphen is dropped", "self-aware", "<table><tr><td>self- aware</td></tr></table>"),
        text("hyph-unspaced", "P", "an unspaced hyphen is never optional", "develop-ers", "developers"),
    ),
    table(
        "internals-edits",
        measure("edits-1", 1, False, "3050 cases, 0 passed above budget, 0 failed within budget"),
        measure("edits-1-swap", 1, True, "1021 cases, 820 passed above budget, 0 failed within budget"),
        measure("edits-2", 2, False, "2229 cases, 0 passed above budget, 0 failed within budget"),
        measure("edits-2-swap", 2, True, "1782 cases, 1016 passed above budget, 0 failed within budget"),
    ),
    table(
        "internals-loader",
        loads("load-md-max", "`max_diffs` must be below the folded length", "present", {"content": {"text": "ab", "max_diffs": 2}}, "refused"),
        loads("load-md-ok", "one edit on two characters", "present", {"content": {"text": "ab", "max_diffs": 1}}, "loads"),
        loads("load-repeat-md", "`repeat` takes no edits", "repeat", {"content": {"text": "ab", "max_diffs": 1}}, "refused", {"expected_count": 1}),
        loads("load-shared-md", "the args of one test share `max_diffs`", "order", {"before": {"text": "abc", "max_diffs": 1}, "after": {"text": "abc", "max_diffs": 0}}, "refused"),
        loads("load-empty", "a gold that folds to nothing", "present", {"content": {"text": "\u200b", "max_diffs": 0}}, "refused",
              show="present: content U+200B (md 0)"),
        loads("load-latex-empty", "a latex gold that renders nothing", "present", {"content": {"latex": "\\quad"}}, "refused"),
    ),
]
