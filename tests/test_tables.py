from omni_parse_bench.tables import _grid

# A rowspan cut short by a later colspan: e and h each declare 4 rows but hold one.
#   a a b b b c c . . . . . . . .
#   a a b b b c c d e e e . . . .
#   a a b b b c c f f f f g h . .
#   a a b b b c c f f f f i i i j
#   . . . . . . . . . . . i i i j
SPECS = [
    [("a", 4, 2, False), ("b", 4, 3, False), ("c", 4, 2, False)],
    [("d", 1, 1, False), ("e", 4, 3, False)],
    [("f", 2, 4, False), ("g", 1, 1, False), ("h", 4, 1, False)],
    [("i", 2, 3, False), ("j", 2, 1, False)],
]


def _neighbours(name: str) -> dict[str, list[str]]:
    t = _grid(SPECS)
    cell = next(c for c, x in t.text.items() if x == name)
    return {d: sorted(t.text[x] for x in getattr(t, d)[cell]) for d in ("up", "down", "left", "right")}


def test_a_malformed_span_grid_builds_instead_of_raising():
    # Spans that run past the last row used to index past the grid in `first`.
    assert _grid(SPECS) is not None


def test_a_cut_short_span_has_the_neighbours_the_grid_shows():
    assert _neighbours("e") == {"up": [], "down": ["f"], "left": ["d"], "right": []}
    assert _neighbours("h") == {"up": [], "down": ["i"], "left": ["g"], "right": []}
