# [변경사유]: 설정·방 목록·좌표 캘리브레이션 로드
"""설정."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class RoomSpec:
    id: str
    search: str
    enabled: bool = True
    # [변경사유]: 오픈 단톡방(open)=Down×2, 일반 단톡방(general)=Down×3
    # room_type 에 맞게 drawer_menu_downs 기본값을 자동 결정.
    # rooms.yaml 에서 drawer_menu_downs 를 직접 지정하면 그 값을 우선 사용.
    room_type: str = "open"       # "open" | "general"
    drawer_menu_downs: int | None = None   # None → room_type 기본값으로 결정


ROOM_TYPE_DEFAULTS: dict[str, int] = {
    "open": 2,       # 오픈 단톡방 — ☰ → Down×2 → Right → Down×1 → Enter
    "general": 3,    # 일반 단톡방 — ☰ → Down×3 → Right → Down×1 → Enter
}


def effective_drawer_menu_downs(room: "RoomSpec", coords_default: int = 2) -> int:
    """방별 실제 drawer_menu_downs 결정 (rooms.yaml 직접 지정 > room_type 기본 > coords 전역)."""
    if room.drawer_menu_downs is not None:
        return room.drawer_menu_downs
    return ROOM_TYPE_DEFAULTS.get(room.room_type, coords_default)


@dataclass
class CoordConfig:
    """창 클라이언트 좌상단 기준 오프셋."""

    room_client_size: tuple[int, int] = (800, 900)
    hamburger: tuple[int, int] = (760, 28)
    drawer_menu: tuple[int, int] = (620, 120)
    photos_submenu: tuple[int, int] = (780, 140)
    drawer_menu_downs: int = 2
    photos_menu_downs: int = 0
    use_menu_coords: bool = True
    drawer_client_size: tuple[int, int] = (1100, 800)
    first_photo: tuple[int, int] = (320, 220)
    download: tuple[int, int] = (1050, 60)
    # [변경사유]: 메인 목록 창 — 검색칸·첫 결과. 헤더 우측(친구 추가)을 피한다.
    main_client_size: tuple[int, int] = (441, 1032)
    # [변경사유]: 왼쪽 레일 — 방 수집=채팅 탭, 관리자 알림=친구 탭 (F: 로컬 2026-08-24 실측)
    friends_tab: tuple[int, int] = (33, 56)
    chats_tab: tuple[int, int] = (30, 118)
    main_search: tuple[int, int] = (213, 106)
    first_search_result: tuple[int, int] = (215, 168)
    # [변경사유]: 친구 탭 검색 결과 첫 행 — 「친구 N」 헤더 아래. 채팅 first_search_result 와 Y 다름
    # None 이면 first_search_result 로 폴백(경고 로그). 운영 PC는 반드시 실측 기입.
    friends_first_search_result: tuple[int, int] | None = None
    # [변경사유]: 채팅 탭 헤더 돋보기 — 아이콘 3개(검색·새채팅·오픈) 중 왼쪽
    search_icon: tuple[int, int] = (329, 56)
    # [변경사유]: 친구 탭 헤더 돋보기 — 아이콘 2개(검색·친구추가)라 X가 채팅과 다름.
    # None 이면 search_icon 폴백(경고). 관리자 알림은 반드시 친구 탭에서 실측 기입.
    friends_search_icon: tuple[int, int] | None = None
    # [변경사유]: I5 — 관리자 알림 메시지 입력칸 (없으면 창 하단 중앙 추정)
    message_input: tuple[int, int] | None = None
    select_count: int = 50
    preload_arrow_presses: int = 80
    arrow_mode: str = "right_then_down"
    grid_columns: int = 6


@dataclass
class Settings:
    project_root: Path
    kakao_import_root: Path
    download_dir: Path
    raw_root: Path
    chats_dir: Path
    photos_dir: Path
    rooms: list[RoomSpec]
    coords: CoordConfig
    run_import: bool = True
    # [변경사유]: 수집·import 체인 완료 직후 upload --no-dry-run (시각 분리 스케줄 대신 순차 호출)
    run_upload: bool = False
    # [변경사유]: I5 — 관리자 카톡 알림 검색어 (비어 있으면 전송 안 함)
    admin_notify_search: str = ""
    log_level: str = "INFO"
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    watermark_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "watermarks.json"
    )

    def room_chats_dir(self, room_id: str) -> Path:
        """[변경사유]: 방별 txt — import 매칭이 섞이지 않게."""
        return self.raw_root / room_id / "chats"

    def room_photos_dir(self, room_id: str) -> Path:
        """[변경사유]: 방별 사진."""
        return self.raw_root / room_id / "photos"


def _xy(v: Any, default: tuple[int, int]) -> tuple[int, int]:
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return int(v[0]), int(v[1])
    return default


def load_coords(path: Path) -> CoordConfig:
    raw: dict[str, Any] = {}
    if path.is_file() and yaml is not None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return CoordConfig(
        room_client_size=_xy(raw.get("room_client_size"), (800, 900)),
        hamburger=_xy(raw.get("hamburger"), (760, 28)),
        drawer_menu=_xy(raw.get("drawer_menu"), (620, 120)),
        photos_submenu=_xy(raw.get("photos_submenu"), (780, 140)),
        drawer_menu_downs=int(raw.get("drawer_menu_downs") or 2),
        photos_menu_downs=int(raw.get("photos_menu_downs") or 0),
        use_menu_coords=bool(raw.get("use_menu_coords", True)),
        drawer_client_size=_xy(raw.get("drawer_client_size"), (1100, 800)),
        first_photo=_xy(raw.get("first_photo"), (320, 220)),
        download=_xy(raw.get("download"), (1050, 60)),
        main_client_size=_xy(raw.get("main_client_size"), (441, 1032)),
        # [변경사유]: 탭 좌표 로드 — 없으면 로컬 실측 기본값
        friends_tab=_xy(raw.get("friends_tab"), (33, 56)),
        chats_tab=_xy(raw.get("chats_tab"), (30, 118)),
        main_search=_xy(raw.get("main_search"), (213, 106)),
        first_search_result=_xy(raw.get("first_search_result"), (215, 168)),
        # [변경사유]: 친구 탭 첫 결과 — 키 없으면 None → open 시 채팅용으로 폴백+경고
        friends_first_search_result=_xy(raw["friends_first_search_result"], (0, 0))
        if raw.get("friends_first_search_result") is not None
        else None,
        search_icon=_xy(raw.get("search_icon"), (329, 56)),
        # [변경사유]: 친구 탭 돋보기 — 키 없으면 None → open 시 채팅용으로 폴백+경고
        friends_search_icon=_xy(raw["friends_search_icon"], (0, 0))
        if raw.get("friends_search_icon") is not None
        else None,
        message_input=_xy(raw["message_input"], (0, 0))
        if raw.get("message_input") is not None
        else None,
        select_count=int(raw.get("select_count") or 50),
        preload_arrow_presses=int(raw.get("preload_arrow_presses") or 80),
        arrow_mode=str(raw.get("arrow_mode") or "right_then_down"),
        grid_columns=int(raw.get("grid_columns") or 6),
    )


def load_rooms(path: Path) -> list[RoomSpec]:
    if not path.is_file():
        return []
    if yaml is None:
        raise RuntimeError("PyYAML 필요: pip install pyyaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rooms: list[RoomSpec] = []
    for item in raw.get("rooms") or []:
        # [변경사유]: room_type(open/general)·drawer_menu_downs 방별 지정 지원
        rtype = str(item.get("room_type") or "open").lower()
        raw_dmd = item.get("drawer_menu_downs")
        dmd: int | None = int(raw_dmd) if raw_dmd is not None else None
        rooms.append(
            RoomSpec(
                id=str(item["id"]),
                search=str(item["search"]),
                enabled=bool(item.get("enabled", True)),
                room_type=rtype,
                drawer_menu_downs=dmd,
            )
        )
    return rooms


def load_settings(
    *,
    env_path: Path | None = None,
    rooms_path: Path | None = None,
    coords_path: Path | None = None,
) -> Settings:
    root = PROJECT_ROOT
    env_file = env_path or (root / ".env")
    # [변경사유]: PROJECT_ROOT 기준 .env (cwd 아님). 없으면 경고 — 잘못된 경로/옛 설치 조기 발견
    loaded = load_dotenv(env_file, override=False)
    if not loaded and not env_file.is_file():
        from kakao_pc_collect.logging_util import get_logger

        get_logger(__name__).warning(
            "dotenv missing path=%s PROJECT_ROOT=%s — KAKAO_ADMIN_NOTIFY_SEARCH 등 미적용",
            env_file,
            root,
        )

    import_root = Path(
        os.getenv("KAKAO_IMPORT_ROOT")
        or str(root.parent / "kakao-import-local")
    ).resolve()
    download = Path(
        os.getenv("KAKAO_DOWNLOAD_DIR")
        or r"D:\Users\msgu\Documents\카카오톡 받은 파일"
    )
    run_import = (os.getenv("KAKAO_COLLECT_RUN_IMPORT") or "1").strip() not in (
        "0",
        "false",
        "False",
        "no",
    )
    # [변경사유]: 기본 0 — 기존 수동 upload 흐름 유지. 스케줄은 1 로 켜서 수집 완료 후 즉시 upload
    run_upload = (os.getenv("KAKAO_COLLECT_RUN_UPLOAD") or "0").strip() in (
        "1",
        "true",
        "True",
        "yes",
    )
    # [변경사유]: I5 — 예: KAKAO_ADMIN_NOTIFY_SEARCH=관리자닉네임 (친구 탭 검색)
    admin_notify_search = (os.getenv("KAKAO_ADMIN_NOTIFY_SEARCH") or "").strip()
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    rooms = load_rooms(rooms_path or (root / "config" / "rooms.yaml"))
    coords = load_coords(coords_path or (root / "config" / "coords.yaml"))

    # [변경사유]: 알림 opt-in 로드 여부 — 비어 있으면 전송 스킵이므로 시작 시 로그로 확인
    from kakao_pc_collect.logging_util import get_logger

    get_logger(__name__).info(
        "settings loaded PROJECT_ROOT=%s env=%s admin_notify_search=%r",
        root,
        env_file,
        admin_notify_search or "(empty→skip)",
    )

    raw_root = import_root / "input" / "raw"
    return Settings(
        project_root=root,
        kakao_import_root=import_root,
        download_dir=download,
        raw_root=raw_root,
        chats_dir=raw_root / "chats",
        photos_dir=raw_root / "photos",
        rooms=rooms,
        coords=coords,
        run_import=run_import,
        run_upload=run_upload,
        admin_notify_search=admin_notify_search,
        log_level=os.getenv("LOG_LEVEL") or "INFO",
        data_dir=data_dir,
        watermark_path=data_dir / "watermarks.json",
    )
