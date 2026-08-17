# [변경사유]: 스템 파싱·워터마크 비교 단위 테스트
"""stems / watermark 테스트."""

from __future__ import annotations

from pathlib import Path

from kakao_pc_collect.pipeline import (
    _names_on_or_after,
    _should_stop_room,
    first_run_cutoff_stem,
)
from kakao_pc_collect.stems import canonical_kakao_name, is_kakao_image, parse_kakao_stem
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


def test_parse_windows_duplicate_suffix() -> None:
    # [변경사유]: 같은 이름이면 ` (3)` — 스템·앨범 번호는 유지
    stem, seq, ext = parse_kakao_stem("KakaoTalk_20260817_193136507 (3).png")
    assert stem == "20260817_193136507"
    assert seq == 0
    assert ext == "png"
    stem2, seq2, ext2 = parse_kakao_stem(
        "KakaoTalk_20260817_171930427_13 (3).jpg"
    )
    assert stem2 == "20260817_171930427"
    assert seq2 == 13
    assert ext2 == "jpg"
    assert (
        canonical_kakao_name("KakaoTalk_20260817_171930427_13 (3).jpg")
        == "KakaoTalk_20260817_171930427_13.jpg"
    )
    assert canonical_kakao_name("KakaoTalk_20260815_234947259.png") == (
        "KakaoTalk_20260815_234947259.png"
    )


def test_is_kakao_image_rejects_mp4() -> None:
    assert is_kakao_image("KakaoTalk_20260815_234947259.png")
    assert is_kakao_image("KakaoTalk_20260817_193136507 (3).png")
    assert not is_kakao_image("KakaoTalk_20260815_234947259.mp4")
    assert not is_kakao_image("KakaoTalk_20260817_213745936 (3).mp4")
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


def test_should_stop_duplicate_suffix_already_in_photos() -> None:
    stop, reason = _should_stop_room(
        batch_names=["KakaoTalk_20260816_120000000 (3).png"],
        watermark=None,
        photos_before={"KakaoTalk_20260816_120000000.png"},
    )
    assert stop is True
    assert reason == "all_already_in_photos"


def test_first_run_cutoff_stem_format() -> None:
    # [변경사유]: 오늘-3일 0시 스템 형식
    s = first_run_cutoff_stem(days=3)
    assert s.endswith("_000000000")
    assert len(s) == 18


def test_names_on_or_after_filters_old() -> None:
    kept = _names_on_or_after(
        [
            "KakaoTalk_20260816_120000000.png",
            "KakaoTalk_20260810_120000000.png",
            "KakaoTalk_20260815_000000000.jpg",
        ],
        "20260815_000000000",
    )
    assert kept == [
        "KakaoTalk_20260816_120000000.png",
        "KakaoTalk_20260815_000000000.jpg",
    ]


def test_should_stop_first_run_days() -> None:
    # [변경사유]: 신규 방은 3일보다 오래된 칸이 나오면 중단
    stop, reason = _should_stop_room(
        batch_names=[
            "KakaoTalk_20260816_120000000.png",
            "KakaoTalk_20260810_120000000.png",
        ],
        watermark=None,
        photos_before=set(),
        first_run_cutoff="20260815_000000000",
    )
    assert stop is True
    assert reason == "first_run_days"


def test_should_stop_first_run_continue() -> None:
    stop, reason = _should_stop_room(
        batch_names=["KakaoTalk_20260817_120000000.png"],
        watermark=None,
        photos_before=set(),
        first_run_cutoff="20260815_000000000",
    )
    assert stop is False
    assert reason == "continue"
