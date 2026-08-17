# kakao-pc-collect

카카오톡 PC UI **하이브리드** 수집 도구.  
`kakao-import-local`과 **분리**되어 있으며, 산출물은 import의 `input/raw/chats` · `input/raw/photos`에 넣는다.

계약·실측: [kakao-pc-collect-plan.md](../kakao-import-local/docs/kakao-pc-collect-plan.md)

## 하는 일

1. 허용 방 검색 → Enter → **Ctrl+S** 로 대화 txt → `chats/`
2. ☰ · 서랍 첫 사진 · 다운로드 **창 클라이언트 상대 좌표 3곳**으로 사진 배치
3. Documents `카카오톡 받은 파일` → 신규 `KakaoTalk_*.png/jpg`만 이름 유지 복사 → `photos/`
4. 방별 워터마크 스템으로 배치 중단
5. 성공 시 `kakao-import run` + `similar-detect`만 호출 (**upload 금지**)

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

# 한 방만, import 호출 없이
kakao-pc-collect run --room gangnam_latin --no-import

# txt만 / 사진만
kakao-pc-collect run --chats-only
kakao-pc-collect run --photos-only
```

수집 후 사람 작업:

```text
kakao-import similar-review → upload --dry-run → upload --no-dry-run
```

## 환경 변수

| 변수 | 의미 |
|------|------|
| `KAKAO_IMPORT_ROOT` | kakao-import-local 경로 |
| `KAKAO_DOWNLOAD_DIR` | 카톡 받은 파일 폴더 |
| `KAKAO_COLLECT_RUN_IMPORT` | `1`이면 수집 후 run+similar-detect |

워터마크: `data/watermarks.json` (방 id → 마지막 스템)
