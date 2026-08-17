# [변경사유]: 방 창 너비가 달라도 ☰ 가 창 밖으로 나가지 않게
"""우측 고정 좌표."""

from kakao_pc_collect.win_click import right_anchored_xy


def test_hamburger_right_anchor_narrow_room() -> None:
    # 캘리브 424×1032, hamburger (402, 60) → 오른쪽 여백 22
    assert right_anchored_xy(
        (402, 60),
        calibrated_size=(424, 1032),
        actual_size=(385, 1032),
    ) == (363, 60)


def test_hamburger_same_size_unchanged() -> None:
    assert right_anchored_xy(
        (402, 60),
        calibrated_size=(424, 1032),
        actual_size=(424, 1032),
    ) == (402, 60)
