from omni_parse_bench.tables import _grid


def test_a_malformed_span_grid_builds_instead_of_raising():
    # Spans that run past the last row used to index past the grid in `first`.
    specs = [
        [("a", 4, 2, False), ("b", 4, 3, False), ("c", 4, 2, False)],
        [("d", 1, 1, False), ("e", 4, 3, False)],
        [("f", 2, 4, False), ("g", 1, 1, False), ("h", 4, 1, False)],
        [("i", 2, 3, False), ("j", 2, 1, False)],
    ]
    assert _grid(specs) is not None
