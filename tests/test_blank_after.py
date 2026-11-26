# ruff: noqa: E501
"""`present` with `{"blank_after": true}`: what a gold file may say, and the verdicts it gives on blank fields,
invented values, tables of three layouts, and the places the label can hide (docs/scoring/present-text.md)."""
from __future__ import annotations

import pytest

from omni_parse_bench import markdown, score
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as gold

DOB, MASK = "Date of birth:", "__/__/____"
STOPS = ["Name:", "Place of birth:"]
SETTING = {"blank_after": True}


def text(s: str) -> dict:
    return {"text": s, "max_diffs": 0}


def args(label: str = DOB, printed: str | None = MASK, stops: list[str] | None = None) -> dict:
    out: dict = {"content": text(label)}
    if printed is not None:
        out["printed"] = text(printed)
    out["stops"] = [text(s) for s in (STOPS if stops is None else stops)]
    return out


def gold_of(a: dict, settings: dict | None = None, test_type: str = "present") -> tuple[gold.Test, ...]:
    return gold.parse("p", {"tests": [{"id": "a", "test_type": test_type, "output_type": "html",
                                       "derivation": "authored", "tags": ["form"], "args": a,
                                       "settings": SETTING if settings is None else settings}]})


def verdict(html: str, **kw) -> tuple[bool, str]:
    r = score({"html": html}, gold_of(args(**kw)))[0]
    return r.result == "pass", r.why


def passes(html: str, **kw) -> bool:
    return verdict(html, **kw)[0]


def rows(*rs: str) -> str:
    return "<table>" + "".join(f"<tr>{r}</tr>" for r in rs) + "</table>"


# ----------------------------------------------------------------------------------------- the schema


def test_a_blank_after_test_loads_with_its_roles():
    t, = gold_of(args())
    p = t.params
    assert p.blank_after and p.content == R.Text(DOB, 0) and p.printed == R.Text(MASK, 0)
    assert p.stops == (R.Text("Name:", 0), R.Text("Place of birth:", 0))


def test_the_roles_are_optional():
    p = gold_of({"content": text(DOB)}).__getitem__(0).params
    assert p.blank_after and p.printed is None and p.stops == ()


def test_a_plain_present_test_is_unchanged():
    p = gold_of({"content": text(DOB)}, {})[0].params
    assert p == R.Present(R.Text(DOB, 0)) and not p.blank_after


@pytest.mark.parametrize("role", ["printed", "stops"])
def test_the_roles_need_the_setting(role):
    with pytest.raises(ValueError, match="blank_after"):
        gold_of({"content": text(DOB), **{k: v for k, v in args().items() if k == role}}, {})


@pytest.mark.parametrize("settings", [{"blank_after": False}, {"blank_after": 1}, {"blank_after": "true"},
                                      {"blank_after": True, "x": 1}, {"other": True}])
def test_the_setting_is_exactly_true(settings):
    with pytest.raises(ValueError, match="settings"):
        gold_of(args(), settings)


@pytest.mark.parametrize("test_type", ["order", "repeat", "table_cell", "layout_kind", "format"])
def test_the_setting_is_refused_on_other_test_types(test_type):
    with pytest.raises(ValueError):
        gold_of({"content": text(DOB)}, SETTING, test_type)


@pytest.mark.parametrize("bad", [
    {"content": {"number": "5"}}, {"content": {"latex": "x"}},
    {"content": {"text": DOB, "max_diffs": 1}}, {"content": {"text": DOB, "max_diffs": 0, "exact_case": True}},
    {"content": {"text": DOB, "max_diffs": 0, "exact_case": False}},
    {"content": {"text": DOB, "max_diffs": 0, "place": [[0, 0, 1, 1]]}},
])
def test_the_label_is_exact_text(bad):
    with pytest.raises(ValueError):
        gold_of(bad)


@pytest.mark.parametrize("role, bad", [
    ("printed", {"number": "5"}), ("printed", {"text": MASK, "max_diffs": 1}),
    ("printed", {"text": "x", "max_diffs": 0, "exact_case": False}),
    ("stops", [{"text": "Name:", "max_diffs": 2}]), ("stops", [{"number": "5"}]), ("stops", "Name:"),
    ("printed", [text(MASK)]), ("stops", [text(DOB)]), ("stops", [text("Name:"), text("name:")]),
])
def test_the_other_roles_are_exact_text_too(role, bad):
    with pytest.raises(ValueError):
        gold_of({"content": text(DOB), role: bad})


def test_a_label_that_folds_to_nothing_is_refused():
    with pytest.raises(ValueError):
        gold_of({"content": text("___")})


def test_arg_kinds_counts_text_once():
    assert gold.arg_kinds("present", args()) == ("text",)


# ------------------------------------------------------------------------- running text: both ways

BLANKS = {
    "nothing, then the next field": "<p>Name: Ann</p><p>Date of birth:</p><p>Place of birth: Paris</p>",
    "the last field on the page": "<p>Name: Ann</p><p>Date of birth:</p>",
    "underscores": "<p>Date of birth: ____</p><p>Place of birth: Paris</p>",
    "two underscores": "<p>Date of birth: __</p><p>Place of birth: Paris</p>",
    "dots": "<p>Date of birth: ........</p><p>Place of birth: Paris</p>",
    "dots and underscores": "<p>Date of birth: ._._._</p>",
    "an ellipsis": "<p>Date of birth: …</p>",
    "a middle dot": "<p>Date of birth: ·</p>",
    "the printed mask": "<p>Date of birth: __/__/____</p><p>Place of birth: Paris</p>",
    "the mask after underscores": "<p>Date of birth: __/__/____ ____</p>",
    "white space": "<p>Date of birth:   </p><p>Place of birth: Paris</p>",
    "line breaks": "<p>Date of birth:<br><br></p><p>Place of birth: Paris</p>",
    "nbsp": "<p>Date of birth:&nbsp;&nbsp;</p>",
    "an empty element": "<p>Date of birth: <span></span><b></b></p>",
    "one line": "<p>Name: Ann Date of birth: ____ Place of birth: Paris</p>",
    "glued to the next label": "<p>Date of birth: _____Place of birth: ____</p>",
    "the label in capitals": "<p>DATE OF BIRTH:</p><p>Place of birth: Paris</p>",
    "bold label": "<p><b>Date of birth:</b></p><p><b>Place of birth:</b> Paris</p>",
    "another field first": "<p>Place of birth: Paris</p><p>Date of birth:</p><p>Name: Ann</p>",
    "an image description": "<p>Date of birth: <img alt='calendar'></p><p>Place of birth: Paris</p>",
    "an empty input": "<p>Date of birth: <input type=text></p><p>Place of birth: Paris</p>",
    "an empty list item": "<p>Date of birth: </p><ul><li></li></ul>",
    "a glued page": "<p>Dateofbirth:____Placeofbirth:Paris</p>",
    "a table after it, whose first cell is a stop": "<p>Date of birth:</p><table><tr><td>Name:</td><td>Ann</td></tr></table>",
}
FILLED = {
    "a date": "<p>Date of birth: 01/02/1990</p><p>Place of birth: Paris</p>",
    "n/a": "<p>Date of birth: N/A</p><p>Place of birth: Paris</p>",
    "a dash": "<p>Date of birth: -</p><p>Place of birth: Paris</p>",
    "two dashes": "<p>Date of birth: --</p>",
    "none": "<p>Date of birth: none</p>",
    "[blank]": "<p>Date of birth: [blank]</p>",
    "the mask twice": "<p>Date of birth: __/__/____ __/__/____</p>",
    "a mask with a date": "<p>Date of birth: 01/__/____</p>",
    "the last field filled": "<p>Name: Ann</p><p>Date of birth: 5 May</p>",
    "a value glued to the label": "<p>Date of birth:1990</p>",
    "a value on the next line": "<p>Date of birth:</p><p>01/02/1990</p><p>Place of birth: Paris</p>",
    "a value after a leader": "<p>Date of birth: ____ 1990</p>",
    "a checkbox": "<p>Date of birth: <input type=checkbox></p>",
    "a footnote mark": "<p>Date of birth: [1]</p>",
    "a value with the next field's label missing": "<p>Date of birth: Paris</p>",
    "the next field's value, label missing": "<p>Date of birth:</p><p>Paris</p>",
    "a value in a table after it": "<p>Date of birth:</p><table><tr><td>1990</td></tr></table>",
    "a value in an input": "<p>Date of birth: <input value='1990'></p>",
    "a one-line form, filled": "<p>Name: Ann Date of birth: 1990 Place of birth: Paris</p>",
    "markup around a value": "<p>Date of birth: <i>1990</i></p>",
}


@pytest.mark.parametrize("name", BLANKS)
def test_a_blank_field_passes(name):
    assert passes(BLANKS[name]), verdict(BLANKS[name])


@pytest.mark.parametrize("name", FILLED)
def test_a_filled_field_fails(name):
    assert not passes(FILLED[name]), name


def test_a_pass_is_a_plain_present_pass():
    for html in BLANKS.values():
        assert score({"html": html}, gold_of({"content": text(DOB)}, {}))[0].result == "pass"


def test_a_missing_label_fails_with_the_plain_reason():
    ok, why = verdict("<p>Name: Ann</p>")
    assert not ok and "not found" in why


def test_the_label_inside_a_longer_word_fails():
    ok, why = verdict("<p>Surnames: Ann</p>", label="Name", printed=None, stops=[])
    assert not ok and "word edge" in why


def test_the_label_split_over_two_cells_fails():
    ok, why = verdict(rows("<td>Date of</td><td>birth:</td>"))
    assert not ok and "word edge" in why


def test_without_stops_the_region_runs_to_the_end_of_the_page():
    page = "<p>Date of birth:</p><p>Place of birth: Paris</p>"
    assert passes(page) and not passes(page, stops=[])


def test_a_stop_ends_the_region_so_a_later_value_is_not_this_fields():
    assert passes("<p>Date of birth:</p><p>Place of birth: Paris</p><p>Name: Ann</p>")


def test_the_printed_mask_is_allowed_once_and_only_when_named():
    assert passes("<p>Date of birth: __/__/____</p>")
    assert not passes("<p>Date of birth: __/__/____</p>", printed=None)
    assert not passes("<p>Date of birth: __/__/____ __/__/____</p>")
    assert not passes("<p>Date of birth: DD/MM/YYYY</p>")
    assert passes("<p>Date of birth: DD / MM / YYYY</p>", printed="DD / MM / YYYY")


def test_a_copy_inside_a_longer_stop_is_that_stop():
    page = "<p>Last Name: ____</p><p>Name: ____</p>"
    assert passes(page, label="Name:", printed=None, stops=["Last Name:"])
    assert not passes("<p>Last Name: Roe</p><p>Name: Ann</p>", label="Name:", printed=None, stops=["Last Name:"])


def test_a_repeated_label_passes_only_when_every_copy_is_blank():
    assert passes("<p>Date of birth:</p><p>Date of birth: ____</p>")
    assert not passes("<p>Date of birth: 1990</p><p>Date of birth:</p>")
    assert not passes("<p>Date of birth:</p><p>Date of birth: 1990</p>")
    assert not passes("<p>Date of birth: 1990</p><p>Date of birth: 1991</p>")


def test_a_digit_label_is_not_cut_out_of_a_longer_number():
    ok, _ = verdict("<p>Box 12:</p>", label="Box 1", printed=None, stops=[])
    assert not ok
    assert passes("<p>Box 1</p>", label="Box 1", printed=None, stops=[])


def test_markdown_and_html_agree():
    blank = "Name: Ann\n\nDate of birth: \n\nPlace of birth: Paris"
    filled = "Name: Ann\n\nDate of birth: 01/02/1990\n\nPlace of birth: Paris"
    assert passes(markdown.to_html(blank)) and not passes(markdown.to_html(filled))
    table = "| Date of birth: | |\n|---|---|\n| Place of birth: | Paris |"
    assert passes(markdown.to_html(table))
    assert not passes(markdown.to_html(table.replace("| |", "| 1990 |", 1)))


# ---------------------------------------------------------------------- tables: three layouts, both ways

TABLES = {
    # name: (blank page, filled page)
    "two columns": (rows(f"<td>{DOB}</td><td></td>", "<td>Place of birth:</td><td>Paris</td>"),
                    rows(f"<td>{DOB}</td><td>01/02/1990</td>", "<td>Place of birth:</td><td>Paris</td>")),
    "two columns, the mask": (rows(f"<td>{DOB}</td><td>{MASK}</td>"), rows(f"<td>{DOB}</td><td>{MASK} {MASK}</td>")),
    "two columns, leaders": (rows(f"<td>{DOB}</td><td>......</td>"), rows(f"<td>{DOB}</td><td>......  x</td>")),
    "the rest of the cell": (rows(f"<td>{DOB} ____</td><td></td>"), rows(f"<td>{DOB} 5</td><td></td>")),
    "header row": (rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td></td><td>Paris</td>"),
                   rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td>01/02/1990</td><td>Paris</td>")),
    "header row, th": (rows(f"<th>{DOB}</th><th>Place of birth:</th>", "<td></td><td>Paris</td>"),
                       rows(f"<th>{DOB}</th><th>Place of birth:</th>", "<td>1990</td><td>Paris</td>")),
    "header row, a third field": (rows(f"<td>{DOB}</td><td>Name:</td><td>Place of birth:</td>", "<td> </td><td>Ann</td><td>Paris</td>"),
                                  rows(f"<td>{DOB}</td><td>Name:</td><td>Place of birth:</td>", "<td>1990</td><td>Ann</td><td>Paris</td>")),
    "read across": (rows(f"<td>{DOB}</td><td></td><td>Name:</td><td>Ann</td>"),
                    rows(f"<td>{DOB}</td><td>1990</td><td>Name:</td><td>Ann</td>")),
    "the value shifted in": (rows(f"<td>{DOB}</td><td></td>", "<td>Place of birth:</td><td>Paris</td>"),
                             rows(f"<td>{DOB}</td><td>Paris</td>", "<td>Place of birth:</td><td></td>")),
    "a merged label": (f"<table><tr><td rowspan=2>{DOB}</td><td></td></tr><tr><td></td></tr></table>",
                       f"<table><tr><td rowspan=2>{DOB}</td><td></td></tr><tr><td>1990</td></tr></table>"),
    "a merged value": (rows(f"<td>{DOB}</td><td colspan=2></td>"), rows(f"<td>{DOB}</td><td colspan=2>1990</td>")),
    "a short row": (rows(f"<td>{DOB}</td>", "<td>Place of birth:</td><td>Paris</td>"),
                    rows(f"<td>{DOB}</td><td>1990</td>", "<td>Place of birth:</td><td>Paris</td>")),
    "an image": (rows(f"<td>{DOB}</td><td></td>"), rows(f"<td>{DOB}</td><td><img src='a.png'></td>")),
}


@pytest.mark.parametrize("name", TABLES)
def test_a_table_of_each_layout_passes_blank_and_fails_filled(name):
    blank, filled = TABLES[name]
    assert passes(blank), verdict(blank)
    assert not passes(filled), name


def test_the_cell_below_may_be_another_label_or_missing():
    assert passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>"))
    assert passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td>Name:</td><td></td>"))
    assert passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td>Name:</td>"))


def test_a_label_in_the_last_column_reads_the_cell_below_and_passes_with_none():
    assert not passes(rows(f"<td>Name: Ann</td><td>{DOB}</td>", "<td>x</td><td>1990</td>"))
    assert passes(rows(f"<td>Name: Ann</td><td>{DOB}</td>", "<td>x</td><td></td>"))
    assert passes(rows(f"<td>Name: Ann</td><td>{DOB}</td>"))


def test_only_a_cell_that_is_a_whole_label_is_not_a_value():
    # right: a label alone reads the cell below; a label with text after it is a value
    assert passes(rows(f"<td>{DOB}</td><td>Name:</td>", "<td></td><td></td>"))
    assert not passes(rows(f"<td>{DOB}</td><td>Name: Ann</td>"))
    assert not passes(rows(f"<td>{DOB}</td><td>Name: Ann</td>", "<td></td><td></td>"))
    # below: a whole label is no value, a label with text after it is
    assert passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td>Name:</td><td></td>"))
    assert not passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td>Name: Ann</td><td></td>"))
    assert not passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td>1990</td><td></td>"))


def test_a_one_column_table_has_no_value_column():
    assert passes(rows(f"<td>{DOB}</td>", "<td>Name: Ann</td>"))
    assert passes(rows(f"<td>{DOB}</td>", "<td>1990</td>"))    # a blind spot: the next row is not read
    assert not passes(rows(f"<td>{DOB} 1990</td>", "<td>Name: Ann</td>"))


def test_a_table_is_judged_by_its_cells_not_by_reading_order():
    # the label in a cell, a stop later in reading order: the next row's value is not the label's
    assert passes(rows(f"<td>{DOB}</td><td></td>", "<td>Place of birth:</td><td>Paris</td>"))
    # nested tables: the inner table's cell is the label's
    inner = f"<table><tr><td>{DOB}</td><td>1990</td></tr></table>"
    assert not passes(f"<table><tr><td>{inner}</td></tr></table>")


def test_a_paragraph_label_before_a_table_reads_the_tables_text_as_its_region():
    assert not passes(f"<p>{DOB}</p><table><tr><td>1990</td></tr></table>")
    assert passes(f"<p>{DOB}</p><table><tr><td>Name:</td><td>Ann</td></tr></table>")


def test_an_unclosed_or_stray_table_tag_does_not_raise():
    assert passes(f"</table><p>{DOB}</p>")
    assert passes(f"<table><tr><td>{DOB}</td><td></td></tr>")


def test_a_label_in_both_a_cell_and_a_paragraph_passes_only_when_both_are_blank():
    assert passes(f"<p>{DOB}</p>" + rows(f"<td>{DOB}</td><td></td>"))
    assert not passes(f"<p>{DOB} 1990</p>" + rows(f"<td>{DOB}</td><td></td>"))
    assert not passes(f"<p>{DOB}</p>" + rows(f"<td>{DOB}</td><td>1991</td>"))


def test_the_why_names_the_value_and_where():
    assert verdict("<p>Date of birth: 01/02/1990</p><p>Name: Ann</p>")[1] == (
        "'Date of birth:' is followed by '01/02/1990' before the next field")
    assert verdict("<p>Date of birth: 5</p>")[1] == "'Date of birth:' is followed by '5' to the end of the page"
    assert verdict(rows(f"<td>{DOB}</td><td>1990</td>"))[1] == (
        "'Date of birth:' cell's value cell (right) holds '1990'")
    assert verdict(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td>1990</td><td></td>"))[1] == (
        "'Date of birth:' cell's value cell (below) holds '1990'")
    assert verdict(rows(f"<td>{DOB} 5</td><td></td>"))[1] == "'Date of birth:' is followed by '5' in its cell"


def test_a_table_the_cell_reader_cannot_parse_is_read_as_text():
    odd = f"<table><td>{DOB}</td><td></td></table>"
    assert not R.tables.parse(odd)
    assert passes(odd)
    assert not passes(f"<table><td>{DOB}</td><td>1990</td></table>")


@pytest.mark.parametrize("valid", ["", "<table><tr><td>Name:</td><td>Ann</td></tr></table>", "<p>Name: Ann</p>"])
@pytest.mark.parametrize("before", [False, True])
def test_an_unparseable_table_is_read_as_text_whatever_else_is_on_the_page(valid, before):
    def page(inner: str) -> str:
        odd = f"<table><td>{inner}</td><td></td></table>"
        return valid + odd if before else odd + valid
    assert passes(page(DOB))
    assert not passes(f"<table><td>{DOB}</td><td>1990</td></table>" if not before else
                      "<table><tr><td>other</td></tr></table><table><td>" + DOB + "</td><td>1990</td></table>")


# ------------------------------------------------------------------------- every copy, and the region's edges


def test_a_value_before_the_label_fails_unless_another_field_comes_first():
    assert not passes(f"<p>12/03/1985 {DOB} {MASK}</p>")
    assert passes(f"<p>Name: Ann Lee {DOB} {MASK}</p>")    # that value is Name:'s
    assert passes(f"<p>____ {DOB} {MASK}</p>")
    assert verdict(f"<p>12/03/1985 {DOB}</p>")[1] == "'Date of birth:' has '12/03/1985' before it"
    assert not passes(rows(f"<td>12/03/1985 {DOB}</td><td></td>"))
    assert not passes(rows(f"<td>12/03/1985</td><td>{DOB}</td><td></td>"))
    assert passes(rows("<td>Name:</td><td>Ann</td><td>" + DOB + "</td><td></td>"))    # Name:'s value


def test_every_cell_to_the_right_is_read_up_to_another_label():
    assert not passes(rows(f"<td>{DOB}</td><td></td><td>1990</td>"))
    assert passes(rows(f"<td>{DOB}</td><td></td><td></td>"))
    assert passes(rows(f"<td>{DOB}</td><td>Place of birth:</td><td>Paris</td>"))


def test_the_cells_below_are_read_down_to_another_label_when_the_right_is_blank():
    assert not passes(rows(f"<td>{DOB}</td><td></td>", "<td>1990</td><td></td>"))
    assert not passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td></td><td>Paris</td>", "<td>1990</td><td></td>"))
    assert passes(rows(f"<td>{DOB}</td><td></td>", "<td></td><td></td>", "<td>Name:</td><td>Ann</td>"))
    assert passes(rows(f"<td>{DOB}</td><td></td>", "<td>Name:</td><td>Ann</td>"))


def test_the_text_after_a_table_that_ends_with_the_label_is_the_fields_region():
    table = rows(f"<td>{DOB}</td><td></td>")
    assert not passes(table + "<table><tr><td>1990</td></tr></table>")
    assert not passes(table + "<p>1990</p>")
    assert passes(table + "<p>Place of birth: Paris</p>")
    assert passes(table)
    assert passes(rows(f"<td>{DOB}</td><td></td>", "<td>Name:</td><td>Ann</td>") + "<p>footer</p>")    # a label below: not the end
    assert "after its table" in verdict(table + "<p>1990</p>")[1]


def test_a_printed_mask_of_underscores_survives_markdown():
    page = markdown.to_html(f"{DOB} {MASK}\n\nPlace of birth: Paris")
    assert passes(page)
    assert not passes(markdown.to_html(f"{DOB} {MASK} 1990\n\nPlace of birth: Paris"))
    assert not passes(markdown.to_html(f"{DOB} 1990\n\nPlace of birth: Paris"))


def test_a_label_printed_twice_blank_is_faithful_in_every_layout_and_one_filled_copy_fails():
    two = f"{DOB} {MASK} {DOB} {MASK}"
    assert passes(f"<p>{two} Place of birth: Paris</p>")
    assert not passes(f"<p>{DOB} {MASK} {DOB} {MASK} 1990 Place of birth: Paris</p>")
    assert not passes(f"<p>{DOB} {MASK} 1990 {DOB} {MASK} Place of birth: Paris</p>")
    assert passes(rows(f"<td>{DOB}</td><td></td><td>{DOB}</td><td></td>"))
    assert passes(rows(f"<td>{DOB}</td><td></td><td></td><td>{DOB}</td><td></td>"))
    assert not passes(rows(f"<td>{DOB}</td><td></td><td>{DOB}</td><td>1990</td>"))
    assert not passes(rows(f"<td>{DOB}</td><td></td><td>1990</td><td>{DOB}</td><td></td>"))


def test_the_value_may_be_in_the_blank_right_cells_column_below():
    value = rows(f"<td>{DOB}</td><td></td>", "<td></td><td>12/03/1985</td>", "<td>Name:</td><td>Ann Lee</td>")
    assert not passes(value)
    assert passes(value.replace("12/03/1985", ""))
    assert passes(rows(f"<td>{DOB}</td><td></td>", "<td>Name:</td><td>Ann Lee</td>"))
    assert passes(rows(f"<td>{DOB}</td><td>Place of birth:</td>", "<td></td><td>Paris</td>"))


def test_a_one_column_table_does_not_read_below_but_its_tail_is_the_region():
    assert not passes(rows(f"<td>{DOB}</td>") + "<p>1990</p>")
    assert passes(rows(f"<td>{DOB}</td>") + "<p>Place of birth: Paris</p>")
    assert passes(rows(f"<td>{DOB}</td>", "<td>Name:</td>") + "<p>1990</p>")    # a label below: not the end


def test_a_literal_slash_pair_is_not_the_markdown_mask():
    assert not passes(f"<p>{DOB} //</p>")
    assert passes(f"<p>{DOB} {MASK}</p>")
    assert passes(markdown.to_html(f"{DOB} {MASK}"))
    assert not passes(markdown.to_html(f"{DOB} {MASK}") .replace("</p>", " //</p>"))
