import pytest

from library.image.optimization import crop_dimensions


@pytest.mark.parametrize(
    "actual_dim, max_dim, expected_dim",
    [
        ((10, 10), (10, 10), (10, 10)),
        ((10, 10), (5, 10), (5, 5)),
        ((10, 10), (10, 5), (5, 5)),
        ((10, 10), (5, 5), (5, 5)),
        ((10, 10), (5, 0), (5, 5)),
        ((10, 10), (0, 5), (5, 5)),
        ((10, 10), (0, 10), (10, 10)),
        ((10, 10), (10, 0), (10, 10)),
        ((10, 10), (0, 0), (10, 10)),
        ((1923, 1000), (1080, 0), (1080, 561)),
        ((3408, 4000), (1080, 0), (1080, 1267)),
        ((2560, 2000), (1080, 0), (1080, 843)),
        ((800, 600), (1080, 0), (800, 600)),
    ],
)
def test_calculate_dimensions(actual_dim, max_dim, expected_dim) -> None:
    assert crop_dimensions(actual_dim, max_dim) == expected_dim
