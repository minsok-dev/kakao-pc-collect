# [변경사유]: 테스트 방 2개·방별 폴더 경로 확인
"""rooms.yaml · 방별 chats/photos."""

from __future__ import annotations

from kakao_pc_collect.config import PROJECT_ROOT, load_rooms, load_settings


def test_enabled_rooms_include_collect_targets() -> None:
    rooms = load_rooms(PROJECT_ROOT / "config" / "rooms.yaml")
    enabled = [(r.id, r.search) for r in rooms if r.enabled]
    assert enabled == [
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
