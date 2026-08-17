# [변경사유]: 테스트 방 2개·방별 폴더 경로 확인
"""rooms.yaml · 방별 chats/photos."""

from __future__ import annotations

from kakao_pc_collect.config import PROJECT_ROOT, load_rooms, load_settings


def test_enabled_rooms_are_the_two_test_rooms() -> None:
    rooms = load_rooms(PROJECT_ROOT / "config" / "rooms.yaml")
    enabled = [(r.id, r.search) for r in rooms if r.enabled]
    assert enabled == [
        ("gangnam_latin", "강남 라틴클럽"),
        ("gangnamton_news", "강남턴 소식방"),
    ]


def test_room_dirs_under_raw_root() -> None:
    settings = load_settings()
    assert settings.room_chats_dir("gangnam_latin") == (
        settings.raw_root / "gangnam_latin" / "chats"
    )
    assert settings.room_photos_dir("gangnamton_news") == (
        settings.raw_root / "gangnamton_news" / "photos"
    )
