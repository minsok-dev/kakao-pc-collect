# kakao-pc-collect

카카오톡 PC UI **하이브리드** 수집 도구.  
`kakao-import-local`과 **분리**되어 있으며, 산출물은 방별 폴더에 넣는다.

```text
kakao-import-local/input/raw/<room_id>/chats/*.txt
kakao-import-local/input/raw/<room_id>/photos/KakaoTalk_*
kakao-import-local/input/raw/<room_id>/non_posters/KakaoTalk_*   ← import가 확정한 비포스터. 수집기는 쓰지 않음
```

계약·실측: [kakao-pc-collect-plan.md](../kakao-import-local/docs/kakao-pc-collect-plan.md)  
포스터 분류: [poster-classifier-plan.md](../kakao-import-local/docs/poster-classifier-plan.md)  
스케줄 자동 upload · similar hold · 포스터 재학습: [schedule-auto-upload-and-poster-retrain-design.md](../kakao-import-local/docs/schedule-auto-upload-and-poster-retrain-design.md) §11  
단톡 홍보 예약: [promo-schedule.md](docs/promo-schedule.md)

## 하는 일

1. 허용 방 검색 → Enter → ☰ · 서랍 첫 사진 · 다운로드 **창 클라이언트 상대 좌표**로 사진 배치
   (서랍 선택은 `arrow_mode: right` — Shift+RIGHT만. 줄 끝은 카톡이 다음 줄로 넘김)
2. Documents `카카오톡 받은 파일` → 신규 `KakaoTalk_*.png/jpg`만 이름 유지 복사 → `<room_id>/photos/`
3. 방별 워터마크 스템으로 배치 중단. 저장된 워터마크가 없으면 `photos/`와 `non_posters/` 중 더 큰 스템을 쓴다. 두 폴더에 이미 있는 카카오 파일명은 다시 받지 않는다
4. **Ctrl+S** 로 대화 txt → `<room_id>/chats/` (사진 수집 **이후** — 다운로드 중 생긴 캡션 포함)
5. 성공 시 `kakao-import run` + `poster-classify --no-review` + `similar-detect` 호출.
   `KAKAO_COLLECT_RUN_UPLOAD=1` 또는 `--with-upload` 일 때만 이어서 `upload --no-dry-run` (기본은 upload 안 함).
   (자동 체인에서는 poster-review UI를 띄우지 않음. 수동 리뷰는 `kakao-import poster-review`)

## 설치

```powershell
cd F:\site_kdance\TEST_web\kakao-pc-collect
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

카카오톡 PC가 **로그인된 상태**에서 실행한다.

## 캘리브레이션 (필수)

`config/coords.yaml` 기본값은 placeholder. 실측 후 기입한다.

```powershell
# 목표 창을 전경으로 두고, 클릭할 위치에 마우스 →
kakao-pc-collect calibrate
# 또는 서랍만
kakao-pc-collect calibrate --title "채팅방 서랍" --watch
```

출력된 `client_offset`을 `hamburger` / `first_photo` / `download`에 넣는다.  
절대 화면 좌표는 쓰지 않는다.

## 방 목록

`config/rooms.yaml` — `search`는 Enter 시 **첫 결과가 목표 방**이어야 한다.

## 실행

```powershell
# dry-run (실제 클릭 없음)
kakao-pc-collect run --dry-run

# 테스트 방 2개, import 호출 없이
kakao-pc-collect run --room gangnam_latin --room gangnamton_news --no-import

# 한 방만
kakao-pc-collect run --room gangnam_latin --no-import

# txt만 / 사진만
kakao-pc-collect run --chats-only
kakao-pc-collect run --photos-only
```

실행 이력 (덮어쓰지 않음):

```text
kakao-pc-collect/data/run-report.json          ← 항상 마지막 실행
kakao-pc-collect/data/runs/<시각-pid>/
  run-report.json     ← 방별 error, 복사 수, hold
  collect.log
  import-chain.log    ← kakao-import run/classify/similar/upload 출력
  upload-result.json  ← 업로드된/스킵/hold 상세 (있으면)
  last_upload_manifest.json
```

이미지가 있는데 업로드가 안 된 건은 `runs/<해당시각>/upload-result.json` 의 `by_next`·hold·file_missing 과 `collect.room_errors`를 보면 됩니다.

수집 후 사람 작업 (similar deferred hold분):

```text
kakao-import similar-review → upload --dry-run → upload --no-dry-run
```

스케줄 / 로컬에서 수집 **완료 직후** 자동 업로드(similar deferred 는 hold):

```text
# .env
KAKAO_COLLECT_RUN_UPLOAD=1

# 또는 한 번만
kakao-pc-collect run --with-upload
```

`upload`는 import(run → poster-classify → similar-detect)가 **끝난 뒤** 같은 실행에서 호출된다.  
upload용으로 시각만 어긋난 별도 스케줄은 쓰지 않는다.

## 단톡 홍보 예약

수집과 **따로** 실행한다. 같은 시각에 돌리면 카카오톡 창 클릭이 겹친다.  
순서·예약·재전송·단위 테스트 범위는 [docs/promo-schedule.md](docs/promo-schedule.md).

`config/promo.example.yaml` 을 `data/promo/current.yaml` 로 복사한 뒤 이미지·문구·방별 URL·`send_at` 만 바꾼다.  
방 id 는 `config/rooms.yaml` 과 같아야 한다.

말풍선 순서 (값 있는 것만):

1. 공통 이미지
2. 공통 홍보 문구
3. 그 방 바로가기 URL
4. 그 방 추가 이미지 (`image2`, 없으면 생략)
5. 그 방 추가 문구 (`body2`)
6. 그 방 추가 바로가기 (`url2`)

```text
kakao-pc-collect promo --campaign data/promo/current.yaml --dry-run
kakao-pc-collect promo --campaign data/promo/current.yaml
```

작업 스케줄러는 10분마다 두 번째 명령을 호출하면 된다. `send_at` 전에는 보내지 않고, 성공한 방은 `current.yaml.sent.json` 에 남아 다시 나가지 않는다. 재전송은 그 파일을 지우거나 `--force`.

## 환경 변수

| 변수 | 의미 |
|------|------|
| `KAKAO_IMPORT_ROOT` | kakao-import-local 경로 |
| `KAKAO_DOWNLOAD_DIR` | 카톡 받은 파일 폴더 |
| `KAKAO_COLLECT_RUN_IMPORT` | `1`이면 수집 후 run + poster-classify --no-review + similar-detect |
| `KAKAO_COLLECT_RUN_UPLOAD` | `1`이면 위 import **완료 직후** `upload --no-dry-run` |

워터마크: `data/watermarks.json` (방 id → 마지막 스템)
