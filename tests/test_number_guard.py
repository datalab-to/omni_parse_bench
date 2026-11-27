"""The number guard: an edit budget never pays for a digit or a minus sign, in `present`, `order` and
`table_cell`; every other edit is still paid by it (docs/scoring/*.md, "Numbers are exact")."""
import pytest

from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners as R


def present(gold: str, page: str, md: int) -> bool:
    return R.present(R.Present(R.Text(gold, md)), views.html(f"<p>{page}</p>"))[0]


def order(before: str, after: str, page: str, md: int) -> bool:
    return R.order(R.Order(before, after, md), views.html(page))[0]


def cell(gold: str, page: str, md: int, **relations) -> bool:
    page = f"<table><tr><td>{page}</td></tr></table>"
    return R.table_cell(R.TableCell(gold, relations, md), views.html(page))[0]


def all_types(gold: str, page: str, md: int) -> list[bool]:
    """The verdict of each type on a page that writes `page` where the test's string is `gold`."""
    return [present(gold, page, md), order(gold, "zzzz", f"<p>{page}</p><p>zzzz</p>", md),
            cell(gold, page, md)]


@pytest.mark.parametrize("md", [1, 2, 3])
@pytest.mark.parametrize("gold, wrong", [
    ("Total 1982 here", "Total 1983 here"),          # a digit changed
    ("Total 1982 here", "Total 1928 here"),          # digits transposed
    ("Total 12 here", "Total 1.2 here"),             # a decimal point inserted
    ("Total 1.2 here", "Total 12 here"),             # a decimal point dropped
    ("Total 1,240 here", "Total 1240 here"),         # a separator dropped
    ("Total 12 here", "Total 120 here"),             # a digit added
    ("Total 12 here", "Total 1 2 here"),             # a number split
    ("Total 1 2 here", "Total 12 here"),             # two numbers joined
    ("Total 12 here", "Total  here"),                # a number dropped
])
def test_a_budget_never_pays_for_a_digit(gold, wrong, md):
    assert all(all_types(gold, gold, md))
    assert not any(all_types(gold, wrong, md)), (gold, wrong, md)


@pytest.mark.parametrize("md", [1, 2, 3])
@pytest.mark.parametrize("gold, wrong", [
    ("net -5 total", "net 5 total"), ("net 5 total", "net -5 total"), ("(-5) margin", "(5) margin"),
    ("x = −5 kg", "x = 5 kg"), ("-5 net", "5 net"), ("net 5 total", "net −5 total"),
])
def test_a_budget_never_pays_for_a_minus_sign(gold, wrong, md):
    assert all(all_types(gold, gold, md))
    assert not any(all_types(gold, wrong, md)), (gold, wrong, md)


@pytest.mark.parametrize("gold, same", [("net -5 total", "net −5 total"), ("net -5 total", "net –5 total"),
                                        ("net −5 total", "net -5 total")])
def test_a_minus_sign_is_one_sign_in_any_spelling(gold, same):
    assert all(all_types(gold, same, 0)) and all(all_types(gold, same, 2))


@pytest.mark.parametrize("gold, page", [
    ("table 2026-11-26 ok", "table 2026 11-26 ok"),     # a date: a hyphen between figures
    ("see A-12 and B-7", "see A12 and B-7"),            # an id: a hyphen after a letter
    ("pages 1-2 here", "pages 1 2 here"),               # a range
    ("COVID-19 cases", "COVID19 cases"),
    ("3 - 2 = 1", "3 2 = 1"),                           # a spaced dash is not a sign
])
def test_a_hyphen_between_figures_or_after_a_letter_is_not_a_sign(gold, page):
    assert all(all_types(gold, gold, 0))
    assert all(all_types(gold, page, 1)), (gold, page)              # the hyphen costs an edit
    assert not any(all_types(gold, page, 0)), (gold, page)


@pytest.mark.parametrize("md", [1, 2, 3])
@pytest.mark.parametrize("gold, page", [
    ("Total due 1,240 units", "Totel due 1,240 units"), ("Total due 1,240 units", "Total due 1,240 unts"),
    ("ratio of 3.5 to 12 cells", "ratio of 3.5 to 12 cels"), ("dose -4.8 mg daily", "dose -4.8 mg dally"),
])
def test_a_letter_edit_within_the_budget_still_passes(gold, page, md):
    assert all(all_types(gold, page, md)), (gold, page, md)


def test_the_neighbors_headings_section_and_row_groups_of_a_cell_are_exact_too():
    def table(up="x 12", head="Total 2024", sect="Cohort 1982", group="Arm 7"):
        return (f"<table><tr><td></td><th>{head}</th></tr><tr><td colspan=2>{sect}</td></tr>"
                f"<tr><td></td><td>{up}</td></tr><tr><td>{group}</td><td>a</td></tr></table>")

    def passes(t, page):
        return R.table_cell(t, views.html(page))[0]

    assert passes(R.TableCell("a", {"up": "x 12"}, 1), table())
    assert not passes(R.TableCell("a", {"up": "x 13"}, 1), table())
    assert passes(R.TableCell("a", {"up": "x 12"}, 1, headings=("Totel 2024",)), table())
    assert not passes(R.TableCell("a", {"up": "x 12"}, 1, headings=("Total 2025",)), table())
    assert passes(R.TableCell("a", {}, 1, section="Cohort 1982"), table())
    assert not passes(R.TableCell("a", {}, 1, section="Cohort 1983"), table())
    assert passes(R.TableCell("a", {}, 1, row_groups=("Ar 7",)), table())
    assert not passes(R.TableCell("a", {}, 1, row_groups=("Arm 8",)), table())


def test_the_why_says_a_number_differs():
    ok, why = R.table_cell(R.TableCell("a", {"up": "Total 12"}, 1),
                           views.html("<table><tr><td>Total 13</td></tr><tr><td>a</td></tr></table>"))
    assert not ok and "other numbers" in why
    ok, why = R.order(R.Order("Total: 40", "ZZZ", 0), views.html("<p>Total: 400</p><p>ZZZ</p>"))
    assert not ok and "longer number" in why


def test_an_order_pair_is_found_with_exact_numbers_in_either_order_of_spacing():
    assert order("Alpha 1", "Beta 2", "<p>Alpha 1</p><p>Beta 2</p>", 1)
    assert not order("Alpha 1", "Beta 2", "<p>Beta 2</p><p>Alpha 1</p>", 1)           # reversed
    assert not order("Alpha 1", "Beta 2", "<p>Alpha 1</p><p>Beta 3</p>", 1)           # a digit
    assert order("To tal 12", "ZZZ", "<p>Total12</p><p>ZZZ</p>", 1)                   # squeezed
    assert not order("12 500", "ZZZ", "<p>1 2500</p><p>ZZZ</p>", 1)                   # squeezed, joined
    assert order("Alpha 12", "Beta", "<p>x 13 y</p><p>Alpha 12</p><p>Beta</p>", 1)    # another 13 elsewhere


def test_a_gold_without_a_digit_is_not_guarded():
    # As in `present`: the rule is about the numbers of a gold that has one, so a figure added to a string
    # that has none is paid by the budget like any other characters.
    assert all(all_types("Total here", "Total 12 here", 3))


@pytest.mark.parametrize("gold, page", [
    ("周环变化 -0.1% 较", "周环变化-0.1% 较"),         # a Chinese text puts no space before its minus
    ("周环变化-0.1% 较", "周环变化 -0.1% 较"),
    ("mM kg-1 24 h-1", "mM kg -1 24 h -1"),             # a unit exponent spaced by the page
    ("0.010 mol·kg-1 的", "0.010 mol·kg -1 的"),
])
def test_a_minus_is_kept_whatever_the_spacing(gold, page):
    assert all(all_types(gold, page, 0)), (gold, page)


@pytest.mark.parametrize("gold, page", [
    ("周环变化 -0.1% 较", "周环变化 0.1% 较"),
    ("周环变化 0.1% 较", "周环变化-0.1% 较"),
])
def test_a_lost_or_added_minus_still_fails_after_a_cjk_character(gold, page):
    assert not any(all_types(gold, page, 2)), (gold, page)


@pytest.mark.parametrize("gold, page, kept", [
    ("− 0.756", "−0.756", True), ("− 0.756", "- 0.756", True), ("− 0.756", "0.756", False),
    ("0.756", "− 0.756", False), ("(− 5) net", "(-5) net", True), ("(− 5) net", "(5) net", False),
])
def test_a_spaced_minus_at_the_start_of_a_cell_or_after_a_bracket_is_a_sign(gold, page, kept):
    got = cell(gold, page, 1)
    assert got == kept, (gold, page)


def test_a_list_marker_before_a_number_is_no_sign_in_a_page_text():
    assert all(all_types("12", "- 12", 0)[:2]), "a list item"


@pytest.mark.parametrize("gold, lost", [("−11.7–11.8", "11.7–11.8"), ("−8.054–8.054", "8.054–8.054"),
                                         ("a -5 to 5-5", "a 5 to 5-5")])
def test_a_signed_number_that_shares_digits_with_a_hyphenated_one_is_kept(gold, lost):
    assert all(all_types(gold, gold, 0)) and all(all_types(gold, gold, 2))
    assert not any(all_types(gold, lost, 1)), gold


@pytest.mark.parametrize("gold, lost", [("rate 1e-3 per", "rate 1e3 per"), ("p 2.5E-4 ok", "p 2.5E4 ok")])
def test_the_sign_of_an_exponent_is_kept(gold, lost):
    assert all(all_types(gold, gold, 0))
    assert not any(all_types(gold, lost, 1)), gold


@pytest.mark.parametrize("gold, page", [
    ("rate 1.2 per", "rate 1,2 per"),          # a comma for the decimal point
    ("rate 1,2 per", "rate 1.2 per"),
    ("rate 1.2 per", "rate 12 per"),            # the point dropped
    ("rate 12 per", "rate 1.2 per"),            # a point inserted
    ("rate 1.2 per", "rate 1 2 per"),           # replaced by a space
    ("rate 1.25 per", "rate 12.5 per"),         # the point moved
    ("rate 1,240 per", "rate 1.240 per"),       # a thousands comma for a point
    ("rate 1,240 per", "rate 1240 per"),        # separators stay as written
    ("area .5 ha", "area 5 ha"), ("area 5 ha", "area .5 ha"), ("area .5 ha", "area 0.5 ha"),
])
@pytest.mark.parametrize("md", [1, 2, 3])
def test_a_budget_never_pays_for_a_decimal_separator(gold, page, md):
    assert all(all_types(gold, gold, md))
    assert not any(all_types(gold, page, md)), (gold, page, md)


@pytest.mark.parametrize("gold, lost", [
    ("dose +1.55 mg", "dose 1.55 mg"), ("dose ±0.3 mg", "dose 0.3 mg"), ("(+5) and", "(5) and"),
    ("+1.55", "1.55"), ("x = +5 ok", "x = 5 ok"),
])
@pytest.mark.parametrize("md", [1, 2, 3])
def test_a_plus_or_plus_minus_sign_is_kept_and_not_added(gold, lost, md):
    assert all(all_types(gold, gold, md))
    assert not any(all_types(gold, lost, md)), (gold, lost, md)
    assert not any(all_types(lost, gold, md)), (lost, gold, md)


@pytest.mark.parametrize("gold, page", [("A+5 here", "A5 here"), ("n=1+ x", "n=1 x")])
def test_a_plus_after_a_letter_or_digit_is_no_sign(gold, page):
    assert all(all_types(gold, page, 1))


@pytest.mark.parametrize("gold, page", [("area .5 ha", "area .5 ha"), ("total, .5", "total, .5"),
                                        ("A.5 here", "A.5 here")])
def test_a_leading_point_number_matches_itself(gold, page):
    assert all(all_types(gold, page, 0))


@pytest.mark.parametrize("gold, page", [
    ("december 7, 2016 here", "december 7,2016 here"),       # a comma that is no thousands mark
    ("said 'ok'. 2 men", "said 'ok'.2 men"),                  # a full stop before a digit is no leading point
    ("end of it. 5 more", "end of it.5 more"),
])
def test_a_missing_space_after_a_comma_or_full_stop_is_not_a_number_change(gold, page):
    assert all(all_types(gold, page, 1)), (gold, page)


@pytest.mark.parametrize("gold, page", [
    ("conc 0.100 mol·dm -3 here", "conc 0.100 mol·dm-3 here"),   # a unit exponent the page does not space
    ("conc 0.100 mol·dm-3 here", "conc 0.100 mol·dm -3 here"),
    ("shall hold 6% ± 2% here", "shall hold 6% ±2% here"),      # a plus-minus between two values is no sign
    ("a 0.2 ± 0.1 b", "a 0.2 ±0.1 b"),
])
def test_spacing_around_a_unit_exponent_or_a_plus_minus_between_values_is_free(gold, page):
    assert all(all_types(gold, page, 0)) or all(all_types(gold, page, 1)), (gold, page)
    assert all(all_types(gold, page, 1)), (gold, page)


@pytest.mark.parametrize("gold, lost", [("conc 0.100 mol·dm -3 here", "conc 0.100 mol·dm 3 here"),
                                        ("a ±0.1 b", "a 0.1 b")])
def test_a_lost_sign_still_fails_with_the_spacing_tolerance(gold, lost):
    assert not any(all_types(gold, lost, 2)), (gold, lost)


@pytest.mark.parametrize("gold, lost", [
    ("net -$1,234 total", "net $1,234 total"), ("net −€5.5 total", "net €5.5 total"),
    ("(−$5) net", "($5) net"),
    ("loss -£5 here", "loss £5 here"), ("-¥500 paid", "¥500 paid"), ("-₹12 paid", "₹12 paid"),
    ("net $-1,234 total", "net $1,234 total"), ("net +$5 total", "net $5 total"),
])
@pytest.mark.parametrize("md", [1, 2, 3])
def test_a_sign_before_a_currency_symbol_is_kept_and_not_added(gold, lost, md):
    assert all(all_types(gold, gold, md))
    assert not any(all_types(gold, lost, md)), (gold, lost, md)
    assert not any(all_types(lost, gold, md)), (lost, gold, md)


@pytest.mark.parametrize("gold, page", [
    ("Case A-5 and 5 units", "Case A-5 and -5 units"),        # a sign invented beside a hyphenated figure
    ("A-5 vs 5 mg", "A-5 vs -5 mg"),
])
@pytest.mark.parametrize("md", [1, 2])
def test_an_invented_sign_is_not_taken_for_a_hyphen(gold, page, md):
    assert not any(all_types(gold, page, md)), (gold, page, md)


@pytest.mark.parametrize("gold, page", [("−0.756", "− 0.756"), ("net −5 total", "net − 5 total"),
                                        ("x = −5", "x = − 5")])
def test_a_spaced_minus_on_the_page_is_the_golds_minus(gold, page):
    assert all(all_types(gold, page, 1)), (gold, page)


@pytest.mark.parametrize("gold, page", [("5 6", "6 5"), ("5", "5 5"), ("5 and 6", "6 and 5"),
                                        ("5 6", "5 6 6")])
def test_the_numbers_of_a_cell_are_in_order_and_as_many(gold, page):
    assert not cell(gold, page, 3), (gold, page)


@pytest.mark.parametrize("gold, page", [
    ("CI (1.13, 3.99) here", "CI (1.13,3.99) here"), ("CI (1.13,3.99) here", "CI (1.13, 3.99) here"),
    ("on 12, 19 November 2012", "on 12,19 November 2012"),
    ("on 12,19 November 2012", "on 12, 19 November 2012"),
    ("[-100, -60, 80,10]", "[-100, -60, 80, 10]"), ("(0.39, 1.56)", "(0.39,1.56)"),
])
def test_the_space_after_a_comma_between_numbers_is_not_a_number_change(gold, page):
    assert all(all_types(gold, page, 1)), (gold, page)


@pytest.mark.parametrize("gold, page", [
    ("sum 1,240 here", "sum 1240 here"), ("sum 1, 240 here", "sum 1240 here"),
    ("rate 1.2 per", "rate 1, 2 per"),
])
@pytest.mark.parametrize("md", [1, 3])
def test_a_thousands_or_decimal_comma_that_is_dropped_or_moved_is_a_number_change(gold, page, md):
    assert not any(all_types(gold, page, md)), (gold, page, md)


def test_a_spaced_minus_after_a_comma_in_a_cell_is_a_sign():
    gold, page = "− 0.075 (− 0.15, − 0.001)", "−0.075 (−0.15, −0.001)"
    assert cell(gold, page, 1) and cell(page, gold, 1)
    assert not cell(gold, "−0.075 (−0.15, 0.001)", 3) and not cell(gold, "0.075 (0.15, 0.001)", 3)


def test_a_leading_zero_the_page_adds_is_a_digit_the_guard_refuses():
    assert not any(all_types(".150 (4.07)", "0.150 (4.07)", 1))
    assert not any(all_types("0.150 (4.07)", ".150 (4.07)", 1))


@pytest.mark.parametrize("gold, page", [("rate 7,2016 per", "rate 7;2016 per"),
                                        ("on 7,2016 and", "on 7 2016 and")])
def test_a_comma_before_four_digits_is_no_number_separator(gold, page):
    assert all(all_types(gold, page, 1)), (gold, page)


@pytest.mark.parametrize("gold, page", [("6 people came", "In 2018, 6 people came"),
                                        ("6. Enter the total", "2018, 6. Enter the total"),
                                        ("12 cases", "n = 5, 12 cases")])
def test_a_number_after_a_comma_and_a_space_is_its_own_number(gold, page):
    assert all(all_types(gold, page, 0)[:2]), (gold, page)    # a cell is matched whole


@pytest.mark.parametrize("gold, page", [
    ("meet C&MS Items 630,", "meet C&MS Items 630, 632, 633 and"), ("A 630", "A 630, 632"),
    ("pages 5 and 7", "pages 5 and 7, 9"),
    ("conform with C&MS 625.11 and 725.06,", "conform with C&MS 625.11 and 725.06, 730"),
    ("Items 630, 632", "see Items 630, 632, 633"),
])
def test_a_gold_that_stops_inside_a_list_of_numbers_passes(gold, page):
    assert all(all_types(gold, page, 0)[:2]), (gold, page)


@pytest.mark.parametrize("gold, page", [
    ("+ 0.30 (+ 23%)", "+0.30 (+23%)"), ("+0.30 (+23%)", "+ 0.30 (+ 23%)"),
    ("− 32.9 (− 42.0 to − 23.4)", "−32.9 (−42.0 to −23.4)"),
    ("−32.9 (−42.0 to −23.4)", "− 32.9 (− 42.0 to − 23.4)"),
])
def test_spaced_signs_in_a_cell_read_as_the_same_signs_unspaced(gold, page):
    assert cell(gold, page, 1), (gold, page)


@pytest.mark.parametrize("gold, lost", [("+ 0.30 (+ 23%)", "0.30 (23%)"),
                                        ("− 32.9 (− 42.0 to − 23.4)", "−32.9 (−42.0 to 23.4)"),
                                        ("± 0.3 here", "0.3 here")])
def test_a_lost_spaced_sign_in_a_cell_still_fails(gold, lost):
    assert not cell(gold, lost, 3), (gold, lost)


def test_a_spaced_dash_between_values_is_no_sign_in_a_cell():
    assert cell("3 - 5", "3 5", 1) and cell("3 - 5", "3-5", 1)


@pytest.mark.parametrize("gold, page", [("12.20 -13.20 Discussion", "12.20 - 13.20 discussion"),
                                        ("12.20 -13.20 here", "12.20 - 13.20 here")])
def test_a_time_range_with_a_spaced_hyphen_is_the_golds_hyphen(gold, page):
    assert all(all_types(gold, page, 1)[:2]), (gold, page)


@pytest.mark.parametrize("gold, lost", [("at 5 -3 here", "at 5 3 here"),
                                        ("12.20 -13.20 here", "12.20 13.20 here")])
def test_a_lost_hyphen_before_a_number_after_a_value_still_fails(gold, lost):
    assert not any(all_types(gold, lost, 0)[:2]), (gold, lost)
