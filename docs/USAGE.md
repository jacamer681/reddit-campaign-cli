# 사용 가이드

## 목차

1. [설치](#설치)
2. [브라우저 자동화 설정](#브라우저-자동화-설정)
3. [캠페인 실행](#캠페인-실행)
4. [캠페인 관리](#캠페인-관리)
5. [모니터링 및 리포트](#모니터링-및-리포트)
6. [30일 스케줄](#30일-스케줄)
7. [일반적인 사용 흐름](#일반적인-사용-흐름)
8. [문제 해결](#문제-해결)

---

## 설치

### 요구 사항

- Python 3.11 이상
- Google Chrome 브라우저
- Reddit 계정 (크롬에서 로그인)
- [kimi CLI](https://github.com/anthropics/kimi) — AI 댓글/포스트 자동 생성에 필요

### 설치 절차

```bash
cd redit-market

# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate    # macOS/Linux

# 의존성 설치
pip install -r requirements.txt
```

---

## 브라우저 자동화 설정

크롬 브라우저에 로그인된 Reddit 세션을 이용하여 캠페인을 자동 실행합니다. Reddit API 키는 필요 없습니다.

### 아키텍처

```
┌─────────────┐    WebSocket     ┌──────────────────┐     Chrome     ┌─────────┐
│ Python CLI  │ ←──(port 9877)──→ │ 레딧브라우저 확장 │ ←──────────→  │ Reddit  │
│ main.py     │                  │ background.js    │    CDP/DOM     │  웹사이트 │
│ browser cmd │                  │ (Service Worker) │               │         │
└─────────────┘                  └──────────────────┘               └─────────┘
       │                                │
       ▼                                ▼
  data/campaign.db               크롬 로그인 세션 사용
  (상태/이력 저장)
```

### 1단계: 크롬 확장프로그램 설치

1. 크롬에서 `chrome://extensions` 접속
2. 우측 상단 **개발자 모드** 켜기
3. **압축해제된 확장 프로그램을 로드합니다** 클릭
4. `extension/` 폴더 선택
5. **레딧브라우저** 확장이 설치되면 아이콘이 표시됨

### 2단계: Reddit 로그인

크롬 브라우저에서 https://www.reddit.com 에 **직접 로그인** 해둡니다. 브라우저 자동화는 이 로그인 세션을 그대로 사용합니다.

### 3단계: 캠페인 설정

```bash
# campaign.toml 생성 (인터랙티브)
python main.py campaign init
```

`campaign.toml`에 제품 정보, 타겟 서브레딧, 톤 설정 등을 지정합니다.

### 확장프로그램 연결 확인

크롬에서 확장프로그램 아이콘을 클릭하면 팝업에 연결 상태가 표시됩니다:
- **"연결됨"** (초록): Python 서버와 정상 연결
- **"연결 대기 중..."** (빨강): 서버 미실행 또는 연결 끊김

---

## 캠페인 실행

### 기본 실행

```bash
# 가상환경 활성화
source .venv/bin/activate

# 다음 미완료 날짜 1일 실행
python main.py browser

# 특정 날짜부터 실행
python main.py browser --day 4

# 모든 미완료 날짜 연속 실행
python main.py browser --all

# 미리보기 (실제 포스팅 안 함)
python main.py browser --dry-run

# 날짜 간 딜레이 조절 (기본 30초)
python main.py browser --delay 60
```

실행하면 Python이 WebSocket 서버(포트 9877)를 시작하고, 크롬 확장프로그램이 자동으로 연결됩니다.

### 커맨드 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--day N` | N일차부터 시작 | 다음 미완료 날짜 |
| `--all` | 모든 미완료 날짜 연속 실행 | 1일만 실행 |
| `--dry-run` | 미리보기만 (실제 액션 없음) | off |
| `--delay N` | 날짜 간 대기 시간(초) | 30 |
| `--schedule` | 30일 전체 스케줄 조회 | - |
| `--status` | 진행 현황 확인 | - |
| `--campaign PATH` | campaign.toml 경로 지정 | campaign.toml |

### 실행 흐름

```
python main.py browser
  │
  ├─ 1. WebSocket 서버 시작 (port 9877)
  ├─ 2. 크롬 확장프로그램 연결 대기
  ├─ 3. Reddit 로그인 상태 확인
  ├─ 4. 30일 스케줄 로드 (campaign.toml 기반)
  ├─ 5. 다음 미완료 날짜 실행
  │     │
  │     ├─ KARMA 태스크: r/{sub}/hot → 글 선택 → 댓글 작성
  │     ├─ SEED 태스크: r/{sub}/search → 관련 글 → 씨뿌리기 댓글
  │     ├─ POST 태스크: r/{sub}/submit → 제목/본문 입력 → 게시
  │     └─ MONITOR 태스크: 기존 포스트 댓글 확인
  │
  └─ 6. 결과를 DB에 저장 + 리포트 생성
```

### 안전 장치

- **마케팅 엔진 프리플라이트 체크**: 매 액션 전 계정 건강도, 일일 한도, 타이밍 등급 확인
- **일일 한도**: 포스트 2개/일, 댓글 8개/일 (campaign.toml에서 조정 가능)
- **랜덤 딜레이**: 액션 간 90~180초 랜덤 대기 (봇 탐지 방지)
- **타이밍 차단**: EST 기준 새벽 시간대(트래픽 최저)에는 자동 차단
- **중복 방지**: 이미 댓글 단 글, 이미 포스트한 서브레딧 자동 스킵
- **3단계 댓글 폴백**: JS 삽입 → CDP 재시도 → 페이지 새로고침 후 전체 재시도

---

## 캠페인 관리

### 캠페인 설정

```bash
# 새 캠페인 생성
python main.py campaign init

# 캠페인 설정 확인
python main.py campaign show

# 캠페인 진행 상태
python main.py campaign status
```

### 스케줄 조회 및 수정

```bash
# 30일 전체 계획 조회
python main.py campaign plan

# 특정 날짜 상세 + 댓글 미리보기
python main.py campaign day 5

# 댓글 변형 N개 미리보기
python main.py campaign preview 5 -n 3

# 특정 날짜 스케줄 수정
python main.py campaign edit-day 5 --desc "카르마+씨뿌리기" \
  --clear-tasks --add-karma commandline:terminal,cli

# 특정 날짜 자동 스케줄로 복원
python main.py campaign edit-day 5 --revert

# 특정 날짜 리셋 (재실행 가능)
python main.py campaign reset 5
```

### 활동 이력

```bash
# 전체 이력 조회
python main.py campaign history

# 날짜/유형 필터
python main.py campaign history --date 2026-03-15 --type karma_build
```

---

## 모니터링 및 리포트

```bash
# 진행 현황 대시보드
python main.py browser --status

# 일일 전략 리포트
python main.py report --karma 150

# 웹 대시보드 (브라우저에서 확인)
python main.py web --port 8090

# 터미널 대시보드
python main.py dashboard

# 영향력 분석
python main.py influence --user YOUR_USERNAME
python main.py influence --url "/r/rust/comments/..."
```

---

## 30일 스케줄

### 4단계 구성

| Phase | 기간 | 활동 | 목적 |
|-------|------|------|------|
| Phase 1 | Day 1~8 | 카르마 빌딩만 | 계정 신뢰도 확보 |
| Phase 2 | Day 9~15 | 카르마 + 가벼운 씨뿌리기 | 자연스러운 제품 언급 시작 |
| Phase 3 | Day 16~22 | 씨뿌리기 + 첫 포스트 | 본격적인 콘텐츠 게시 |
| Phase 4 | Day 23~30 | 전체 캠페인 | 포스트 + 씨뿌리기 + 모니터링 |

### 태스크 유형

| 태스크 | 설명 |
|--------|------|
| KARMA | 타겟 서브레딧에서 도움이 되는 댓글 작성 (앱 언급 없음) |
| SEED | 관련 글에 자연스럽게 제품을 언급하는 댓글 |
| POST | 서브레딧에 직접 포스트 게시 |
| MONITOR | 기존 포스트의 새 댓글 확인 |
| REST | 휴식 (활동 없음) |
| REVIEW | 메트릭 수집 + 복기 |

---

## 일반적인 사용 흐름

### 캠페인 시작 전

```bash
# 1. 캠페인 설정
python main.py campaign init

# 2. 스케줄 확인
python main.py campaign plan

# 3. 미리보기
python main.py browser --dry-run
```

### 매일 실행

```bash
# 오늘 날짜 실행 (자동으로 다음 미완료 날짜 선택)
python main.py browser
```

### 진행 확인

```bash
# 상태 확인
python main.py browser --status

# 활동 이력
python main.py campaign history
```

### 날짜 재실행

```bash
# 특정 날짜 리셋 후 재실행
python main.py campaign reset 5
python main.py browser --day 5
```

---

## 문제 해결

### "연결 대기 중..." (확장프로그램 연결 안 됨)

- `python main.py browser`가 실행 중인지 확인
- 크롬에서 `chrome://extensions` → 레딧브라우저가 활성화되어 있는지 확인
- 포트 9877이 다른 프로세스에 의해 사용 중인지 확인: `lsof -i :9877`
- 확장프로그램을 새로고침(리로드)해보세요

### Reddit 로그인 안 됨

- 크롬 브라우저에서 https://www.reddit.com 에 직접 로그인되어 있는지 확인
- 시크릿(프라이빗) 모드에서는 확장프로그램이 동작하지 않을 수 있습니다

### 댓글 작성 실패

- Reddit UI가 업데이트되면 DOM 선택자가 변경될 수 있습니다
- 확장프로그램 콘솔(`chrome://extensions` → 레딧브라우저 → Service Worker)에서 에러 로그 확인
- 3단계 폴백(JS 삽입 → CDP → 전체 재시도) 모두 실패한 경우, 크롬을 재시작해보세요

### 타이밍 차단 (BLOCKED)

- EST 기준 새벽 시간대(트래픽 최저)에는 자동으로 액션이 차단됩니다
- 한국 시간 기준 낮~저녁에 실행하면 EST 오전~오후에 해당하여 정상 동작합니다

### DB 초기화

캠페인 데이터를 처음부터 다시 시작하려면:

```bash
rm data/campaign.db
```

다음 실행 시 자동으로 새 DB가 생성됩니다.
