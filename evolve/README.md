# evolve — EvoLecture 자가 진화 루프

설계는 `PLAN.md` 3절. 여기는 실행법.

```
evolve/common.py       문제 은행 로드 · 페이지 텍스트(예상 문제 제거) · Claude 래퍼(비용 상한, mock)
evolve/solve.py        풀이자 실행 (조건 none/brief/page, k 반복, effort)
evolve/diagnose.py     오답 몰린 개념 · 미검증 주장 · 패치 대상 카드
evolve/propose.py      보강 설명 제안(전공/쉬운 두 벌 + 출처) → 카드에 삽입
evolve/verify.py       유출(문제 문장 베끼기) 검사 · HTML 짝 검사 · R 계산
evolve/round.py        한 라운드 오케스트레이션 → evolve/reports/round-NN.json (→ PR)
evolve/experiments.py  행동 실험 E1(effort) · E2(pass@k) · E3(하네스 효과)
evolve/retro.py        사후 분해: 이미 머지된 라운드의 패치를 비공개 세트까지 써서 다시 잰다
evolve/notes.py        학습 노트(루프가 고쳐 쓰는 규칙 목록)와 항목 제약
evolve/note_propose.py 노트 제안자 (갈래마다 보는 것이 다름)
evolve/counter.py      반례 처치(규칙대로 풀면 틀리는 문항으로 노트를 고침)와 고쳐 쓰기 대조군
evolve/ladder.py       전이 사다리 분해 · 공동 부트스트랩 · 가설 판정
evolve/note_round.py   노트 루프 실험 실행 (탐색/확정, 저장 지점에서 이어 돌리기)
```

## 준비 — 두 가지 백엔드

| 백엔드 | 과금 | 설정 |
|---|---|---|
| **claude-cli** (기본) | Claude **구독**(Pro/Max) 사용량. API 키 불필요 | 터미널에서 `claude` 실행 → `/login` 으로 구독 계정 로그인. 스크립트가 `claude -p` 를 도구 없이 1턴씩 호출 |
| api | Anthropic API 키 과금 | `export ANTHROPIC_API_KEY=...` (설정돼 있으면 자동으로 api 백엔드) |

`EVOLVE_BACKEND=api|claude-cli` 로 강제할 수 있습니다. 구독 백엔드는 5시간 창 사용량 제한을 따르므로 한 라운드(풀이 60회 + 제안 3회 정도)는 무리 없지만 `--k 10` 실험은 창을 나눠 돌리세요.

```bash
python3 -m venv .venv && .venv/bin/pip install anthropic     # api 백엔드일 때만 필요 (cli 는 표준 라이브러리만)
claude -p "ANSWER: 2 라고만 답해" --model claude-haiku-5-5 --output-format json --bare --tools "" --no-session-persistence | head -c 300   # 로그인 확인
```

### 비공개 평가 세트 위치

비공개 세트는 공개 저장소에 두지 않습니다(`.gitignore` 가 `_heldout/` 을 막음). 스크립트는 아래 순서로 찾습니다.

1. 환경 변수 `HELDOUT_DIR`
2. 저장소 안 `_heldout/heldout/` (Actions 가 비공개 저장소를 여기에 체크아웃)
3. 저장소 옆 `../team14-heldout/heldout/` (로컬에서 별도 저장소로 둘 때)

현재 세트(2026-11-24 생성): 8주차 15문항 · 9주차 20문항, 모두 mc/num. 문항의 `basic: true` 는 "자료 없이도 풀리는 것으로 확인된 쉬운 문항"이라는 뜻이며, 리포트는 전체 정답률과 함께 basic 이 아닌 **변별 문항만의 정답률**(`heldout_nonbasic`)을 따로 남깁니다. 2·4주차는 공개 시드와 마찬가지로 자료 없이 다 풀려서 기본 세트에 넣지 않았습니다(예비 보관).

```bash
.venv/bin/python evolve/solve.py --bank heldout --weeks week09 --condition page   # 비공개 세트만 풀어 보기

GitHub Actions 에서 구독으로 돌리려면: 로컬에서 `claude setup-token` 으로 장기 토큰을 만들어 저장소 시크릿 `CLAUDE_CODE_OAUTH_TOKEN` 에 넣습니다(워크플로가 자동 감지). API 키가 있으면 `ANTHROPIC_API_KEY` 시크릿으로도 됩니다.

## 실행

```bash
# API 없이 파이프라인만 확인 (가짜 풀이자, 정답률은 의미 없음)
.venv/bin/python evolve/round.py --weeks week09 --mock

# 실제 1라운드 (풀이자 haiku, 제안자 opus, 상한 $5)
.venv/bin/python evolve/round.py --weeks week02,week04,week08

# 문항당 3회 풀어 진단 (k=1 에서 전부 맞혀 고칠 것이 없을 때. 한 번이라도 틀리는 개념을 약한 개념으로 본다)
.venv/bin/python evolve/round.py --weeks week09 --k 3 --apply

# 사후 분해: 1회차 패치 이전 시점(9b545c6)과 이후 페이지로 공개·비공개 세트를 다시 풀어 O·G 계산
.venv/bin/python evolve/retro.py --round 1 --weeks week09 --before-ref 9b545c6 --after-ref 7c0a4e5 --k 3

# 통과한 패치를 브랜치 + PR 로
.venv/bin/python evolve/round.py --weeks week02,week04,week08 --pr

# 행동 실험
.venv/bin/python evolve/experiments.py e3 --weeks week02,week04,week08
.venv/bin/python evolve/experiments.py e2 --weeks week09 --k 10
.venv/bin/python evolve/experiments.py e1 --weeks week04
```

환경 변수: `EVOLVE_WEAK_MODEL`(기본 claude-haiku-5-5), `EVOLVE_STRONG_MODEL`(기본 claude-opus-5-5), `EVOLVE_MAX_USD`(기본 5).

`--bare` 로 "Not logged in" 이 나는 PC(키체인 대신 앱 로그인만 된 Windows 등)에서는 `EVOLVE_CLI_ISOLATION=--safe-mode` 를 붙여 실행합니다. CLAUDE.md·스킬·플러그인·훅·MCP 는 꺼지고 구독 로그인은 그대로 쓰입니다. 리포트의 `cli_isolation` 에 어떤 옵션으로 돌렸는지 남습니다.

## 노트 루프와 전이 사다리 (교수님 피드백 대응)

페이지 전체를 주면 풀이자가 이미 95~100% 를 맞혀 오버피팅을 볼 수 없다. 그래서 풀이자에게 **루프가 쓴 학습 노트만** 주는 루프를 따로 두고, 향상을 세 단으로 잰다. 설계: `docs/superpowers/specs/2026-11-24-transfer-ladder-counterexample-design.md`, 사전 등록: 실험실 페이지 0-2.

| 단 | 문항 | 위치 |
|---|---|---|
| 1단 기출 | 공개 세트 그대로 | `assets/data/quiz/` |
| 2단 바꿔 쓴 기출 | 같은 사실·같은 정답, 표현만 다름. 기출과 1:1 짝 | 비공개 `ladder/` |
| 3단 다른 측면 | 같은 개념의 다른 사실·사례 | 비공개 `ladder/` |

`O_암기 = Δ1 − Δ2`, `O_측면 = Δ2 − Δ3`, `G = Δ3`. 기존 O 를 둘로 나눈 것이다.

```bash
# 탐색 실행: 프롬프트를 다듬을 때. 기출만 푼다. 사다리는 읽지도 풀지도 않고 리포트도 남기지 않는다
EVOLVE_CLI_ISOLATION=--safe-mode EVOLVE_MAX_USD=25 .venv/bin/python evolve/note_round.py --exp exp1 --week week09 --explore --tag try1

# 확정 실행: evolve/ 를 커밋(동결)한 뒤 한 번. 가설 판정은 이것으로만 한다. 끊기면 같은 명령을 다시 실행하면 이어서 돈다
EVOLVE_CLI_ISOLATION=--safe-mode EVOLVE_MAX_USD=25 .venv/bin/python evolve/note_round.py --exp exp1 --week week09

# 가짜 풀이자로 형식만 확인 (산출물 이름에 -mock 이 붙는다. 커밋하지 않는다)
.venv/bin/python evolve/note_round.py --exp exp1 --week week09 --mock
```

- 사다리 문항 위치: `LADDER_DIR` → 비공개 세트 폴더 옆의 `ladder/` (예: `../team14-heldout/ladder`). 없으면 확정 실행은 멈춘다(`--mock` 이어도). 사다리 없이 돌릴 수 있는 것은 `--explore` 뿐이다(`--explore --mock` 포함).
- 확정 실행(실제 풀이자)은 `evolve/`, `content/briefs/`, `assets/data/quiz/` 에 커밋하지 않은 변경이 있거나, 읽은 사다리 문항의 해시가 `note_round.LADDER_SHA256` 과 다르면 시작하지 않는다. 리포트의 `freeze` 에 커밋·해시·모델·매개변수가 남는다.
- 확정 실행은 실험마다 한 번이다. 실측 리포트가 이미 있으면 그 실행을 이어 돌리는 경우가 아닌 한 시작하지 않는다.
- 풀이자가 빈 응답을 내거나 사용량 제한이 풀리지 않으면 그 단계를 저장하지 않고 멈춘다(빈 응답을 오답으로 채점하지 않는다). 잠시 뒤 같은 명령을 다시 실행하면 그 단계부터 한다.
- 갈래는 한 프로세스에서 순서대로 돌린다. 같은 저장 위치에 두 프로세스를 동시에 돌리지 않는다.
- 저장 지점은 `evolve/runs/<실험>-<주차>-…/` (gitignore). 다른 커밋으로 만든 저장 지점은 이어 쓰지 않는다.
- 산출물: `evolve/reports/ladder-<실험>-<주차>.json`, `evolve/notes/<실험>/<갈래>/<주차>.json` (라운드별 노트).
- 테스트: `python -m pytest tests/evolve` (가짜 문항만 쓴다. 비공개 세트를 읽지 않는다).

## 보상과 분해

- `R = 0.6 · Acc_public + 0.4 · SourcePass` (verify.py). `SourcePass` 는 비교표 배지 집계(`src` 통과 / `check` 미판정)로 근사.
- 라운드 리포트의 `decomposition`: `Δ공개`, `Δ비공개`, `O = Δ공개 − Δ비공개`, `T`(이 설계에서는 호출 수 동일 → 0; 호출 수 효과는 E1·E2 로 별도 측정), `G = Δ − O − T`.
- 비공개 세트가 없으면 O·G 는 `null` 로 남는다. **비공개 세트 없이는 "개선"을 주장하지 않는다.** 대상 주차에 비공개 문항이 없을 때도 마찬가지다(현재 8·9주차만 있음).
- `heldout_nonbasic`: 비공개 세트 중 변별 문항만의 전/후 정답률. 쉬운 문항이 섞이면 Δ비공개가 0 쪽으로 눌리므로 둘을 함께 본다.

### 지금까지의 실측 (9주차, 풀이자 claude-haiku-5-5)

| 기록 | k | Acc 공개 | Acc 비공개 | O | G | 비고 |
|---|---|---|---|---|---|---|
| round-01 (11/23) | 1 | 94.4% → 100% | 세트 없음 | — | — | 패치 1개(c4), CI 겹침 |
| retro-round-01 (11/24) | 3 | 94.4% → 98.1% | 93.3% → 95.0% | +0.020 | +0.017 | round-01 패치를 비공개 세트로 사후 측정. CI 겹침 |
| round-02 (11/24) | 1 | 100% → 100% | 95% → 95% | 0 | 0 | 약한 개념 0개, 패치 0개(기각) |
| round-03 (11/24) | 3 | 98.1% → 100% | 95% → 95% | +0.019 | 0 | 패치 1개(c4), CI 겹침 |

읽는 법: 두 패치 모두 공개 세트 점수는 올렸지만 비공개 세트는 움직이지 않았거나 패치와 무관한 문항 하나가 흔들린 정도다. 신뢰구간이 전부 겹치므로 **"일반화된 개선"이라고 주장할 근거는 아직 없다.** 한계도 함께 적는다.

- 페이지를 주면 풀이자가 비공개 20문항 중 19개를 이미 맞힌다(천장). 올라갈 여지가 한 문항뿐이라 개선을 재기 어렵고, 악화 감지에는 쓸 수 있다.
- 남은 한 문항은 근거가 8주차 자료에만 있어, 9주차 브리프만 보는 제안자가 원리상 보강할 수 없다. 9주차 비공개 문항 20개 중 5개가 이런 문항이다.
- 사후 분해의 비공개 세트는 해당 라운드 뒤에 만들어졌다(사전 등록 측정이 아님).

## 유출 방지 (리워드 해킹 차단)

1. 풀이자에게 주는 페이지 텍스트에서 `section.exam`, `details.quiz` 를 제거한다.
2. 제안자는 문제를 보지 않는다. 약한 **개념 이름**과 브리프·페이지 본문만 본다.
3. 패치 문장이 공개 문제 문장·보기와 25자 이상(또는 60%) 겹치면 라운드를 기각한다.
4. 비공개 세트 점수가 공개 세트만큼 오르지 않으면 O 로 드러난다.

## GitHub Actions

`.github/workflows/evolve.yml` — 매주 일요일 18:00 UTC(월 03:00 KST) + 수동 실행. 시크릿: `CLAUDE_CODE_OAUTH_TOKEN`(구독, `claude setup-token`) **또는** `ANTHROPIC_API_KEY`(API) 중 하나, `HELDOUT_TOKEN`(비공개 저장소 읽기용 PAT, 선택). 결과는 `evolve/round-NN` 브랜치의 PR 로만 올라간다.

## 구독·키 없이 보려면

Claude 구독이나 API 키가 없으면 위 스크립트는 첫 호출에서 실패합니다. 그 경우 배포된 **라이브 실험실**(https://team14-live-lab.vercel.app/)에서 E3 를 버튼으로 돌려 볼 수 있습니다. 같은 `evolve/common.py` · `evolve/solve.py` 의 프롬프트와 채점을 서버에서 부릅니다(`livelab/core.py`). 수업이 끝나 연결을 끊은 뒤에는 저장된 리포트(`evolve/reports/`)만 보여 줍니다.

로컬에서 띄우기: `LIVE_MOCK=1 python -m livelab.dev_server` (가짜 풀이자) 와 `npm --prefix live run dev`. 테스트: `python -m pytest tests/live` · `npm --prefix live run test`.
