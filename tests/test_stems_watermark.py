# [변경사유]: 스템 파싱·워터마크 비교 단위 테스트
"""stems / watermark 테스트."""

from __future__ import annotations

from pathlib import Path

from kakao_pc_collect.pipeline import _should_stop_room
from kakao_pc_collect.stems import is_kakao_image, parse_kakao_stem
from kakao_pc_collect.watermark import (
    load_watermarks,
    max_stem_among,
    min_stem_among,
    save_watermarks,
    unique_stems,
)


def test_parse_main_and_album() -> None:
    stem, seq, ext = parse_kakao_stem("KakaoTalk_20260815_234947259.png")
    assert stem == "20260815_234947259"
    assert seq == 0
    assert ext == "png"

    stem2, seq2, ext2 = parse_kakao_stem("KakaoTalk_20260815_234947259_01.jpg")
    assert stem2 == "20260815_234947259"
    assert seq2 == 1
    assert ext2 == "jpg"


def test_is_kakao_image_rejects_mp4() -> None:
    assert is_kakao_image("KakaoTalk_20260815_234947259.png")
    assert not is_kakao_image("KakaoTalk_20260815_234947259.mp4")
    assert not is_kakao_image("random.png")


def test_stem_order() -> None:
    names = [
        "KakaoTalk_20260815_100000000.png",
        "KakaoTalk_20260816_010000000_01.png",
        "KakaoTalk_20260814_235959999.png",
    ]
    assert max_stem_among(names) == "20260816_010000000"
    assert min_stem_among(names) == "20260814_235959999"
    assert unique_stems(names) == {
        "20260815_100000000",
        "20260816_010000000",
        "20260814_235959999",
    }


def test_watermark_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "watermarks.json"
    save_watermarks(path, {"gangnam_latin": "20260815_234947259"})
    loaded = load_watermarks(path)
    assert loaded["gangnam_latin"] == "20260815_234947259"


def test_should_stop_reached_watermark() -> None:
    stop, reason = _should_stop_room(
        batch_names=[
            "KakaoTalk_20260815_100000000.png",
            "KakaoTalk_20260814_090000000.png",
        ],
        watermark="20260815_000000000",
        photos_before=set(),
    )
    assert stop is True
    assert reason == "reached_watermark"


def test_should_stop_all_new_continue() -> None:
    stop, reason = _should_stop_room(
        batch_names=["KakaoTalk_20260816_120000000.png"],
        watermark="20260815_000000000",
        photos_before=set(),
    )
    assert stop is False
    assert reason == "continue"


def test_should_stop_already_in_photos() -> None:
    name = "KakaoTalk_20260816_120000000.png"
    stop, reason = _should_stop_room(
        batch_names=[name],
        watermark=None,
        photos_before={name},
    )
    assert stop is True
    assert reason == "all_already_in_photos"
