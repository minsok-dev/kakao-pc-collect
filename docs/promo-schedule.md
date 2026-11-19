# 단톡 홍보 예약

<!-- [변경사유]: 2026-11-20 — 수집 완료 알림과 같은 PC 카톡 자동화로, 홍보만 별도 명령으로 둔다 -->

| 항목 | 내용 |
|------|------|
| 기준일 | 2026-11-20 |
| 명령 | `kakao-pc-collect promo` |
| 예시 | `config/promo.example.yaml` |
| 단위 테스트 | `tests/test_promo_campaign.py` (10개). 전체 `pytest` 75 passed |
| 실전송 | 이 PC 카카오 창에 붙여넣기까지는 아직 확인하지 않음 |

수집(`run`)과 완료 알림(`notify-test`)은 바꾸지 않는다. 홍보는 그 둘과 **다른 시각**에 실행한다. 같은 카카오톡 창을 클릭하기 때문이다.

## 말풍선 순서

값이 있는 단계만 보낸다. 한 단계가 말풍선 하나다.

| 순서 | 필드 | 범위 | 내용 |
|------|------|------|------|
| 1 | `image` | 캠페인 공통 | 이미지 |
| 2 | `body` | 캠페인 공통 | 홍보 문구 |
| 3 | `url` | 방별 | 바로가기 URL 만 |
| 4 | `image2` | 방별, 없으면 생략 | 추가 이미지 |
| 5 | `body2` | 방별, 없으면 생략 | 추가 문구 |
| 6 | `url2` | 방별, 없으면 생략 | 추가 바로가기 URL |

바로가기는 문구 끝에 붙이지 않는다. URL 만 따로 보내 카카오 링크 미리보기가 나오게 한다.

이미지·문구는 캠페인에서 그때그때 바꾼다. 방 `id` 는 `config/rooms.yaml` 의 id 와 같아야 하고, 검색어는 그 파일의 `search` 를 쓴다. 창 제목에 검색어가 없으면 그 방은 보내지 않는다.

## 파일

`config/promo.example.yaml` 을 `data/promo/current.yaml` 로 복사한다. `data/` 는 git 에 올리지 않는다.

```yaml
id: 20261121-week
send_at: "2026-11-21 10:00"
image: poster.jpg
body: |
  공통 홍보 문구
rooms:
  - id: gangnam_latin
    url: "https://danceinfo.net/lessons"
  - id: hongdae_bonita
    url: "https://danceinfo.net/lessons"
    image2: poster-extra.jpg
    body2: |
      이 방만 추가 안내
    url2: "https://danceinfo.net/"
```

- `image`, `image2` 가 상대 경로면 캠페인 파일이 있는 폴더 기준이다.
- `send_at` 을 빼면 명령을 실행한 시각에 바로 보낸다. 형식은 `2026-11-21 10:00` (PC 로컬 시각).
- 빈 칸인 단계는 말풍선을 만들지 않는다. 2번 세트는 방마다 있는 항목만 이어 붙인다.

## 실행

```text
kakao-pc-collect promo --campaign data/promo/current.yaml --dry-run
kakao-pc-collect promo --campaign data/promo/current.yaml
kakao-pc-collect promo --campaign data/promo/current.yaml --room gangnam_latin --now
kakao-pc-collect promo --campaign data/promo/current.yaml --force
```

| 옵션 | 동작 |
|------|------|
| `--dry-run` | 카톡을 열지 않고 말풍선 순서와 문구를 출력. `send_at` 전에도 순서는 보여 준다 |
| `--now` | `send_at` 이전이어도 지금 전송 |
| `--room` | 캠페인 안 그 id 만. 여러 번 쓸 수 있다 |
| `--force` | `ok` 인 방도 다시 전송 |

작업 스케줄러는 10분마다 `--dry-run` 없는 명령을 호출한다. `send_at` 전에는 상태 `not_due` 로 끝나고 카톡을 열지 않는다.

성공한 방은 캠페인 옆 `current.yaml.sent.json` 에 남는다. 다음 실행은 그 방을 건너뛴다. 실패한 방만 다시 시도한다. 같은 글을 다시 보내려면 그 파일을 지우거나 `--force`.

이미지는 클립보드용으로 긴 변 1920 을 넘으면 줄여서 붙인다. 원본 파일은 바꾸지 않는다. 로그에는 홍보 본문을 남기지 않고 글자 수만 남긴다.

## 단위 테스트

카톡 창 없이 `tests/test_promo_campaign.py` 가 순서를 고정한다.

- 공통 이미지 → 문구 → 바로가기, 그 다음 방별 이미지2 → 문구2 → 바로가기2
- `image2` 가 없어도 문구2·바로가기2 는 그 순서로 남음
- 공백만 있는 추가 항목은 말풍선에서 빠짐
- `rooms.yaml` 에 없는 id 는 오류
- `send_at` 전에는 방을 열지 않음
- `--dry-run` 은 시각 전에도 순서를 보여주고, 이미지 파일이 없으면 열지 않음
- 한 방이 실패하면 성공한 방은 기록되고, 다시 실행하면 실패 방만 이어서 보냄
- `--force` 는 이미 성공한 방도 다시 포함

2026-11-20 실행: `.\.venv\Scripts\python.exe -m pytest -q` → **75 passed**.

이 테스트는 클릭·붙여넣기·Enter 를 대역으로 바꾼 것이다. 로그인된 카카오톡 PC 에서 사진이 말풍선으로 나가는지는 `--room` 한 방으로 따로 확인한다. 그 실행 중에는 화면 잠금이 없어야 하고, 수집 스케줄과 겹치면 안 된다.
