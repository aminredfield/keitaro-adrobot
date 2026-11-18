"""Пересчёт долей офферов в потоке. Чистая арифметика, без базы и сети."""

from collections.abc import Sequence

from app.errors import ValidationError

TOTAL_SHARE = 100


def distribute(pinned_shares: Sequence[int], unpinned_count: int) -> list[int]:
    """Делит между незакреплёнными офферами то, что осталось после закреплённых.

    Делим поровну, остаток от деления отдаём первым:
    100 на троих -> 34, 33, 33; при закреплённых 25% на двоих -> 38, 37.
    """
    free_share = TOTAL_SHARE - sum(pinned_shares)
    if free_share < 0:
        raise ValidationError(f"Закреплённые доли дают в сумме больше {TOTAL_SHARE}%")
    if unpinned_count == 0:
        return []
    # каждому незакреплённому офферу должен достаться хотя бы 1%
    if free_share < unpinned_count:
        raise ValidationError(
            f"На {unpinned_count} оффер(ов) без закрепа осталось {free_share}% — снимите закреп"
        )

    base, remainder = divmod(free_share, unpinned_count)
    return [base + 1 if index < remainder else base for index in range(unpinned_count)]
