# ruff: noqa: E501
"""`no_excess_repeats`: what a gold file may say, and the verdicts it gives on faithful pages, loops, duplicated
passages, passages the page prints twice, tables read as text, math and scripts written without spaces
(docs/scoring/no_excess_repeats.md)."""
from __future__ import annotations

import pytest

from omni_parse_bench import score
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as gold

A = "The committee met on Monday to review the budget and the plans for the new library downtown."
B = "Members asked for a second estimate before the vote."
PAGE = f"{A} {B}"


def gold_of(content, settings=None) -> tuple[gold.Test, ...]:
    return gold.parse("p", {"tests": [{"id": "a", "test_type": "no_excess_repeats", "output_type": "html",
                                       "derivation": "text_layer", "tags": [], "args": {"content": content},
                                       "settings": settings or {}}]})


def verdict(html: str, page: str = PAGE) -> tuple[bool, str]:
    r = score({"html": html}, gold_of({"text": page, "max_diffs": 0}))[0]
    return r.result == "pass", r.why


# ------------------------------------------------------------------------------------------- the loader


def test_the_loader_takes_the_pages_text():
    [t] = gold_of({"text": PAGE, "max_diffs": 0})
    assert t.params == R.NoExcessRepeats(PAGE)
    assert gold.arg_kinds("no_excess_repeats", t.args) == ("text",)


@pytest.mark.parametrize("content, settings, why", [
    ({"text": PAGE, "max_diffs": 1}, {}, "max_diffs: 0"),
    ({"text": PAGE, "max_diffs": 0, "exact_case": False}, {}, "no exact_case"),
    ({"text": PAGE, "max_diffs": 0, "place": [[0, 0, 1, 1]]}, {}, "no place"),
    ({"number": "12"}, {}, "content is the page's full text"),
    ({"text": "% + %", "max_diffs": 0}, {}, "no word to count"),
    ({"text": PAGE, "max_diffs": 0}, {"n": 8}, "no settings expected"),
])
def test_the_loader_refuses_what_the_test_cannot_count(content, settings, why):
    with pytest.raises(ValueError, match=why):
        gold_of(content, settings)


@pytest.mark.parametrize("text", ["สวัสดีครับ ทุกคน", "会议在周一举行", "ສະບາຍດີ", "សួស្តី", "こんにちは", "안녕하세요", "မင်္ဂလာပါ"])
def test_the_loader_refuses_a_script_written_without_spaces(text):
    with pytest.raises(ValueError, match="without spaces"):
        gold_of({"text": f"{PAGE} {text}", "max_diffs": 0})


def test_a_figure_is_read_for_its_caption_only():
    fig = f"<figure><img src='a.png'><p>{A}</p><figcaption>{A}</figcaption></figure>"
    assert verdict(f"<p>{B}</p>{fig}")[0]
    assert not verdict(f"<p>{A}</p><p>{B}</p>{fig}")[0]


def test_the_loader_needs_content():
    with pytest.raises(ValueError, match="needs args"):
        gold.parse("p", {"tests": [{"id": "a", "test_type": "no_excess_repeats", "output_type": "html",
                                    "derivation": "authored", "tags": [], "args": {}, "settings": {}}]})


# ------------------------------------------------------------------------------------------- verdicts


@pytest.mark.parametrize("html", [
    f"<p>{A}</p><p>{B}</p>", f"<p>{B}</p><p>{A}</p>", f"<p>{A} {B}</p>", f"<h1>{A}</h1><ul><li>{B}</li></ul>",
    f"<p>{A}</p>", "", f"<p>{A.upper()}</p><p>{B}</p>",
])
def test_a_faithful_or_shorter_page_passes(html):
    assert verdict(html) == (True, "")


@pytest.mark.parametrize("html", [
    f"<p>{A}</p><p>{A}</p><p>{B}</p>", f"<p>{A} {A}</p><p>{B}</p>", f"<p>{A}</p><p>{B}</p><p>{A}</p><p>{B}</p>",
    "<p>" + "budget " * 40 + "</p>", f"<p>{A}</p><p>{B}</p><p>{'the plans and ' * 10}</p>",
    f"<p>{A}</p><div>{A}</div><p>{B}</p>", f"<p>{A}</p><p>{A.replace('Monday', 'Monday,')}</p><p>{B}</p>",
])
def test_a_loop_or_a_duplicate_fails(html):
    ok, why = verdict(html)
    assert not ok and "appears" in why and "more often than the page prints them" in why, why


def test_the_why_names_the_run_its_count_and_a_word_in_excess():
    assert verdict(f"<p>{A}</p><p>{A}</p><p>{B}</p>") == (False, (
        "'the committee met on monday to review the budget and the plans for the new libra' appears 2x, and its "
        "words more often than the page prints them (e.g. 'the' 9x, the page 5x)"))


def test_a_repeat_whose_every_word_the_page_prints_often_enough_passes():
    # Note: "for" is in both sentences, so the page prints it twice; A twice without B is not in excess there
    assert verdict(f"<p>{A}</p><p>{A}</p>")[0]
    assert not verdict(f"<p>{A}</p><p>{A}</p><p>{B}</p>")[0]


def test_a_passage_the_page_prints_twice_may_be_written_twice():
    page = f"{A} {B} {A}"
    assert verdict(f"<p>{A}</p><p>{B}</p><p>{A}</p>", page)[0]
    assert not verdict(f"<p>{A}</p><p>{B}</p><p>{A}</p><p>{A}</p>", page)[0]


def test_sixteen_words_is_the_run():
    words = [f"w{i}" for i in range(40)]
    page = " ".join(words)
    for n, ok in ((15, True), (16, False)):
        extra = " ".join(words[:n])
        assert verdict(f"<p>{page}</p><p>{extra}</p>", page)[0] is ok, n
    assert R.REPEAT_RUN == 16


def test_order_does_not_matter_on_either_side():
    shuffled = f"{B} {A}"
    assert verdict(f"<p>{A}</p><p>{B}</p>", shuffled)[0]
    assert not verdict(f"<p>{A}</p><p>{A}</p><p>{B}</p>", shuffled)[0]


@pytest.mark.parametrize("extra", [
    f"<p>$${A}$$</p>", f"<p>\\({A}\\)</p>", f"<p>\\[{A}\\]</p>", f"<math>{A}</math>",
    f"<img alt='{A}'>",
])
def test_math_and_image_descriptions_are_not_read(extra):
    assert verdict(f"<p>{A}</p><p>{B}</p>{extra}") == (True, "")


def test_a_table_does_not_hide_the_text_after_it():
    assert not verdict(f"<p>{A}</p><table><tr><td>x</td></tr></table><p>{A}</p><p>{B}</p>")[0]


@pytest.mark.parametrize("before", ["<!-- <table> -->", "<p title='<table>'>Note</p>", "<p>a &lt;table&gt; tag</p>",
                                    "<p>Cost $5</p>", "<p>$5 and $6</p>"])
def test_a_table_tag_as_text_or_a_price_hides_nothing(before):
    # Note: tables and math are found in the parsed html and by `mathspans`, so a tag in a comment or an
    # attribute and a dollar of a price leave the text after them read
    assert verdict(f"{before}<p>{A}</p><p>{B}</p>")[0]
    assert not verdict(f"{before}<p>{A}</p><p>{A}</p><p>{B}</p><p>Fee $6</p>")[0]


@pytest.mark.parametrize("table", [f"<table><tr><td>{A}</td></tr></table>",
                                   f"<table><tr><td>{A}</td><td>{A}</td></tr></table>",
                                   f"<table><tr><td><table><tr><td>{A}</td></tr></table></td></tr></table>",
                                   f"<table><tr><td>x</td></tr><p>{A}</p>"])
def test_a_table_is_read_as_text(table):
    # Note: a table's cells, nested or unclosed, are words like any other: a sentence written again in one is
    # written twice
    assert not verdict(f"<p>{A}</p><p>{B}</p>{table}")[0]


@pytest.mark.parametrize("got", ["self-aware", "self- aware", "self-<br>aware", "self-\naware", "selfaware"])
def test_a_compound_reads_the_same_kept_broken_or_joined(got):
    page = " ".join(f"Item {i}: the self-aware system logs." for i in range(17))
    html = "".join(f"<p>Item {i}: the {got} system logs.</p>" for i in range(17))
    assert verdict(html, page) == (True, "")
    assert not verdict(html + html, page)[0]


def test_a_word_broken_at_a_paragraph_end_joins_the_next_paragraphs_first_word():
    # Note: a line hyphen is read joined across a block end too, so a paragraph that ends in `measure-` and is
    # written twice reads `measurein`: the two copies share no run of all their words
    x = "In the season the survey team of the national mapping division made careful measure-"
    assert R._words(R._repeat_text(f"<p>{x}</p><p>{x}</p>"))[11:14] == ["made", "careful", "measurein"]


def test_two_short_paragraphs_written_twice_fail_only_when_a_run_of_16_repeats():
    # Note: a run of 16 words written twice is the unit, so two 8-word paragraphs written twice are caught when
    # the copies keep their neighbors (A B A B) and not when each is doubled in place (A A B B): a blind spot
    a, b = "one two three four five six seven eight", "nine ten eleven twelve thirteen fourteen fifteen sixteen"
    page = f"{a} {b}"
    assert verdict(f"<p>{a}</p><p>{b}</p>", page)[0]
    assert not verdict(f"<p>{a}</p><p>{b}</p><p>{a}</p><p>{b}</p>", page)[0]
    assert verdict(f"<p>{a}</p><p>{a}</p><p>{b}</p><p>{b}</p>", page)[0]


def test_words_of_a_script_without_spaces_are_its_characters():
    zh = "第三次试验后发动机分解检查结果如下在鼓风机进口处卡着两只鸟"
    assert R._words(zh)[:3] == ["第", "三", "次"]
    # Note: a gold cannot hold one (the loader refuses it), but an output's loop in one is found on any page
    assert verdict(f"<p>{A}</p><p>{B}</p><p>{zh}</p>")[0]
    assert not verdict(f"<p>{A}</p><p>{B}</p><p>{zh}</p><p>{zh}</p>")[0]


def test_marks_stay_in_their_word():
    km = "ក្រុមប្រឹក្សា"
    assert R._words(f"{km} {km}") == [km, km]
    te = "ఏర్పోవడం"
    assert R._words(te) == [te]


def test_a_long_page_is_graded_quickly():
    import time
    page = " ".join(f"word{i}" for i in range(5000))
    t0 = time.perf_counter()
    assert verdict(f"<p>{page}</p>", page)[0]
    assert not verdict(f"<p>{page} {page}</p>", page)[0]
    assert time.perf_counter() - t0 < 2


ROW = "Not applicable, see note one for the details of the lease terms and the fees listed in the annex"


TABLE_FORMS = [f"<table><tr><td>{ROW}</td></tr><tr><td>{ROW}</td></tr></table>",
               f"<p>| {ROW} |\n| {ROW} |</p>", f"<p>| {ROW} |</p><p>| {ROW} |</p>", f"<p>{ROW}</p><p>{ROW}</p>",
               f"| {ROW} |\n|---|\n| {ROW} |"]


@pytest.mark.parametrize("table", TABLE_FORMS)
def test_a_table_the_page_prints_passes_however_it_is_written(table):
    # Note: the content holds the table's text, and the output's cells count the same in a <table>, as a
    # markdown table, or flattened to paragraphs
    page = f"{PAGE} {ROW} {ROW}"
    assert verdict(f"<p>{A}</p><p>{B}</p>{table}", page) == (True, "")
    assert not verdict(f"<p>{A}</p><p>{B}</p>{table}<p>{ROW}</p>", page)[0]


def test_a_table_row_the_page_prints_once_fails_written_twice():
    page = f"{PAGE} {ROW}"
    assert verdict(f"<p>{A}</p><p>{B}</p><table><tr><td>{ROW}</td></tr></table>", page)[0]
    assert not verdict(f"<p>{A}</p><p>{B}</p>{TABLE_FORMS[0]}", page)[0]


@pytest.mark.parametrize("loop", ["-".join(["budget"] * 40),
                                  " ".join(f"item {i} and the plans for the library" for i in range(1, 13))])
def test_a_loop_that_changes_a_word_in_every_16_passes(loop):
    # Note: a blind spot: one word joined by hyphens is one word, and a counter breaks every run of 16
    assert verdict(f"<p>{A}</p><p>{B}</p><p>{loop}</p>")[0]
