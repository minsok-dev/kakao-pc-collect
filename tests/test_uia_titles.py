# [변경사유]: 방 창 제목 매칭 — 메인/서랍과 구분
"""창 제목 매칭 테스트."""

from kakao_pc_collect.uia_kakao import (
    classify_save_wait,
    is_browser_title,
    is_search_bar_open_by_edit_count,
    title_is_room_match,
)


def test_room_title_contains_search() -> None:
    title = "💘 강남 라틴클럽Club LATIN🔺️코드 5001"
    assert title_is_room_match(title, "강남 라틴클럽") is True


def test_main_kakao_is_not_room() -> None:
    assert title_is_room_match("카카오톡", "강남 라틴클럽") is False


def test_chrome_search_is_not_room() -> None:
    assert (
        title_is_room_match("강남 라틴클럽 - Google 검색 - Chrome", "강남 라틴클럽")
        is False
    )
    assert is_browser_title("카카오톡 MCP 기능 및 활용 - Claude - Chrome") is True


def test_drawer_and_save_excluded() -> None:
    assert title_is_room_match("채팅방 서랍", "강남 라틴클럽") is False
    assert title_is_room_match("다른 이름으로 저장", "강남 라틴클럽") is False
    assert title_is_room_match("대화 내보내기", "강남 라틴클럽") is False


def test_txt_write_is_stable() -> None:
    from kakao_pc_collect.uia_kakao import txt_write_is_stable

    assert txt_write_is_stable(None, {"a.txt": 10}) is False
    assert txt_write_is_stable({"a.txt": 10}, {"a.txt": 20}) is False
    assert txt_write_is_stable({"a.txt": 0}, {"a.txt": 0}) is False
    assert txt_write_is_stable({"a.txt": 100}, {"a.txt": 100}) is True


def test_classify_save_wait_found() -> None:
    assert (
        classify_save_wait(
            elapsed=1.0,
            found=True,
            fg_title="다른 이름으로 저장",
            room_title="💘 강남 라틴클럽",
        )
        == "found"
    )


def test_classify_save_wait_focus_lost() -> None:
    assert (
        classify_save_wait(
            elapsed=3.0,
            found=False,
            fg_title="kakao-pc-collect — Cursor",
            room_title="💘 강남 라틴클럽Club LATIN",
        )
        == "focus_lost"
    )


def test_classify_save_wait_still_on_room() -> None:
    assert (
        classify_save_wait(
            elapsed=8.0,
            found=False,
            fg_title="💘 강남 라틴클럽Club LATIN🔺️코드 5001",
            room_title="💘 강남 라틴클럽Club LATIN🔺️코드 5001",
        )
        == "waiting_kakao"
    )


def test_search_bar_open_by_edit_count() -> None:
    # [변경사유]: Edit=0 닫힘 / 1 이상 열림 — 돋보기는 닫힘일 때만
    assert is_search_bar_open_by_edit_count(0) is False
    assert is_search_bar_open_by_edit_count(1) is True
    assert is_search_bar_open_by_edit_count(2) is True
