"""table_cell's `{"empty": true}` and `{"end": true}` args: what they accept in a gold file, and the verdicts
they give on blank encodings, invented content, shifted and merged cells (docs/scoring/table_cell.md)."""
from __future__ import annotations

import pytest

from omni_parse_bench import score, views
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as gold

EMPTY, END = {"empty": True}, {"end": True}


def text(s: str) -> dict:
    return {"text": s, "max_diffs": 0}


def gold_of(args: dict, test_type: str = "table_cell") -> tuple[gold.Test, ...]:
    return gold.parse("p", {"tests": [{"id": "a", "test_type": test_type, "output_type": "html",
                                       "derivation": "authored", "tags": [], "args": args, "settings": {}}]})


def verdict(args: dict, html: str) -> bool:
    return score({"html": html}, gold_of(args))[0].result == "pass"


def rows(*rs: str) -> str:
    return "<table>" + "".join(f"<tr>{r}</tr>" for r in rs) + "</table>"


HEAD = "<th>Item</th><th>Q1</th><th>Q2</th>"
ROW = "<td>Rent</td><td>100</td>{}"
RIGHT = {"cell": text("100"), "right": EMPTY, "top_heading": text("Q1")}


# ----------------------------------------------------------------------------------------- the schema


@pytest.mark.parametrize("role", ["up", "down", "left", "right"])
@pytest.mark.parametrize("flag", [EMPTY, END])
def test_a_flag_is_an_arg_of_a_neighbour(role, flag):
    t, = gold_of({"cell": text("100"), role: flag})
    assert t.params.shapes == {role: next(iter(flag))}
    assert role not in t.params.relations


@pytest.mark.parametrize("role", ["cell", "top_heading", "left_heading", "right_heading", "section"])
@pytest.mark.parametrize("flag", [EMPTY, END])
def test_a_flag_is_refused_on_any_other_role(role, flag):
    with pytest.raises(ValueError, match="table_cell's"):
        gold_of({"cell": text("100"), role: flag} if role != "cell" else {"cell": flag})


@pytest.mark.parametrize("role", ["headings", "row_groups"])
def test_a_flag_is_refused_in_a_list_role(role):
    with pytest.raises(ValueError):
        gold_of({"cell": text("100"), role: [EMPTY]})


@pytest.mark.parametrize("test_type", ["present", "repeat", "layout_kind"])
def test_a_flag_is_refused_on_other_test_types(test_type):
    with pytest.raises(ValueError):
        gold_of({"content": EMPTY}, test_type)


@pytest.mark.parametrize("bad", [{"empty": False}, {"end": False}, {"empty": 1}, {"empty": "true"},
                                 {"empty": True, "end": True}, {"empty": True, "text": "x"},
                                 {"empty": True, "max_diffs": 0}, {"blank": True}])
def test_a_malformed_flag_is_refused(bad):
    with pytest.raises(ValueError):
        gold_of({"cell": text("100"), "right": bad})


def test_a_flag_is_no_arg_kind_and_does_not_set_max_diffs():
    assert gold.arg_kinds("table_cell", {"cell": text("100"), "right": EMPTY, "down": END}) == ("text",)
    # `cell` alone fixes max_diffs; a text neighbour must still share it.
    with pytest.raises(ValueError, match="max_diffs"):
        gold_of({"cell": text("100"), "right": EMPTY, "up": {"text": "xxxx", "max_diffs": 1}})


def test_a_flag_and_a_text_role_combine():
    t, = gold_of({"cell": text("100"), "left": text("Rent"), "right": EMPTY, "down": END,
                   "top_heading": text("Q1")})
    assert t.params.relations == {"left": "Rent", "top_heading": "Q1"}
    assert t.params.shapes == {"right": "empty", "down": "end"}


# ------------------------------------------------------------------------------------- empty: verdicts


@pytest.mark.parametrize("blank", ["<td></td>", "<td> </td>", "<td>&nbsp;</td>", "<td><br></td>",
                                   "<td>​</td>", "<td><p></p></td>", "<td>...</td>", "<td>.....</td>",
                                   "<td><b></b></td>", "", "<th></th>"])
def test_every_blank_encoding_is_empty(blank):
    assert verdict(RIGHT, rows(HEAD, ROW.format(blank)))


@pytest.mark.parametrize("filled", ["<td>100</td>", "<td>200</td>", "<td>0</td>", "<td>-</td>",
                                    "<td><img alt='chart'></td>", "<td>x</td>", "<th>Q2</th>"])
def test_any_text_in_the_cell_is_not_empty(filled):
    assert not verdict(RIGHT, rows(HEAD, ROW.format(filled)))


def test_a_text_arg_reads_the_stand_in_but_empty_does_not():
    html = rows(HEAD, ROW.format("<td>100</td>"))
    # Left of an empty cell reads the value above it (a heading), so a copy passes a text arg...
    assert score({"html": rows(HEAD, "<td>Rent</td><td>100</td><td></td>")},
                 gold_of({"cell": text("100"), "right": text("Q2")}))[0].result == "pass"
    # ...and the same copy of the neighbour fails `empty`.
    assert not verdict(RIGHT, html)


def test_a_missing_trailing_cell_is_empty_but_the_table_edge_is_not():
    assert verdict(RIGHT, rows(HEAD, ROW.format("")))
    assert not verdict(RIGHT, rows("<th>Item</th><th>Q1</th>", ROW.format("")))   # no third column anywhere


def test_empty_on_each_side():
    t = rows("<td></td><td>a</td><td></td>", "<td>b</td><td>X</td><td>c</td>", "<td></td><td>d</td><td></td>")
    assert not verdict({"cell": text("X"), "left": EMPTY}, t)
    assert verdict({"cell": text("a"), "left": EMPTY, "right": EMPTY}, t)
    assert verdict({"cell": text("a"), "up": END, "left": EMPTY}, t)
    assert not verdict({"cell": text("d"), "right": EMPTY, "up": EMPTY}, t)
    assert verdict({"cell": text("d"), "right": EMPTY, "left": EMPTY, "down": END}, t)


def test_the_mirror_swaps_left_and_right():
    out = rows(HEAD, "<td>Rent</td><td></td><td>100</td>")
    assert verdict({"cell": text("100"), "left": EMPTY}, out)
    assert not verdict({"cell": text("100"), "right": EMPTY}, out)
    out = rows(HEAD, "<td>Rent</td><td>100</td><td></td>")
    assert verdict({"cell": text("100"), "right": EMPTY}, out)
    assert not verdict({"cell": text("100"), "left": EMPTY}, out)


def test_values_shifted_by_one_row_or_column_fail():
    gold_args = {"cell": text("100"), "right": EMPTY, "top_heading": text("Q1")}
    assert verdict(gold_args, rows(HEAD, ROW.format("<td></td>")))
    assert not verdict(gold_args, rows(HEAD, "<td>Rent</td><td></td><td>100</td>"))      # shifted right
    assert not verdict(gold_args, rows(HEAD, "<td>100</td><td></td><td></td>"))          # shifted left
    assert not verdict(gold_args, rows(HEAD, "<td></td><td>100</td><td>x</td>"))
    assert not verdict(gold_args, rows(HEAD, "<td>Rent</td><td>100</td><td></td>").replace("Q1", "Q0"))


def test_a_colspan_covering_the_slot_fails():
    assert not verdict(RIGHT, rows(HEAD, "<td>Rent</td><td colspan=2>100</td>"))
    # a neighbour cell that spans the slot with text fails too
    swallowed = rows(HEAD, "<td>Rent</td><td colspan=2>100</td>")
    assert not verdict({"cell": text("Rent"), "right": EMPTY}, swallowed)
    # but a blank spanning cell is blank
    assert verdict({"cell": text("Rent"), "right": EMPTY}, rows(HEAD, "<td>Rent</td><td colspan=2></td>"))


def test_a_cell_spanning_rows_needs_every_neighbour_blank():
    args = {"cell": text("Rent"), "right": EMPTY}
    assert verdict(args, rows("<td rowspan=2>Rent</td><td></td>", "<td>&nbsp;</td>"))
    assert not verdict(args, rows("<td rowspan=2>Rent</td><td></td>", "<td>5</td>"))
    assert not verdict(args, rows("<td rowspan=2>Rent</td><td>5</td>", "<td></td>"))


def test_empty_up_and_down_read_the_adjacent_slot_not_the_stand_in():
    args = {"cell": text("7"), "up": EMPTY}
    assert verdict(args, rows("<td>5</td><td></td>", "<td>q</td><td>7</td>"))
    assert not verdict(args, rows("<td>5</td><td>5</td>", "<td>q</td><td>7</td>"))
    assert not verdict({"cell": text("5"), "down": EMPTY}, rows("<td>5</td>", "<td>5</td>"))
    assert verdict({"cell": text("5"), "down": EMPTY}, rows("<td>5</td>", "<td></td>"))


def test_a_header_with_empty_cells_beside_it_tells_merged_from_flat():
    flat = "<table><tr><th>Group</th><th></th></tr><tr><td>5</td><td>6</td></tr></table>"
    merged = "<table><tr><th colspan=2>Group</th></tr><tr><td>5</td><td>6</td></tr></table>"
    args = {"cell": text("Group"), "right": EMPTY}
    assert verdict(args, flat) and not verdict(args, merged)


def test_empty_follows_the_html_order_in_a_right_to_left_table():
    out = "<table dir='rtl'><tr><th>المجموع</th><td>1,240</td><td></td></tr></table>"
    assert verdict({"cell": text("1,240"), "right": EMPTY}, out)
    assert not verdict({"cell": text("1,240"), "left": EMPTY}, out)


def test_empty_reasons():
    ok, why = R.table_cell(gold_of({"cell": text("100"), "right": EMPTY})[0].params,
                           views.html(rows(HEAD, ROW.format("<td>200</td>"))))
    assert not ok and "right '200' isn't empty" in why
    ok, why = R.table_cell(gold_of({"cell": text("80"), "right": EMPTY})[0].params,
                           views.html(rows(HEAD, "<td>a</td><td>b</td><td>80</td>")))
    assert not ok and "no right cell" in why


# --------------------------------------------------------------------------------------- end: verdicts

BODY = ["<td>Rent</td><td>100</td>", "<td>Fuel</td><td>70</td>"]
LAST = {"cell": text("70"), "down": END, "right": END}


def test_the_last_row_and_column_end():
    assert verdict(LAST, rows(*BODY))
    assert not verdict({"cell": text("100"), "down": END}, rows(*BODY))
    assert not verdict({"cell": text("Fuel"), "right": END}, rows(*BODY))


@pytest.mark.parametrize("extra", ["<tr><td></td><td></td></tr>", "<tr><td>&nbsp;</td><td><br></td></tr>",
                                   "<tr></tr><tr><td>...</td></tr>"])
def test_empty_trailing_rows_pass(extra):
    assert verdict(LAST, rows(*BODY) .replace("</table>", extra + "</table>"))


def test_an_empty_trailing_column_passes():
    assert verdict(LAST, rows("<td>Rent</td><td>100</td><td></td>", "<td>Fuel</td><td>70</td><td></td>"))
    assert verdict(LAST, rows("<td>Rent</td><td>100</td><td></td>", "<td>Fuel</td><td>70</td>"))


@pytest.mark.parametrize("row", ["<tr><td>Tax</td><td>9</td></tr>", "<tr><td></td><td>9</td></tr>",
                                 "<tr><td>9</td></tr>", "<tr><td></td><td></td></tr><tr><td>x</td></tr>"])
def test_an_invented_row_fails_end(row):
    ok = verdict({"cell": text("70"), "down": END}, rows(*BODY).replace("</table>", row + "</table>"))
    assert not ok


@pytest.mark.parametrize("col", ["<td>9</td>", "<td></td><td>9</td>"])
def test_an_invented_column_fails_end(col):
    out = rows("<td>Rent</td><td>100</td>" + col, "<td>Fuel</td><td>70</td>")
    assert not verdict({"cell": text("70"), "right": END}, out)
    assert not verdict({"cell": text("100"), "right": END}, out)


def test_an_invented_header_row_or_label_column_fails_up_and_left_end():
    assert verdict({"cell": text("Item"), "up": END, "left": END}, rows(HEAD, ROW.format("")))
    assert not verdict({"cell": text("Item"), "up": END}, rows("<td>Report</td>", HEAD))
    assert not verdict({"cell": text("Item"), "left": END}, rows("<td>#</td>" + HEAD))


def test_end_reads_any_column_for_down_and_any_row_for_right():
    out = rows("<td>a</td><td>b</td>", "<td></td><td>c</td>")
    assert not verdict({"cell": text("a"), "down": END}, out)          # `c` is in another column
    assert verdict({"cell": text("c"), "down": END}, out)
    assert not verdict({"cell": text("a"), "right": END}, rows("<td>a</td><td></td>", "<td>b</td><td>c</td>"))


def test_a_cell_spanning_rows_or_columns_ends_past_its_last_slot():
    assert verdict({"cell": text("m"), "down": END}, rows("<td rowspan=2>m</td><td>1</td>", "<td>2</td>"))
    assert not verdict({"cell": text("m"), "down": END},
                       rows("<td rowspan=2>m</td><td>1</td>", "<td>2</td>", "<td>3</td>"))
    assert verdict({"cell": text("m"), "right": END}, rows("<td colspan=2>m</td>", "<td>1</td><td></td>"))
    assert not verdict({"cell": text("m"), "right": END},
                       rows("<td colspan=2>m</td>", "<td>1</td><td>2</td><td>3</td>"))


def test_end_reasons_name_the_row_or_column():
    t = gold_of({"cell": text("70"), "down": END})[0].params
    ok, why = R.table_cell(t, views.html(rows(*BODY, "<td>Tax</td><td>9</td>")))
    assert not ok and "down: row 3 holds 'tax', '9'" in why
    t = gold_of({"cell": text("70"), "right": END})[0].params
    ok, why = R.table_cell(t, views.html(rows("<td>Fuel</td><td>70</td><td>x</td>")))
    assert not ok and "right: column 3 holds 'x'" in why


@pytest.mark.parametrize("figure", ["<img src=chart.png>", "<img alt=''>", "<img alt='chart'>", "<svg></svg>",
                                    "<p><img src=a.png></p>", "<picture><img src=a.png></picture>"])
def test_a_figure_is_not_empty_with_or_without_alt_text(figure):
    assert not verdict(RIGHT, rows(HEAD, ROW.format(f"<td>{figure}</td>")))
    below = rows("<td>Fuel</td><td>70</td>", f"<td></td><td>{figure}</td>")
    assert not verdict({"cell": text("70"), "down": END}, below)
    assert not verdict({"cell": text("70"), "right": END}, rows(f"<td>70</td><td>{figure}</td>"))
    # the same table without the figure passes both
    assert verdict({"cell": text("70"), "down": END}, rows("<td>Fuel</td><td>70</td>", "<td></td><td></td>"))


def test_a_figure_does_not_change_a_text_verdict():
    plain = rows(HEAD, ROW.format("<td></td>"))
    drawn = rows(HEAD, ROW.format("<td><img src=a.png></td>"))
    t = {"cell": text("100"), "right": text("Q2")}
    assert verdict(t, plain) == verdict(t, drawn)
