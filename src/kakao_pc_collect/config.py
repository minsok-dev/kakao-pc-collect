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
    main_search: tuple[int, int] = (213, 106)
    first_search_result: tuple[int, int] = (215, 168)
    # [변경사유]: 검색창 닫힘(Edit=0)일 때만 돋보기 1회. 열려 있으면 누르지 않음(토글).
    search_icon: tuple[int, int] = (329, 56)
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
        main_search=_xy(raw.get("main_search"), (213, 106)),
        first_search_result=_xy(raw.get("first_search_result"), (215, 168)),
        search_icon=_xy(raw.get("search_icon"), (329, 56)),
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
        rooms.append(
            RoomSpec(
                id=str(item["id"]),
                search=str(item["search"]),
                enabled=bool(item.get("enabled", True)),
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
    load_dotenv(env_path or (root / ".env"), override=False)

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
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    rooms = load_rooms(rooms_path or (root / "config" / "rooms.yaml"))
    coords = load_coords(coords_path or (root / "config" / "coords.yaml"))

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
        log_level=os.getenv("LOG_LEVEL") or "INFO",
        data_dir=data_dir,
        watermark_path=data_dir / "watermarks.json",
    )
