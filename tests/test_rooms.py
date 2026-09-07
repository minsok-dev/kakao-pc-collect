# [변경사유]: 테스트 방 2개·방별 폴더 경로 확인
# [변경사유]: 방별 select_count(10~50) · enabled 목록에 등록방 반영
"""rooms.yaml · 방별 chats/photos."""

from __future__ import annotations

from kakao_pc_collect.config import (
    PROJECT_ROOT,
    RoomSpec,
    clamp_select_count,
    effective_select_count,
    load_rooms,
    load_settings,
)


def test_enabled_rooms_include_collect_targets() -> None:
    rooms = load_rooms(PROJECT_ROOT / "config" / "rooms.yaml")
    enabled = [(r.id, r.search) for r in rooms if r.enabled]
    assert enabled == [
        ("danceinfo_registration", "댄스인포 행사.강습 등록방"),
        ("gangnam_latin", "강남 라틴클럽"),
        ("gangnamton_news", "강남턴 소식방"),
        ("hongdae_bonita", "홍대보니따 오픈채팅방"),
        ("info_latin_korea", "(전국라틴댄스)"),
        ("gyeonggi_latin_news", "경기라틴소식방"),
        ("hongton_latin", "홍턴 라틴클럽"),
        ("musica_bachata", "musica bachata"),
        ("ksf_salva_tour", "K.S.F 해외 살바키투어"),
    ]


def test_room_dirs_under_raw_root() -> None:
    settings = load_settings()
    assert settings.room_chats_dir("gangnam_latin") == (
        settings.raw_root / "gangnam_latin" / "chats"
    )
    assert settings.room_photos_dir("gangnamton_news") == (
        settings.raw_root / "gangnamton_news" / "photos"
    )


def test_clamp_select_count() -> None:
    assert clamp_select_count(10) == 10
    assert clamp_select_count(50) == 50
    assert clamp_select_count(1) == 10
    assert clamp_select_count(99) == 50


def test_effective_select_count_room_overrides_coords() -> None:
    room = RoomSpec(id="x", search="x", select_count=10)
    assert effective_select_count(room, 50) == 10
    room_default = RoomSpec(id="y", search="y")
    assert effective_select_count(room_default, 50) == 50


def test_rooms_yaml_select_count_on_registration() -> None:
    rooms = load_rooms(PROJECT_ROOT / "config" / "rooms.yaml")
    by_id = {r.id: r for r in rooms}
    assert by_id["danceinfo_registration"].select_count == 10
    assert by_id["gangnam_latin"].select_count is None
