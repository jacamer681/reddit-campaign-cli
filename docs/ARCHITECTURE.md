# 아키텍처

## 목차

1. [전체 구조](#전체-구조)
2. [모듈 설명](#모듈-설명)
3. [데이터 흐름](#데이터-흐름)
4. [30일 스케줄 시스템](#30일-스케줄-시스템)
5. [SQLite 스키마](#sqlite-스키마)

---

## 전체 구조

```
main.py                            엔트리포인트
  └── src/cli.py                    Click CLI 정의
        ├── src/autopilot_browser.py  브라우저 자동화 오케스트레이터
        │     ├── src/pi_browser.py         Reddit 브라우저 액션
        │     │     └── src/pi_browser_client.py  WebSocket 서버
        │     ├── src/marketing/engine.py   마케팅 엔진 (안전장치)
        │     ├── src/schedule.py           30일 스케줄 생성
        │     └── src/comment_generator.py  댓글 생성
        ├── src/state.py             SQLite 상태 관리
        └── src/display.py           Rich 터미널 UI
```

**의존성 방향:** `cli` → `autopilot_browser` → `pi_browser`, `marketing/engine`, `schedule`, `comment_generator` → `state`, `display`

---

## 모듈 설명

### `main.py`

엔트리포인트. `src.cli.cli()`를 호출합니다.

### `src/cli.py`

Click 기반 CLI 정의.

- `browser` — 브라우저 자동화 캠페인 실행
- `campaign` — 캠페인 설정/조회/수정 (서브커맨드 그룹)
- `report` — 일일 전략 리포트
- `dashboard` — 터미널 대시보드
- `influence` — 영향력 분석
- `web` — 웹 대시보드 서버

### `src/autopilot_browser.py`

브라우저 자동화 오케스트레이터. 30일 스케줄에 따라 태스크를 실행합니다.

**`run_browser_campaign()` 함수 흐름:**
1. WebSocket 서버 시작 (포트 9877)
2. 크롬 확장프로그램 연결 대기
3. Reddit 로그인 상태 확인
4. 30일 스케줄 로드
5. 다음 미완료 날짜의 태스크 실행
6. 결과를 DB에 저장

**태스크 실행 함수:**
- `_exec_karma()` — 카르마 빌딩: r/{sub}/hot → 글 선택 → 도움 댓글
- `_exec_seed()` — 씨뿌리기: r/{sub}/search → 관련 글 → 자연스러운 제품 언급
- `_exec_post()` — 포스트: r/{sub}/submit → 제목/본문 입력 → 게시
- `_exec_monitor()` — 기존 포스트 새 댓글 확인

### `src/pi_browser_client.py`

WebSocket 서버. 크롬 확장프로그램과 통신합니다.

- **포트:** 9877
- **프로토콜:** JSON 메시지 (id, command, params → id, result/error)
- Python에서 명령 전송 → 확장프로그램이 실행 → 결과 반환
- `threading.Event`로 동기적 요청/응답 처리

**주요 명령:**
- `navigate` — URL 이동
- `click`, `clickCoords` — 요소/좌표 클릭
- `fill`, `typeText` — 텍스트 입력 (CDP 기반)
- `evaluate` — JavaScript 실행
- `snapshot` — 페이지 인터랙티브 요소 목록
- `redditSubmitPost` — Reddit 포스트 작성
- `redditComment` — Reddit 댓글 작성
- `redditCheckLogin` — 로그인 상태 확인

### `src/pi_browser.py`

Reddit 전용 브라우저 액션 래퍼.

**댓글 작성 3단계 폴백:**
1. JS 삽입으로 댓글 입력 + 제출
2. CDP typeText로 재시도
3. 페이지 새로고침 후 전체 재시도

**주요 메서드:**
- `post_comment()` — 댓글 작성 (3단계 폴백)
- `submit_post()` — 포스트 작성
- `check_login()` — 로그인 확인
- `verify_comment()` — 댓글 작성 성공 확인

### `src/marketing/engine.py`

마케팅 엔진. 매 액션 전 안전 검사를 수행합니다.

**프리플라이트 체크:**
- 계정 건강도 (업보트/다운보트 비율)
- 타이밍 등급 (optimal/good/acceptable/poor/avoid)
- 일일 한도 (포스트 2개/일, 댓글 8개/일)
- 서브레딧별 규칙 확인

### `src/schedule.py`

30일 스케줄을 자동 생성합니다.

**4단계 구성:**
- Phase 1 (Day 1~8): 카르마 빌딩만
- Phase 2 (Day 9~15): 카르마 + 씨뿌리기
- Phase 3 (Day 16~22): 씨뿌리기 + 포스트
- Phase 4 (Day 23~30): 전체 캠페인

campaign.toml의 타겟 서브레딧/키워드를 기반으로 각 날짜의 태스크를 배정합니다.

### `src/comment_generator.py`

AI 기반 댓글 생성.

- `generate_karma_comment()` — 도움이 되는 전문가 톤 댓글
- `generate_seed_comment()` — 자연스러운 제품 언급 댓글
- `generate_post_title()` / `generate_post_body()` — 포스트 생성

### `src/state.py`

SQLite 데이터베이스를 통한 상태 관리.

- 첫 실행 시 자동으로 DB 파일과 테이블 생성
- 각 테이블별 CRUD 메서드 제공
- `ON CONFLICT` 구문으로 중복 키 처리

### `src/display.py`

Rich 라이브러리를 활용한 터미널 UI.

### `extension/background.js`

크롬 확장프로그램의 Service Worker.

- `ws://localhost:9877`에 WebSocket 클라이언트로 연결
- Python에서 받은 명령을 Chrome DevTools Protocol (CDP) 또는 DOM 조작으로 실행
- Reddit 특화 핸들러: 포스트 작성, 댓글 작성, 로그인 확인 등

---

## 데이터 흐름

### browser 커맨드

```
[campaign.toml]
    ↓ schedule.py
[30일 스케줄]
    ↓ autopilot_browser.py (오케스트레이션)
    ├──→ marketing/engine.py (프리플라이트 체크)
    ├──→ comment_generator.py (댓글 생성)
    ├──→ pi_browser.py (브라우저 액션)
    │       ↓ pi_browser_client.py (WebSocket)
    │       ↓ extension/background.js (CDP/DOM)
    │       ↓ Reddit 웹사이트
    └──→ state.py (DB 저장)
           ↓
    [SQLite DB] ←──→ [display.py → 터미널 출력]
```

---

## 30일 스케줄 시스템

### 태스크 유형 (TaskType)

| 값 | 설명 |
|----|------|
| `KARMA_COMMENT` | 카르마 빌딩 댓글 (앱 언급 없음) |
| `SEED_COMMENT` | 씨뿌리기 댓글 (자연스러운 제품 언급) |
| `POST` | 서브레딧에 포스트 게시 |
| `MONITOR` | 기존 포스트 댓글 확인 |
| `REST` | 휴식 |
| `REVIEW` | 복기 + 메트릭 수집 |

### 커스텀 스케줄

DB에 커스텀 스케줄을 저장하여 자동 생성 스케줄을 오버라이드할 수 있습니다.

```bash
# 특정 날짜 수정
python main.py campaign edit-day 5 --clear-tasks --add-karma commandline:terminal,cli

# 자동 생성으로 복원
python main.py campaign edit-day 5 --revert
```

---

## SQLite 스키마

### campaign_state

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `day_id` | TEXT PK | 날짜 ID (예: `day-01`) |
| `status` | TEXT | `pending`, `in_progress`, `completed`, `error` |
| `started_at` | TEXT | 실행 시작 시간 (ISO 8601) |
| `completed_at` | TEXT | 완료 시간 (ISO 8601) |

### submissions

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `day_id` | TEXT | 날짜 ID |
| `reddit_id` | TEXT | Reddit submission ID |
| `subreddit` | TEXT | 서브레딧명 |
| `title` | TEXT | 포스트 제목 |
| `url` | TEXT | 포스트 URL |
| `posted_at` | TEXT | 게시 시간 (ISO 8601) |

### comments

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `reddit_id` | TEXT | Reddit comment ID |
| `submission_id` | TEXT | 대상 submission ID |
| `subreddit` | TEXT | 서브레딧명 |
| `body` | TEXT | 댓글 내용 |
| `comment_type` | TEXT | `karma_build`, `seeding`, `reply`, `auto_reply` |
| `created_at` | TEXT | 작성 시간 (ISO 8601) |

### metrics

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `submission_id` | TEXT | Reddit submission ID |
| `upvotes` | INTEGER | 업보트 수 |
| `comment_count` | INTEGER | 댓글 수 |
| `recorded_at` | TEXT | 수집 시간 (ISO 8601) |
