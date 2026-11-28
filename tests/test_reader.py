"""The reader (omni_parse_bench/reader.py): visibility, cells, alt text, tokens, scripts, quantities, and the
switches that turn each rule off. Fixtures here; the relations over loaded tests are in
metamorphic/test_reader.py."""

from __future__ import annotations

import pytest

from omni_parse_bench import reader, switches, views
from omni_parse_bench.views import MalformedOutput


@pytest.fixture(autouse=True)
def rules_on():
    """The reader's rules of step 1 on; the text fold (step 2) is off here and on where a test says so."""
    with switches.using(**{r: r != "text_fold" for r in reader.RULES}):
        yield


def toks(h: str, *, drop=("Space", "Break")) -> list[tuple[str, str]]:
    """(class, text) of each token of an HTML output; a Qty shows its canonical spelling."""
    return [
        (t.cls, t.canon if t.cls == "Qty" else t.text) for t in reader.read(h).tokens if t.cls not in drop
    ]


def gold(s: str, **kw) -> list[tuple[str, str]]:
    return [
        (t.cls, t.canon if t.cls == "Qty" else t.text)
        for t in reader.tokenize(s, **kw)
        if t.cls not in ("Space", "Break")
    ]


def words(h: str) -> list[str]:
    return [x for c, x in toks(h) if c == "Word"]


# ------------------------------------------------------------------------------------------- switches


def test_a_switch_is_off_by_default_and_named():
    with switches.set_all(False):
        assert not any(switches.state().values())
    assert set(reader.RULES) <= set(switches.SWITCHES)
    with pytest.raises(KeyError):
        switches.on("nope")
    with pytest.raises(KeyError):
        switches.using(nope=True).__enter__()


def test_the_environment_sets_switches(monkeypatch):
    with switches.using(
        visibility=False, alt_text_out=False, cell_windows=False, sup_exponent=False, tokens=False
    ):
        pass
    monkeypatch.setenv("OPB_SWITCHES", "all,-alt_text_out")
    from omni_parse_bench.switches import _override

    token = _override.set({})
    try:
        assert switches.on("visibility") and not switches.on("alt_text_out")
        monkeypatch.setenv("OPB_SWITCHES", "cell_windows")
        assert switches.on("cell_windows") and not switches.on("visibility")
        monkeypatch.setenv("OPB_SWITCHES", "bogus")
        with pytest.raises(ValueError):
            switches.on("visibility")
    finally:
        _override.reset(token)


# ------------------------------------------------------------------------------------------ visibility


HIDERS = [
    '<span style="display:none">Secret phrase</span>',
    '<span style="color:red; display : none !important">Secret phrase</span>',
    '<span style="visibility:hidden">Secret phrase</span>',
    "<span hidden>Secret phrase</span>",
    "<div hidden='until-found'>Secret phrase</div>",
    "<template>Secret phrase</template>",
    "<noscript>Secret phrase</noscript>",
    '<div style="display:none"><p><b>Secret</b> phrase</p></div>',
    "<script>Secret phrase</script>",
    "<style>Secret phrase</style>",
    "<title>Secret phrase</title>",
    "<head><title>Secret phrase</title></head>",
    "<!-- Secret phrase -->",
]


@pytest.mark.parametrize("hider", HIDERS)
def test_hidden_text_is_not_read(hider):
    assert words(f"<p>Visible</p>{hider}<p>after</p>") == ["Visible", "after"]


def test_a_hidden_input_is_not_read_but_a_visible_value_is():
    assert words('<input type="hidden" value="Secret phrase"><p>a</p>') == ["a"]
    assert words('<p>a</p><input type="text" value="Typed value">') == ["a", "Typed", "value"]


def test_aria_hidden_text_is_printed_so_it_is_read():
    assert words('<span aria-hidden="true">Printed</span> text') == ["Printed", "text"]


def test_css_that_hides_by_class_is_not_evaluated():
    assert words('<style>.x{display:none}</style><span class="x">Declared limit</span>') == [
        "Declared",
        "limit",
    ]


def test_visibility_is_inherited_by_everything_inside():
    assert words("<div hidden><p>a</p><table><tr><td>b</td></tr></table></div><p>c</p>") == ["c"]


def test_malformed_html_has_one_reading():
    # an unclosed hidden element hides what the WHATWG algorithm puts inside it
    assert words("<p>a</p><div hidden><p>b<p>c</div><p>d") == ["a", "d"]
    assert words("<b>x<i>y</b>z</i>") == ["xyz"]  # misnested inline tags still read as running text


def test_a_string_is_the_only_html():
    for bad in (None, 3, ["<p>"]):
        with pytest.raises(MalformedOutput):
            reader.read(bad)


def test_with_visibility_off_hidden_text_is_read():
    with switches.using(visibility=False):
        assert words('<span style="display:none">Secret phrase</span>') == ["Secret", "phrase"]
        assert words("<template>t</template>") == ["t"]
        assert words("<script>x</script><p>a</p>") == ["a"]  # script, style and head are never read


# ------------------------------------------------------------------------------------------ alt text


def test_alt_text_is_not_text():
    assert words('<p>a</p><img src="x.png" alt="Secret phrase"><p>b</p>') == ["a", "b"]
    assert words("<p>a ![Secret phrase](x.png) b</p>") == ["a", "b"]


def test_a_figure_contributes_only_its_caption():
    assert words('<figure><img alt="chart of sales"><figcaption>Figure 1: Sales</figcaption></figure>') == [
        "Figure",
        "Sales",
    ]


def test_with_alt_text_out_off_alt_text_is_text():
    with switches.using(alt_text_out=False):
        assert words('<img alt="Secret phrase">') == ["Secret", "phrase"]
        assert words("![alt words](x.png)") == ["alt", "words"]


# --------------------------------------------------------------------------------------------- cells


def doc_cells(h: str):
    d = reader.read(h)
    return d, [t for t in d.tokens if t.cls in reader.CONTENT]


def test_each_cell_is_its_own_block_with_its_address():
    d, c = doc_cells(
        "<table><tr><td>Total</td><td>Due</td></tr><tr><td colspan=2>x y</td><td>z</td></tr></table>"
    )
    assert [(t.text, t.cell) for t in c] == [
        ("Total", (1, 0, 0)),
        ("Due", (1, 0, 1)),
        ("x", (1, 1, 0)),
        ("y", (1, 1, 0)),
        ("z", (1, 1, 2)),
    ]
    assert [b.kind for b in d.blocks] == ["cell"] * 4


def test_a_window_stops_at_a_cell():
    d, _ = doc_cells("<table><tr><td>Total</td><td>Due</td></tr></table>")
    idx = [i for i, t in enumerate(d.tokens) if t.cls == "Word"]
    assert d.crosses_cell(idx[0], idx[1])
    assert not d.crosses_cell(idx[0], idx[0])


def test_a_window_may_cross_paragraphs_and_lines_but_not_a_cell_boundary():
    d, _ = doc_cells("<p>Total</p><p>Due</p><p>a<br>b</p>")
    idx = [i for i, t in enumerate(d.tokens) if t.cls == "Word"]
    assert not d.crosses_cell(idx[0], idx[-1])
    d, _ = doc_cells("<p>Total</p><table><tr><td>Due</td></tr></table>")
    idx = [i for i, t in enumerate(d.tokens) if t.cls == "Word"]
    assert d.crosses_cell(idx[0], idx[1])  # a cell and text outside every cell


def test_cells_of_nested_tables_have_their_own_tables():
    _, c = doc_cells("<table><tr><td>a<table><tr><td>b</td></tr></table>c</td></tr></table>")
    assert [(t.text, t.cell[0]) for t in c] == [("a", 1), ("b", 2), ("c", 1)]


def test_with_cell_windows_off_nothing_crosses():
    with switches.using(cell_windows=False):
        d = reader.read("<table><tr><td>Total</td><td>Due</td></tr></table>")
        assert not d.crosses_cell(0, len(d.tokens) - 1)


# ------------------------------------------------------------------------------------------- tokens


def test_the_classes_of_the_design_table():
    assert toks("<p>Total: -1,240.5 and +1.55; 45% $45 10kg 3万 1/2 1.2.3 10<sup>2</sup> (x)</p>") == [
        ("Word", "Total"),
        ("Sym", ":"),
        ("Qty", "-1,240.5"),
        ("Word", "and"),
        ("Qty", "+1.55"),
        ("Sym", ";"),
        ("Qty", "45%"),
        ("Qty", "$45"),
        ("Qty", "10kg"),
        ("Qty", "3万"),
        ("Qty", "1/2"),
        ("Qty", "1.2.3"),
        ("Qty", "10^2"),
        ("Sym", "("),
        ("Word", "x"),
        ("Sym", ")"),
    ]


def test_a_hyphen_or_apostrophe_between_two_letters_stays_in_the_word():
    assert toks("<p>self-aware don't l\u2019eau</p>") == [
        ("Word", "self-aware"), ("Word", "don't"), ("Word", "l\u2019eau")]
    assert toks("<p>-aware a- x-5 COVID-19 it's-</p>") == [
        ("Sym", "-"), ("Word", "aware"), ("Word", "a"), ("Sym", "-"), ("Word", "x"), ("Sym", "-"),
        ("Qty", "5"), ("Word", "COVID"), ("Sym", "-"), ("Qty", "19"), ("Word", "it's"), ("Sym", "-")]


def test_token_edges_are_fixed_per_output():
    assert words("<p>catalog</p>") == ["catalog"]
    assert toks("<p>cat<sup>1</sup>alog</p>") == [("Word", "cat"), ("Mark", "1"), ("Word", "alog")]
    assert words("<p>Total Due</p>") == ["Total", "Due"] and words("<p>TotalDue</p>") == ["TotalDue"]


def test_a_break_separates_lines_and_blocks():
    d = reader.read("<p>Total</p><p>Due<br>now</p>")
    assert [t.cls for t in d.tokens] == ["Word", "Break", "Word", "Break", "Word"]
    assert d.text == "Total\nDue\nnow"
    assert [b.kind for b in d.blocks] == ["text", "text"]


def test_a_source_line_break_in_a_paragraph_is_a_space():
    assert [t.cls for t in reader.read("<p>one\ntwo</p>").tokens] == ["Word", "Space", "Word"]


def test_token_spans_cover_the_document_text():
    d = reader.read("<p>Total  <b>Due</b>: 10</p><p>x</p>")
    assert "".join(t.text for t in d.tokens) == d.text
    assert all(d.text[t.start : t.end] == t.text for t in d.tokens)


def test_markup_stays_on_tokens():
    d = reader.read("<p><b>Bold</b> <i>it</i> <b><i>both</i></b></p>")
    assert [(t.text, sorted(t.markup)) for t in d.tokens if t.cls == "Word"] == [
        ("Bold", ["b"]),
        ("it", ["i"]),
        ("both", ["b", "i"]),
    ]


def test_a_math_element_is_a_math_token_with_its_source():
    d = reader.read(
        '<p>a</p><math><semantics><mi>x</mi><annotation encoding="application/x-tex">x^2</annotation>'
        "</semantics></math>"
    )
    assert [(t.cls, t.text) for t in d.tokens if t.cls == "Math"] == [("Math", "x^2")]
    assert not any(t.text == "x" for t in d.tokens if t.cls != "Math")


def test_checkboxes_and_numbered_lists_are_read():
    assert toks("<input type=checkbox checked><input type=radio><ol start=3><li>a<li>b</ol>") == [
        ("Sym", "☒"),
        ("Sym", "☐"),
        ("Qty", "3"),
        ("Sym", "."),
        ("Word", "a"),
        ("Qty", "4"),
        ("Sym", "."),
        ("Word", "b"),
    ]


# --------------------------------------------------------------------------------------------- marks


def test_marks():
    assert toks("<p>Smith<sup>1</sup> wrote[2] it<sup>*</sup> and<sup>†‡</sup> then[^3] but x[ab]</p>") == [
        ("Word", "Smith"),
        ("Mark", "1"),
        ("Word", "wrote"),
        ("Mark", "[2]"),
        ("Word", "it"),
        ("Mark", "*"),
        ("Word", "and"),
        ("Mark", "†‡"),
        ("Word", "then"),
        ("Mark", "[^3]"),
        ("Word", "but"),
        ("Word", "x"),
        ("Sym", "["),
        ("Word", "ab"),
        ("Sym", "]"),
    ]


def test_a_sup_of_four_digits_or_words_is_no_mark():
    assert ("Mark", "1234") not in toks("<p>a<sup>1234</sup></p>")
    assert ("Mark", "th") not in toks("<p>a<sup>th</sup></p>")


def test_a_bracket_between_digits_is_no_mark():
    assert [c for c, _ in toks("<p>1[2]3</p>")] == ["Qty", "Sym", "Qty", "Sym", "Qty"]


# ----------------------------------------------------------------------------------------- quantities


def qtys(s: str) -> list[str]:
    return [x for c, x in gold(s) if c == "Qty"]


@pytest.mark.parametrize(
    "s, want",
    [
        ("1,240.5", ["1,240.5"]),
        ("1,000 vs 1000", ["1,000", "1000"]),
        ("1,5 vs 1.5", ["1,5", "1.5"]),
        ("1.2.3 and 1.2", ["1.2.3", "1.2"]),
        ("12 500", ["12", "500"]),
        ("1'000", ["1'000"]),
        ("٣ and 3", ["٣", "3"]),
        ("１２３", ["123"]),
        ("−5", ["-5"]),
        ("－5", ["-5"]),
        ("3．14", ["3.14"]),
        ("1e3 and 10^2", ["1e3", "10", "2"]),
        ("1e-3", ["1e-3"]),
        ("2E5", ["2E5"]),
        ("10²", ["10^2"]),
        ("10⁻²", ["10^-2"]),
        ("5³⁴", ["5^34"]),
        ("$45 €45 ¥45 ₹45", ["$45", "€45", "¥45", "₹45"]),
        ("-$45", ["-$45"]),
        ("45%", ["45%"]),
        ("5‰", ["5‰"]),
        ("1M and 1m", ["1M", "1m"]),
        ("10kg", ["10kg"]),
        ("3千 3万", ["3千", "3万"]),
        ("12 3万", ["12", "3万"]),
        ("1/2 and 1/3", ["1/2", "1/3"]),
        ("12/05/2024", ["12/05/2024"]),
        ("1 / 2", ["1", "2"]),
        ("+1.55 ±0.3", ["+1.55", "±0.3"]),
        ("5kg/m", ["5kg"]),
        ("3/4kg", ["3/4kg"]),
    ],
)
def test_quantities(s, want):
    assert qtys(s) == want


@pytest.mark.parametrize(
    "s, want",
    [
        ("10-12", [("Qty", "10"), ("Sym", "-"), ("Qty", "12")]),
        ("x-5", [("Word", "x"), ("Sym", "-"), ("Qty", "5")]),
        ("(-5)", [("Sym", "("), ("Qty", "-5"), ("Sym", ")")]),
        ("= -5", [("Sym", "="), ("Qty", "-5")]),
        ("a -5", [("Word", "a"), ("Qty", "-5")]),
        ("- 0.756", [("Qty", "-0.756")]),
        ("a − 0.756", [("Word", "a"), ("Sym", "−"), ("Qty", "0.756")]),
        ("5 − 3", [("Qty", "5"), ("Sym", "−"), ("Qty", "3")]),
        ("中-5", [("Word", "中"), ("Qty", "-5")]),
        ("COVID-19", [("Word", "COVID"), ("Sym", "-"), ("Qty", "19")]),
    ],
)
def test_signs(s, want):
    assert gold(s) == want


@pytest.mark.parametrize(
    "s", ["x123y", "x123", "123y", "A4", "COVID19", "10kgs", "5th", "1.5x", "v1.2.3", "3abc"]
)
def test_digits_glued_to_letters_of_a_spaced_script_make_one_word(s):
    assert gold(s) == [("Word", s)]


def test_digits_glued_to_a_unit_are_a_quantity_and_to_cjk_are_not_glued():
    assert gold("10 kg") == [("Qty", "10"), ("Word", "kg")]  # a unit with a space is a Word
    assert gold("3章") == [("Qty", "3"), ("Word", "章")]
    assert gold("第3章") == [("Word", "第"), ("Qty", "3"), ("Word", "章")]


def test_a_superscript_after_a_digit_is_an_exponent_never_a_mark():
    assert toks("<p>10<sup>2</sup></p>") == [("Qty", "10^2")]
    assert toks("<p>4.2<sup>1</sup></p>") == [("Qty", "4.2^1")]
    assert toks("<p>10<sup>-2</sup> 10<sup>−2</sup></p>") == [("Qty", "10^-2"), ("Qty", "10^-2")]
    assert reader.read("<p>10<sup>2</sup></p>").tokens[0].text == "102"  # as written
    # a sup after a letter is a footnote mark; digits then a sup of a symbol is neither
    assert toks("<p>x<sup>2</sup></p>") == [("Word", "x"), ("Mark", "2")]


def test_the_two_exponent_forms_are_one_quantity():
    assert toks("<p>10<sup>2</sup></p>")[0] == toks("<p>10²</p>")[0] == ("Qty", "10^2")


def test_a_quantity_keeps_its_case_and_its_script():
    a, b = gold("1M")[0], gold("1m")[0]
    assert a != b
    assert gold("٣") != gold("3")


def test_with_sup_exponent_off_a_superscript_after_a_digit_reads_as_a_mark():
    with switches.using(sup_exponent=False):
        assert toks("<p>4.2<sup>1</sup></p>") == [("Qty", "4.2"), ("Mark", "1")]
        assert toks("<p>10<sup>2</sup></p>") == [("Qty", "10"), ("Mark", "2")]
        assert toks("<p>10<sup>2x</sup></p>") == [("Qty", "10"), ("Word", "2x")]


# ---------------------------------------------------------------------------------------------- scripts


def test_han_and_kana_make_one_word_per_cluster():
    assert gold("中文 日本語") == [("Word", c) for c in "中文日本語"]
    assert gold("ひらがなカタカナー") == [("Word", c) for c in "ひらがなカタカナー"]


def test_a_space_between_two_han_characters_is_dropped_by_the_reader():
    assert [t.cls for t in reader.read("<p>中 文</p>").tokens] == ["Word", "Word"]
    assert [t.cls for t in reader.read("<p>日本\n語</p>").tokens] == ["Word", "Word", "Word"]
    assert [t.cls for t in reader.tokenize("中 文")] == ["Word", "Word"]
    assert [t.cls for t in reader.read("<p>iPhone 手机</p>").tokens] == ["Word", "Space", "Word", "Word"]
    assert [t.cls for t in reader.read("<p>서 울</p>").tokens] == [
        "Word",
        "Space",
        "Word",
    ]  # Hangul keeps its space


def test_hangul_syllables_are_words_and_thai_clusters_are_words():
    assert gold("서울에서") == [("Word", c) for c in "서울에서"]
    import regex

    assert gold("กี่ชั่วโมง") == [("Word", c) for c in regex.findall(r"\X", "กี่ชั่วโมง")]
    assert gold("กี") == [("Word", "กี")]  # a vowel sign belongs to its base


def test_a_combining_mark_belongs_to_its_base():
    assert gold("café") == [("Word", "café")]
    assert gold("中́") == [("Word", "中́")]


def test_mixed_scripts_split_at_the_boundary():
    assert gold("iPhone手机") == [("Word", "iPhone"), ("Word", "手"), ("Word", "机")]
    assert gold("iPhone 手机") == [("Word", "iPhone"), ("Word", "手"), ("Word", "机")]


def test_a_word_of_one_cluster_names_its_script_class():
    t = [t for t in reader.tokenize("a中서ก") if t.cls == "Word"]
    assert [x.script for x in t] == ["", "character", "hangul", "phrase"]
    assert reader.script_class("é") == reader.SPACED


def test_a_zwj_and_zwnj_stay_with_their_base():
    assert gold("می‌خواهم") and len(gold("می‌خواهم")) <= 3


# ---------------------------------------------------------------------------------------------- wrap


def test_a_hyphen_ending_a_line_before_a_lowercase_letter_is_a_wrap():
    assert toks("<p>self-<br>aware</p>") == [("Word", "self"), ("Wrap", "-\n"), ("Word", "aware")]
    assert toks("<p>co-\noperate</p>") == [("Word", "co"), ("Wrap", "-\n"), ("Word", "operate")]


@pytest.mark.parametrize(
    "h",
    [
        "<p>Self-<br>Aware</p>",
        "<p>self- aware</p>",
        "<p>self -<br>aware</p>",
        "<p>a-</p><p>b</p>",
        "<p>10-<br>aware</p>",
    ],
)
def test_other_hyphens_are_no_wrap(h):
    assert "Wrap" not in {c for c, _ in toks(h)}


def test_a_gold_string_has_no_wrap():
    assert "Wrap" not in {c for c, _ in gold("self-\naware")}


# --------------------------------------------------------------------------------- legacy text view


@pytest.mark.parametrize("hider", HIDERS[:8])
def test_the_text_view_leaves_out_what_a_page_hides(hider):
    v = views.html(f"<p>Visible</p>{hider}<p>after</p>")
    assert "Secret" not in v.text and "Visible" in v.text and "after" in v.text


def test_the_text_view_leaves_out_alt_text():
    v = views.html('<p>a</p><img alt="Secret phrase"><p>b</p>')
    assert "Secret" not in v.text and "Secret" not in v.seen


def test_with_the_switches_off_the_text_view_is_what_it_was():
    with switches.set_all(False):
        v = views.html('<p>a</p><span hidden>Secret</span><img alt="alt words">')
        assert "Secret" in v.text and "alt words" in v.text and "alt words" not in v.seen


def test_a_page_that_hides_nothing_reads_the_same_with_the_switches_on_or_off():
    page = (
        "<table><tr><td>a</td><td>b &amp; c</td></tr></table>"
        "<p>Let <b>x</b> be 10<sup>2</sup> alt display</p>"
    )
    with switches.set_all(False):
        off = views.html(page)
    assert views.html(page) == off


def test_the_visible_html_of_malformed_input_is_html():
    assert "Secret" not in views.html("<div hidden><p>Secret<p>more</div><p>x").html


def test_a_rowspan_holds_its_column_in_the_rows_below():
    _, c = doc_cells(
        "<table><tr><td rowspan=2>A</td><td>B</td></tr><tr><td>C</td></tr>"
        "<tr><td colspan=2 rowspan=2>D</td><td>E</td></tr><tr><td>F</td></tr></table>"
    )
    assert [(t.text, t.cell[1:]) for t in c] == [("A", (0, 0)), ("B", (0, 1)), ("C", (1, 1)), ("D", (2, 0)),
                                                 ("E", (2, 2)), ("F", (3, 2))]


def test_a_grouping_space_is_part_of_a_quantity_and_a_sign_gap_is_not():
    assert gold("1\u2009234")[0] == ("Qty", "1\u2009234") != gold("1234")[0]
    assert gold("- 0.756") == [("Qty", "-0.756")]


def test_a_hyphen_after_a_combining_mark_stays_in_the_word():
    assert toks("<p>a\u0301-b</p>") == [("Word", "a\u0301-b")]


def test_the_text_fold_runs_between_the_quantity_scan_and_word_tokenization():
    with switches.using(text_fold=True):
        _check_fold()


def _check_fold():
    assert toks("<p>ﬁx the “quote” – x ① ＡＢＣ 12 ３４ a…b</p>") == [
        ("Word", "fix"), ("Word", "the"), ("Sym", '"'), ("Word", "quote"), ("Sym", '"'), ("Sym", "-"),
        ("Word", "x"), ("Qty", "1"), ("Word", "ABC"), ("Qty", "12"), ("Qty", "34"), ("Word", "a"),
        ("Word", "b")]
    assert toks("<p>• Bullet</p>") == [("Word", "Bullet")]


def test_a_quantity_keeps_its_spelling_through_the_fold():
    assert [t.text for t in reader.read("<p>１２３ 4,5</p>").tokens if t.cls == "Qty"] == ["１２３", "4,5"]


def test_with_text_fold_off_the_reading_is_the_unfolded_one():
    with switches.using(text_fold=False):
        assert words("<p>ﬁx “q”</p>") == ["ﬁx", "q"]


def test_long_inputs_are_linear_and_do_not_recurse():
    """A fraction chain of any length reads as one quantity, and a very long line of symbols reads in time
    linear in its length (these once recursed and went quadratic)."""
    import time

    from omni_parse_bench import reader

    t0 = time.time()
    chain = reader.tokenize("1/" * 20000 + "1")
    assert len(chain) == 1 and chain[0].cls == reader.QTY
    syms = reader.tokenize("§" * 200000)
    assert len(syms) == 200000
    assert time.time() - t0 < 20


def test_long_rewritten_run_reads_in_bounded_time():
    """A long stretch that the fold rewrites everywhere (full-width bars) keeps exact source spans, and reads
    in time linear in its length (difflib alone was quadratic here, and so was the markup of each span)."""
    import time

    from omni_parse_bench import reader, switches

    text = "｜ " * 8000
    with switches.using(text_fold=True):
        t0 = time.time()
        toks = reader.tokenize(text)
        assert time.time() - t0 < 20
    bars = [t for t in toks if t.text == "|"]
    assert len(bars) == 8000
    assert all(t.end - t.start == 1 for t in bars)
    assert bars[3].start == 6


def test_a_stretch_that_folds_to_nothing_reads_as_nothing():
    """The cluster table of an empty line is empty (a fold can empty a stretch: invisible characters only)."""
    from omni_parse_bench import reader

    assert reader.tokenize("") == []
    with switches.using(text_fold=True):
        html = "<p>a</p><p>\u200b\u200b</p><p>b</p>"
        assert [t.text for t in reader.read(html).tokens if t.cls == "Word"] == ["a", "b"]


def test_a_scorer_error_fails_one_test_and_not_the_run(monkeypatch, caplog):
    """A test that raises on a well-formed output fails with a logged reason; the page's other tests still run."""
    from omni_parse_bench.scorers.unit_tests import compare, runners, tests

    monkeypatch.delenv("OPB_RAISE_SCORER_ERRORS", raising=False)
    real = runners.run

    def run_bad(*a):
        raise ValueError("zip mismatch")

    spec = {"test_type": "present", "output_type": "html", "derivation": "publisher_markup", "tags": [],
            "args": {"content": {"text": "hello", "max_diffs": 0}}, "settings": {}}
    bad, ok = tests.parse("p", {"tests": [{**spec, "id": "bad", "args": {"content": {"text": "boom", "max_diffs": 0}}}, {**spec, "id": "ok"}]})
    monkeypatch.setattr(runners, "run", lambda *a: real(*a) if a[1] == ok.params else run_bad(*a))
    with caplog.at_level("ERROR", logger="omni_parse_bench.scorer"):
        out = compare.score({"html": "<p>hello</p>"}, [bad, ok])
    assert [(v.id, v.result) for v in out] == [("bad", "fail"), ("ok", "pass")]
    assert out[0].why.startswith("scorer error: ValueError: zip mismatch")
    assert any("test bad" in r.getMessage() for r in caplog.records)
    from omni_parse_bench.scorers import unit_tests as scorer

    page = scorer.UnitTests().score({"html": "<p>hello</p>"}, [bad, ok])
    assert page.result["scorer_errors"] == 1
