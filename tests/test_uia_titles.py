# [변경사유]: 방 창 제목 매칭 — 메인/서랍과 구분
"""창 제목 매칭 테스트."""

from kakao_pc_collect.uia_kakao import title_is_room_match


def test_room_title_contains_search() -> None:
    title = "💘 강남 라틴클럽Club LATIN🔺️코드 5001"
    assert title_is_room_match(title, "강남 라틴클럽") is True


def test_main_kakao_is_not_room() -> None:
    assert title_is_room_match("카카오톡", "강남 라틴클럽") is False


def test_drawer_and_save_excluded() -> None:
    assert title_is_room_match("채팅방 서랍", "강남 라틴클럽") is False
    assert title_is_room_match("다른 이름으로 저장", "강남 라틴클럽") is False
