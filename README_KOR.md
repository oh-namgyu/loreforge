# loreforge

[![CI](https://github.com/oh-namgyu/loreforge/actions/workflows/ci.yml/badge.svg)](https://github.com/oh-namgyu/loreforge/actions/workflows/ci.yml)

셀프호스트 **캐릭터 · 세계관 설정집 스튜디오**. 캐릭터를 한 줄로 적으면
loreforge 가 이를 구조화된 설정집으로 만들어 줍니다 — 프로필, 배경, 성격과
말투, 시그니처 대사, 색 팔레트, 세계관 노트, 그리고 영어 **마스터 이미지
프롬프트**. 원하면 그 프롬프트로 비주얼 캐릭터 보드까지 렌더합니다. 전부 작은
웹 UI 에서 탐색 · 편집 · 내보내기 할 수 있습니다.

모든 데이터는 내 컴퓨터의 평범한 파일로 남습니다. API 키 2개(하나는 필수, 하나는
선택), DB 없음, 계정 없음, 빌드 단계 없음.

*(English — [README.md](README.md))*

## 동작 방식

```
한 줄 컨셉
      │
      ▼
  Generate ──► 구조화된 설정집 JSON  (Anthropic 호출 1회, 첫 응답이 스키마 검증에 실패하면 2회)
      │        프로필 · 배경 · 말투 · 대사 · 팔레트 · 세계관 · master_prompt
      ▼
  UI 에서 검토 · 편집                (API 호출 없음 — 파일 편집일 뿐)
      │
      ▼
  Render (선택) ──► board.png / solo.png   (kind 당 OpenAI 이미지 호출 1회)
      │
      ▼
  Export ──► 이미지를 data URI 로 인라인한 단일 standalone HTML 파일
```

텍스트를 먼저, 이미지를 나중에 두는 2단계 구성은 의도된 것입니다. 아직 읽어보지도
않은 설정집의 이미지 값을 치를 일이 없습니다.

## 스크린샷

<!-- assets/ 에 이미지를 넣고 여기에서 참조하세요. -->

| Home — 북 그리드 & 새 북 폼 | Book 상세 — 바이블 섹션, 팔레트, 보드 |
|------------------------------|----------------------------------------|
| _`assets/home.png`_          | _`assets/detail.png`_                  |

## 빠른 시작

### 로컬 (venv)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # 필수
export OPENAI_API_KEY=sk-...             # 선택, 이미지 렌더 전용
python app.py
```

<http://127.0.0.1:6180> 을 여세요. JSON API 는 `/api` 아래에 있습니다.

비용 없이 UI 만 먼저 보고 싶다면 `LOREFORGE_FAKE_LLM=1 python app.py` — 오프라인
fake 로 전체 앱이 동작합니다. 키도, 네트워크도, 비용도 없습니다.

### Docker

```bash
cp .env.example .env        # ANTHROPIC_API_KEY 와 AUTH_TOKEN 을 채우세요
mkdir -p data && sudo chown 10001:10001 data
docker compose up -d
```

컨테이너는 자기 네트워크 네임스페이스 안에서 `0.0.0.0` 에 바인드하므로
**`AUTH_TOKEN` 이 필수**입니다 — 토큰이 없으면 바인드 가드가 종료코드 1 로
기동을 거부하고, 그 전에 compose 가 먼저 거부합니다. compose 는 호스트의
`127.0.0.1:6180` 으로만 포트를 매핑하므로, 그 줄을 직접 바꾸기 전까지는 네트워크에
아무것도 노출되지 않습니다.

## 설정

모든 설정은 환경변수입니다. [.env.example](.env.example) 참고.

| 변수                     | 기본값             | 의미                                                        |
|--------------------------|--------------------|-------------------------------------------------------------|
| `ANTHROPIC_API_KEY`      | _(미설정)_         | **필수.** 텍스트 생성. 없으면 `/generate` → `503`.           |
| `OPENAI_API_KEY`         | _(미설정)_         | 선택. 이미지 렌더. 없으면 `/render` → `409`.                 |
| `AUTH_TOKEN`             | _(미설정)_         | 토큰 로그인 활성화. **loopback 이 아닌 바인드에는 필수.**    |
| `HOST`                   | `127.0.0.1`        | 바인드 주소.                                                 |
| `PORT`                   | `6180`             | HTTP 포트.                                                   |
| `LOREFORGE_MODEL`        | `claude-sonnet-5`  | 설정집 생성에 쓰는 텍스트 모델.                              |
| `LOREFORGE_IMAGE_MODEL`  | `gpt-image-1`      | board / solo 렌더에 쓰는 이미지 모델.                        |
| `LOREFORGE_DATA`         | `./data`           | `books/<slug>/` 와 삭제 휴지통의 루트.                       |
| `LOREFORGE_TRASH_DAYS`   | `7`                | 기동 시 휴지통에서 정리할 경과 일수.                         |
| `LOREFORGE_FAKE_LLM`     | _(미설정)_         | `1` 이면 두 프로바이더를 오프라인 fake 로 교체 (데모/테스트).|

## 비용

**loreforge 는 사용자 본인의 API 크레딧을 씁니다.** 서비스가 아니고 자체 과금도
없습니다 — 사용자가 넣은 키로 Anthropic 과 OpenAI 를 호출하며, 요금은 각 제공사에
공표된 단가로 사용자가 직접 지불합니다.

| 동작                                       | API 호출                                                    |
|--------------------------------------------|-------------------------------------------------------------|
| 설정집 **Generate**                        | Anthropic 텍스트 호출 1회. 첫 응답이 스키마 검증에 실패하면 **2회** (재시도는 정확히 1회) |
| 보드 **Render**                            | **kind 당** OpenAI 이미지 호출 1회 — board 와 solo 는 별개 호출이라 요청당 1~2회 |
| 탐색 · 편집 · 저장 · 내보내기 · 삭제       | 0 — 이 동작들은 컴퓨터 밖으로 나가지 않습니다               |

텍스트 호출은 출력 4096 토큰으로 제한됩니다. 비싼 쪽은 이미지입니다. 렌더는 절대
자동으로 일어나지 않고 항상 사용자가 누르는 버튼이며, UI 가 버튼 옆에 장당 비용을
명시합니다.

## 프라이버시

- **밖으로 나가는 것:** *Generate* 시 컨셉과 아트 스타일 텍스트가 Anthropic API 로,
  *Render* 시 생성된 마스터 이미지 프롬프트가 OpenAI API 로 전송됩니다. 외부로
  나가는 트래픽은 이것이 전부입니다.
- **나가지 않는 것:** **텔레메트리 · 애널리틱스 · 크래시 리포트 · 업데이트 체크가
  전혀 없습니다.** loreforge 는 그 외 어떤 네트워크 호출도 하지 않습니다.
- **데이터 위치:** 내 디스크의 `data/books/<slug>/` 아래에 평범한 `book.json` 과
  `.png` 파일로 저장됩니다. 삭제한 북은 `data/.trash/` 로 옮겨졌다가 7일 뒤
  정리됩니다. 어디에도 업로드되지 않습니다.
- **API 키**는 서버 환경변수에서만 읽습니다. 디스크에 기록되거나, 응답에 담기거나,
  로그에 남지 않습니다.
- 전송된 내용에는 각 제공사의 데이터 처리 정책이 적용됩니다. 민감한 내용을 넣기
  전에 해당 정책을 확인하세요.

## 보안 모델

loreforge 는 **1인용 셀프호스트** 도구입니다.

- **기본 loopback.** `HOST=127.0.0.1`, Docker 에서는 compose 의 포트 매핑.
- **위험한 노출은 거부.** `AUTH_TOKEN` 없이 loopback 이 아닌 주소에 바인드하면
  경고가 아니라 기동 실패입니다.
- **노출 시 토큰 로그인.** `AUTH_TOKEN` 을 켜면 로그인 폼, 상수시간 토큰 비교,
  HMAC 서명된 `httpOnly` / `SameSite=Strict` 세션 쿠키(8시간 만료)가 활성화됩니다.
  변이 요청은 추가로 same-origin `Origin`/`Referer` 게이트를 통과해야 합니다.
- **자체 TLS 없음.** 트래픽은 평문 HTTP 이며, loopback 이 아닌 바인드 시 그 사실을
  경고로 출력합니다. 외부에 노출하기 전에 TLS 를 종단하는 리버스 프록시 뒤에
  두세요.
- **설계상 단일 워커.** 북 쓰기는 프로세스 내 락으로 직렬화되므로 gunicorn/uwsgi
  멀티 워커 배포는 지원하지 않으며 동시 쓰기를 손상시킵니다. Docker 이미지는
  의도적으로 1개 프로세스만 띄웁니다.

전체 위협 모델: [SECURITY.md](SECURITY.md).

## 결과물 공유

*Export* 는 모든 이미지를 data URI 로 인라인하고 모든 문자열을 서버에서 escape 한
**단일 standalone HTML 파일**을 만듭니다. 외부 참조가 0이라 `file://` 로 오프라인
상태에서, 어떤 브라우저에서든 바로 열립니다. 남에게 건네는 단위는 바로 그 파일
하나입니다. loreforge 자체는 1인용이며, 여기서 말하는 공유는 **내보낸 파일을
공유**한다는 뜻이지 실행 중인 인스턴스를 공유한다는 뜻이 아닙니다.

## 개발

```bash
pip install -r requirements-dev.txt
playwright install chromium      # 브라우저 테스트용, 최초 1회

python -m pytest -q              # 유닛 스위트 — 네트워크·키 불필요
python -m pytest e2e -q          # 실제 서버 대상 브라우저 왕복
```

유닛 스위트는 네트워크도 API 키도 필요 없습니다. 프로바이더 SDK 는 지연 import
되고 테스트는 fake 를 주입합니다. e2e 스위트는 임시 데이터 디렉토리와
`LOREFORGE_FAKE_LLM=1` 로 실제 `app.py` 를 띄우며, chromium 이 없으면 실패가 아니라
**skip** 합니다.

규약: 파일은 300줄 이내, 모든 스타일은 전역 `static/style.css` 에(인라인 스타일
금지), 사용자·LLM 유래 문자열은 `textContent` 로만 주입.
[CONTRIBUTING.md](CONTRIBUTING.md) 참고.

## 한계

- **단일 프로세스, 단일 사용자.** 계정도 역할도 사용자별 데이터도 없습니다.
  `AUTH_TOKEN` 하나를 건네받은 사람 모두가 공유합니다.
- **수평 확장 불가.** 프로세스 내 락 때문에 워커는 1개입니다(위 참고).
- **편집도 생성 스키마를 만족해야 합니다.** `PATCH /api/books/<slug>/bible` 은
  *병합된* 바이블을 검증하므로, 시그니처 대사가 5개 미만이거나 8개 초과, 팔레트가
  4~6개 범위를 벗어나거나, `#RRGGBB` 가 아닌 hex 를 쓰는 편집은 거부되고 아무것도
  기록되지 않습니다.
- **입력 한도.** 컨셉 4000자 이하, 아트 스타일 200자 이하, slug 는
  `[a-z0-9-]{1,64}`.
- **이미지 kind 는 2종** — `board` 와 `solo`. 섹션별 분할 렌더는 미구현입니다.
- **레이트 리밋 없음.** 생성·렌더를 제한하는 장치가 없습니다. 토큰을 공유한다는
  것은 지출 한도를 공유한다는 뜻입니다.
- **TLS 없음, 다국어 UI 없음.** UI 는 영어 단일이고, 선택 가능한 것은 바이블
  *본문* 언어(`en` / `ko`) 뿐입니다.

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
