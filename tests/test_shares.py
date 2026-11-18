import pytest

from app.errors import ValidationError
from app.shares import distribute


@pytest.mark.parametrize(
    ("pinned", "unpinned_count", "expected"),
    [
        ([], 1, [100]),
        ([], 2, [50, 50]),
        ([], 3, [34, 33, 33]),
        ([], 4, [25, 25, 25, 25]),
        ([25], 2, [38, 37]),
        ([25, 25], 1, [50]),
        ([100], 0, []),
        ([], 0, []),
    ],
)
def test_distribute_splits_free_share_evenly(pinned, unpinned_count, expected):
    assert distribute(pinned, unpinned_count) == expected


def test_distribute_always_sums_to_hundred():
    for count in range(1, 60):
        assert sum(distribute([7], count)) == 93


def test_distribute_rejects_pinned_over_hundred():
    with pytest.raises(ValidationError):
        distribute([60, 50], 1)


def test_distribute_rejects_when_nothing_left_for_unpinned():
    with pytest.raises(ValidationError):
        distribute([100], 1)
