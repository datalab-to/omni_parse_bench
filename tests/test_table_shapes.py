# ruff: noqa: E501
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


# ------------------------------------------------------------------ every matching cell, every continuing table

ONE = {"cell": text("100"), "right": EMPTY}
TWO = f"<table><tr>{HEAD}</tr><tr>{ROW.format('<td></td>')}</tr><tr><td>Fuel</td><td>70</td><td>80</td></tr></table>"


def test_every_cell_that_matches_must_be_empty_beside_it():
    filled = TWO.replace("<td></td>", "<td>200</td>")
    assert verdict(ONE, TWO) and verdict(ONE, TWO + TWO)
    assert not verdict(ONE, TWO + filled) and not verdict(ONE, filled + TWO)
    assert not verdict(ONE, rows(HEAD, ROW.format("<td></td>"), "<td>Fuel</td><td>100</td><td>200</td>"))
    assert verdict(ONE, rows(HEAD, ROW.format("<td></td>"), "<td>Fuel</td><td>100</td><td></td>"))


def test_a_cell_matching_by_one_line_must_hold_nothing_more():
    assert not verdict(ONE, TWO.replace("<td>100</td>", "<td>100<br>200</td>"))
    assert verdict({"cell": text("100"), "right": EMPTY, "top_heading": text("Q1")}, TWO)


def test_a_relation_picks_which_cells_must_hold_the_shape():
    two = rows(HEAD, ROW.format("<td></td>"), "<td>Fuel</td><td>100</td><td>200</td>")
    assert verdict({"cell": text("100"), "left": text("Rent"), "right": EMPTY}, two)
    assert not verdict({"cell": text("100"), "left": text("Fuel"), "right": EMPTY}, two)


def test_end_reads_a_table_that_goes_on_from_the_anchors():
    cont = "<table><tr><td>Tax</td><td>9</td><td>8</td></tr></table>"
    args = {"cell": text("70"), "down": END}
    assert verdict(args, TWO)
    assert not verdict(args, TWO + cont) and not verdict(args, TWO + "\n" + cont)
    assert verdict(args, TWO + f"<table><tr>{HEAD}</tr><tr><td>Tax</td><td>9</td><td>8</td></tr></table>")    # a limit: a second table with a header
    assert verdict(args, TWO + TWO) and verdict(args, TWO + TWO.replace("100", "110").replace("70", "71"))
    assert not verdict(args, TWO + TWO.replace("<td>80</td>", "<td>80</td></tr><tr><td>Tax</td><td>9</td><td>8</td>"))
    assert not verdict(args, TWO + f"<div>{cont}</div>") and not verdict(args, TWO + f"<!-- x -->{cont}")
    assert not verdict(args, f"<div>{TWO}</div><div>{cont}</div>") and not verdict(args, TWO + f"<p></p>\n{cont}")
    assert verdict(args, TWO + "<p>Note</p>" + cont) and verdict(args, TWO + f"<div><p>Note</p>{cont}</div>")
    assert verdict(args, TWO + "<p>Note</p>" + cont)
    assert verdict(args, TWO + "<table><tr><th>Cost</th><th>Q3</th><th>Q4</th></tr><tr><td>Tax</td><td>9</td><td>8</td></tr></table>")
    assert verdict(args, TWO + "<table><tr><td>Tax</td><td>9</td></tr></table>")
    assert "continuing" in score({"html": TWO + cont}, gold_of(args))[0].why


def test_end_up_and_left_read_the_table_before_a_continuation():
    first = "<table><tr><td>Tax</td><td>9</td><td>8</td></tr></table>"
    assert not verdict({"cell": text("70"), "up": END}, rows(HEAD, "<td>Fuel</td><td>70</td><td>80</td>"))
    assert not verdict({"cell": text("Fuel"), "up": END}, first + rows("<td>Fuel</td><td>70</td><td>80</td>"))
    assert verdict({"cell": text("Fuel"), "up": END}, first + "<p>x</p>" + rows("<td>Fuel</td><td>70</td><td>80</td>"))


def test_a_second_table_excuses_only_a_full_anchor_candidate():
    extra = "<table><tr><td>Tax</td><td>70</td><td>9</td></tr></table>"
    args = {"cell": text("70"), "down": END}
    assert verdict(args, TWO + extra)    # a second full candidate (no relations): judged as its own table, ends
    left = {"cell": text("70"), "left": text("Fuel"), "down": END}
    assert not verdict(left, TWO + extra)    # not the anchor as the test names it: an invented continuation
    assert verdict(left, TWO + extra.replace("Tax", "Fuel"))    # a second Fuel / 70 row ends too


def test_invisible_text_and_row_headers_do_not_change_what_goes_on():
    cont = "<table><tr><td>Tax</td><td>9</td><td>8</td></tr></table>"
    args = {"cell": text("70"), "down": END}
    assert not verdict(args, TWO + "<script>void 0;</script><style>p{}</style><template>x</template>" + cont)
    assert not verdict(args, TWO + "<table><tr><th scope=row>Tax</th><td>9</td><td>8</td></tr></table>")
    assert verdict(args, TWO + "<p>Note</p>" + cont)


def test_a_blank_corner_before_column_headers_is_a_header_row_and_row_headers_are_not():
    args = {"cell": text("70"), "down": END}
    corner = "<table><tr><td></td><th scope=col>Plan</th><th scope=col>Actual</th></tr><tr><td>Tax</td><td>9</td><td>8</td></tr></table>"
    assert verdict(args, TWO + corner)    # an independent table with a header row
    assert verdict(args, TWO + corner.replace("<td></td>", "<td><br></td>"))
    rowhead = "<table><tr><th scope=row>Tax</th><th scope=row>9</th><th scope=row>8</th></tr></table>"
    assert not verdict(args, TWO + rowhead)
    assert not verdict(args, TWO + "<table><tr><th scope=row>Tax</th><td>9</td><td>8</td></tr></table>")
    assert not verdict(args, TWO + "<table><tr><th>Tax</th><td>9</td><td>8</td></tr></table>")


def test_what_a_page_does_not_draw_is_not_between_tables():
    cont = "<table><tr><td>Tax</td><td>9</td><td>8</td></tr></table>"
    args = {"cell": text("70"), "down": END}
    for hidden in ("<template><span>Hidden</span></template>", "<template><img src=x></template>",
                   "<script>1</script>", "<style>p{}</style>", "<template><div><p>deep</p></div></template>"):
        assert not verdict(args, TWO + hidden + cont), hidden
    assert verdict(args, TWO + "<template><table><tr><td>a</td><td>b</td><td>c</td></tr></table></template>")
    assert not verdict(args, TWO + "<template><table><tr><td>a</td><td>b</td><td>c</td></tr></table></template>" + cont)


def test_a_table_the_page_does_not_draw_is_not_an_anchor_of_a_shape_guard():
    args = {"cell": text("70"), "left": text("Fuel"), "down": END}
    hidden = "<template>" + TWO.replace("</table>", "<tr><td>Tax</td><td>9</td><td>8</td></tr></table>") + "</template>"
    assert verdict(args, TWO + hidden)
    assert not verdict(args, hidden)    # its anchor is not drawn
    assert not verdict({"cell": text("100"), "right": EMPTY}, hidden)
    assert verdict({"cell": text("70")}, hidden)    # a plain cell test keeps reading it
