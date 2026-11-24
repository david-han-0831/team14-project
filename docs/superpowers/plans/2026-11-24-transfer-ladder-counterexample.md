# 전이 사다리와 반례 처치 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 노트만 보는 풀이자로 자가 진화의 오버피팅을 `O_암기 + O_측면` 으로 나눠 재고, 반례 문항 처치가 그것을 줄이는지 대조 갈래와 비교한다.

**Architecture:** 기존 `evolve/` 옆에 노트 루프를 새로 둔다. `notes.py`(노트 저장·제약) → `note_propose.py`(갈래별 제안) → `counter.py`(반례·고쳐 쓰기) → `ladder.py`(분해·부트스트랩·판정) → `note_round.py`(실험 실행, 저장 지점, 리포트). 풀이와 채점은 기존 `solve.run` 을 그대로 쓴다. 페이지 루프(`round.py`)는 건드리지 않는다.

**Tech Stack:** Python 3 표준 라이브러리만(numpy 없음, 기존 코드와 같음), pytest, 구독 백엔드 `claude -p`, 정적 HTML/JS(`lab/index.html`).

**Spec:** `docs/superpowers/specs/2026-11-24-transfer-ladder-counterexample-design.md` (실행자는 계획과 함께 읽는다. 절 번호는 그 문서 기준)

**실행 방식:** 사용자가 "구현 계획 세우고 진행해줘"라고 했으므로 이 세션에서 직접 구현한다. 확정 실행 전마다 독립 검토자 1회(Task 8, 11 의 첫 단계).

## Global Constraints

- 라운드 수 3, 문항당 풀이 3회, 라운드당 새 항목 최대 5개. ③ 제안은 덧붙이기만.
- 노트 항목: 규칙 문장 3문장 이하. 보기 번호·위치, 문항 id 를 가리키는 표현 금지.
- 모델: 풀이자 `claude-haiku-5-5`, 제안·반례 출제·고쳐 쓰기 `claude-opus-5-5`, 반례 거르기 `claude-sonnet-5-5`.
- 9주차에서 브리프를 보는 역할에게는 8주차와 9주차 브리프를 함께 준다. 다른 주차는 그 주차 브리프만.
- 부트스트랩: 1만 번, 시드 14(기존 `bootstrap_ci` 와 같은 값), 1·2단 짝 번호 공동 추출 + 3단 독립 추출을 한 번에.
- 사다리 평가는 기준선과 3라운드 뒤 두 번. 판정 시점은 3라운드 뒤.
- 제안자·반례 출제자·거르는 풀이자의 입력에 사다리 2·3단 문항이 들어가면 안 된다. 사다리·비공개 문항은 공개 저장소에 커밋하지 않는다(`_heldout/` 은 gitignore).
- 탐색 실행은 1단(기출)만 푼다. 사다리 2·3단을 풀거나 그 결과를 보는 것은 동결 뒤 확정 실행에서만.
- mock 실행의 산출물은 `mock: true` 로 표시하고 커밋하지 않는다.
- 실행 환경: `EVOLVE_CLI_ISOLATION=--safe-mode`, `EVOLVE_MAX_USD=25`. 파이썬은 `/Users/ethan.son/workspaces/team14-project/.venv/bin/python`.
- 테스트 자료는 가짜 문항만 쓴다. 테스트에서 `_heldout/` 을 읽지 않는다.
- 모듈 import 는 기존 방식(`from common import ...`, `evolve/` 를 sys.path 에 넣음). 주석·로그는 한국어, 기존 파일의 밀도에 맞춘다.
- 격리 세션 제약: 셸 명령은 작업 트리에서 단순한 형태로 하나씩 실행한다.

## Review Focus

1. 제안자·반례 출제자가 JSON 이 아닌 글이나 제약을 어긴 항목을 낸다 → 그 항목만 버리고 사유를 기록하며 라운드는 계속된다 (Task 3, 9).
2. 어떤 라운드에 기출을 전부 맞혀 틀린 문항이 없다 → 제안 없이 다음 라운드로 넘어가고 마지막 평가까지 간다 (Task 5).
3. 확정 실행이 중간에 끊겼다가 다시 실행된다 → 끝난 단계는 다시 호출하지 않고, 노트 항목이 중복되지 않는다 (Task 5).
4. 사다리 문항 파일이 없는 컴퓨터(조원 PC, Actions)에서 확정 실행을 시도한다 → 한 줄 안내와 함께 멈춘다. `--explore` 와 `--mock` 은 사다리 없이 돈다 (Task 5).
5. 어떤 단의 기준선 정답률이 100% 다 → 정규화 향상은 `None` 으로 나오고 판정은 "구분 못 함"이 된다. 예외로 죽지 않는다 (Task 4).

---

## File Structure

| 파일 | 책임 |
|---|---|
| `evolve/common.py` (수정) | `brief_bundle`, 풀이 조건 `notes`, 사다리 은행 읽기, 리포트 색인에 `ladders`, mock 응답 종류 추가 |
| `evolve/solve.py` (수정) | `run()` 이 문항 목록과 참고 글을 직접 받을 수 있게 |
| `evolve/notes.py` (신규) | 노트 자료형, 항목 제약 검사, 풀이자용 글 |
| `evolve/note_propose.py` (신규) | 갈래별 제안자 입력 조립, 응답 해석, 제약·유출 검사 |
| `evolve/counter.py` (신규) | 반례 출제·거르기·풀기·고치기, 반례 없는 고쳐 쓰기 |
| `evolve/ladder.py` (신규) | 문항별 향상, 분해, 공동 부트스트랩, 갈래 비교, 가설 판정 |
| `evolve/note_round.py` (신규) | 실험 1·2 실행, 저장 지점, 동결 정보, 리포트 |
| `tests/evolve/` (신규) | 위 모듈 테스트. `conftest.py` 가 `evolve/` 를 path 에 넣고 가짜 문항·가짜 LLM 제공 |
| `lab/index.html` (수정) | "전이 사다리" 칸, 사전 등록 문구 |
| `evolve/README.md`, `PLAN.md` (수정) | 실행법, 분해 식 연결 |
| 비공개 `_heldout/tools/ladder_items.py`, `_heldout/ladder/` | 사다리 문항 조립·점검 (공개 저장소 밖) |

---

### Task 1: 풀이 배관 (노트 조건, 브리프 묶음, 사다리 은행)

**Files:**
- Modify: `evolve/common.py` (`load_bank`, `context_for`, `update_report_index`, 새 함수 `brief_bundle`, `ladder_dir`)
- Modify: `evolve/solve.py` (`run`)
- Create: `tests/evolve/conftest.py`, `tests/evolve/test_plumbing.py`

**Interfaces:**
- Produces:
  - `common.brief_bundle(week: str) -> str` — `week09` 이면 `brief_text("week08") + "\n\n" + brief_text("week09")`, 그 밖에는 `brief_text(week)`.
  - `common.ladder_dir() -> Path` — `LADDER_DIR` 환경 변수 → `heldout_dir().parent / "ladder"`.
  - `common.load_bank("ladder", weeks)` — `ladder_dir()/index.json` 을 `heldout` 과 같은 방식으로 읽는다. 문항의 `rung`, `pair` 필드를 그대로 둔다. 파일이 없으면 `[]`.
  - `common.context_for(week, "notes", html_override=None, notes_text: str = "") -> str` — `notes` 조건이면 `notes_text` 를 돌려준다.
  - `solve.run(args, llm=None, html_override=None, patched=False, bank: list[dict] | None = None, context: str | None = None) -> dict` — `bank` 를 주면 `load_bank` 대신 그 목록을 풀고, `context` 를 주면 모든 문항의 참고 글로 그것을 쓴다(빈 문자열이면 참고 자료 블록 없이). 결과 행에 문항의 `rung`, `pair` 를 있으면 복사한다.
  - `tests/evolve/conftest.py`: `fake_items(n, prefix, concepts=None) -> list[dict]`(객관식 4지, 정답 0), `ScriptedLLM(fn)`(`ask(model, system, user, **kw)` 호출을 `fn` 에 넘기고 `calls` 에 기록, `usage.to_dict()` 제공).

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/evolve/test_plumbing.py`)

```python
def test_brief_bundle_week09_includes_week08(monkeypatch):
    monkeypatch.setattr(common, "brief_text", lambda w: f"<{w}>")
    assert common.brief_bundle("week09") == "<week08>\n\n<week09>"
    assert common.brief_bundle("week04") == "<week04>"

def test_notes_condition_returns_given_text():
    assert common.context_for("week09", "notes", notes_text="규칙 A") == "규칙 A"
    assert common.context_for("week09", "notes") == ""

def test_ladder_bank_missing_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("LADDER_DIR", str(tmp_path / "none"))
    assert common.load_bank("ladder", ["week09"]) == []

def test_ladder_bank_keeps_rung_and_pair(tmp_path, monkeypatch):
    # index.json + week09.json(문항 2개: rung T2 pair p1 / rung T3) 를 tmp 에 쓰고
    monkeypatch.setenv("LADDER_DIR", str(tmp_path))
    bank = common.load_bank("ladder", ["week09"])
    assert [(q["rung"], q.get("pair")) for q in bank] == [("T2", "p1"), ("T3", None)]
    assert all(q["bank"] == "ladder" for q in bank)

def test_run_with_explicit_bank_and_context(scripted_llm):
    llm = scripted_llm(lambda model, system, user, **kw: "ANSWER: 1")
    out = solve.run(ns(bank="public", weeks="week09", condition="notes", k=2), llm, bank=fake_items(3, "x"), context="노트 글")
    assert out["summary"]["n"] == 3 and out["summary"]["acc"] == 1.0
    assert all("[참고 자료" in c["user"] and "노트 글" in c["user"] for c in llm.calls)

def test_run_with_empty_context_has_no_reference_block(scripted_llm):
    llm = scripted_llm(lambda *a, **kw: "ANSWER: 2")
    solve.run(ns(bank="public", weeks="week09", condition="notes", k=1), llm, bank=fake_items(1, "x"), context="")
    assert "[참고 자료" not in llm.calls[0]["user"]
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/python -m pytest tests/evolve/test_plumbing.py -q` → 6 failed (속성·인자 없음)
- [ ] **Step 3: 구현** — 위 Interfaces 그대로. `update_report_index` 는 `ladder-*.json` 을 `{"file", "exp", "week", "date", "mock"}` 목록 `ladders` 로 색인에 추가한다.
- [ ] **Step 4: 통과 확인** — `.venv/bin/python -m pytest tests/evolve tests/live -q` → 전부 통과(기존 54 포함)
- [ ] **Step 5: Commit** — `evolve: 노트 조건·브리프 묶음·사다리 은행 읽기`

### Task 2: 학습 노트 (`evolve/notes.py`)

**Files:**
- Create: `evolve/notes.py`, `tests/evolve/test_notes.py`

**Interfaces:**
- Produces:
  - `new_notes(week: str, arm: str) -> dict` — `{"week", "arm", "round": 0, "entries": []}`
  - `check_rule(rule: str) -> list[str]` — 위반 사유 목록. 사유 코드: `"too_long"`(문장 4개 이상. 문장은 `.`, `?`, `!`, `다.` 뒤 공백·끝으로 끊는다), `"option_ref"`(`\d번`, `①~⑤`, `보기 \d`, `첫 번째 보기` 류), `"item_ref"`(`w\d\d[a-z]?-`, `문항 \d`, `\d번 문제`), `"empty"`.
  - `add_entry(notes, concept, rule, sources, origin_from, round_no) -> dict` — id 는 `n{순번:02d}`. `check_rule` 위반이면 `ValueError`.
  - `revise_entry(notes, entry_id, new_rule, origin_from, round_no) -> None` — 이전 규칙을 `history` 에 쌓는다. `delete_entry(notes, entry_id, round_no) -> None` 은 항목을 `entries` 에서 빼 `deleted` 목록으로 옮긴다.
  - `notes_text(notes) -> str` — 항목이 없으면 `""`. 있으면 `"[학습 노트]\n- (개념) 규칙"` 줄들.
  - `load_notes(path: Path) -> dict`, `save_notes(notes, path: Path) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
@pytest.mark.parametrize("rule,code", [
    ("", "empty"),
    ("하나다. 둘이다. 셋이다. 넷이다.", "too_long"),
    ("이 경우 3번을 고른다.", "option_ref"),
    ("정답은 ②이다.", "option_ref"),
    ("w09a-c28 의 답은 MCTS 다.", "item_ref"),
])
def test_check_rule_flags(rule, code):
    assert code in notes.check_rule(rule)

def test_check_rule_accepts_three_sentences_with_numbers():
    assert notes.check_rule("pass@k 는 k 번 중 한 번이라도 맞히면 성공이다. p=0.2, k=10 이면 0.893 이다. 결함 문항은 k 를 늘려도 0 이다.") == []

def test_add_then_text_and_ids():
    n = notes.new_notes("week09", "seen")
    notes.add_entry(n, "pass-at-k", "규칙 하나다.", ["week09 개념 9"], "public-fail", 1)
    notes.add_entry(n, "aflow", "규칙 둘이다.", ["week08 개념 6"], "public-fail", 1)
    assert [e["id"] for e in n["entries"]] == ["n01", "n02"]
    assert notes.notes_text(n) == "[학습 노트]\n- (pass-at-k) 규칙 하나다.\n- (aflow) 규칙 둘이다."

def test_empty_notes_text_is_empty_string():
    assert notes.notes_text(notes.new_notes("week09", "seen")) == ""

def test_add_entry_rejects_violation():
    with pytest.raises(ValueError):
        notes.add_entry(notes.new_notes("week09", "seen"), "c", "3번을 고른다.", [], "public-fail", 1)

def test_revise_keeps_history_and_delete_moves_entry():
    n = notes.new_notes("week09", "seen+ce")
    notes.add_entry(n, "c", "처음 규칙이다.", [], "public-fail", 1)
    notes.revise_entry(n, "n01", "고친 규칙이다.", "counterexample", 1)
    assert n["entries"][0]["rule"] == "고친 규칙이다." and n["entries"][0]["history"][0]["rule"] == "처음 규칙이다."
    notes.delete_entry(n, "n01", 1)
    assert n["entries"] == [] and n["deleted"][0]["id"] == "n01"
    notes.add_entry(n, "c", "새 규칙이다.", [], "public-fail", 2)
    assert n["entries"][0]["id"] == "n02"      # 지운 id 를 다시 쓰지 않는다
```

- [ ] **Step 2: 실패 확인** — `pytest tests/evolve/test_notes.py -q` → 모듈 없음
- [ ] **Step 3: 구현** — Interfaces 그대로
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: Commit** — `evolve: 학습 노트 자료형과 항목 제약`

### Task 3: 갈래별 제안자 (`evolve/note_propose.py`)

**Files:**
- Create: `evolve/note_propose.py`, `tests/evolve/test_note_propose.py`
- Modify: `evolve/common.py` (`LLM._mock_answer` 에 `kind == "note_propose"`)

**Interfaces:**
- Consumes: `notes.check_rule/add_entry/notes_text`, `common.brief_bundle`, `verify.leakage`
- Produces:
  - `ARMS = ("seen", "concept", "seen+ce", "seen+rev")`, `sees_items(arm) -> bool`(`concept` 만 False)
  - `build_user(arm: str, week: str, failed: list[dict], notes: dict, brief: str) -> str` — `failed` 는 틀린 기출 문항(정답 포함) 목록. `seen` 계열은 문항마다 문제·보기·정답 보기 **내용**을 넣는다(번호는 넣지 않는다). `concept` 은 개념 이름의 중복 없는 목록만 넣는다.
  - `parse_entries(text: str) -> list[dict]` — `{"entries": [{"concept", "rule", "sources"}]}` JSON 을 찾는다. 못 찾으면 `[]`.
  - `propose_entries(arm, week, failed, notes, llm, public_bank, max_new=5) -> dict` — `{"added": [entry...], "rejected": [{"rule", "why": [...]}], "raw_n": int}`. 걸러내는 순서: 형식(개념·규칙·출처 없음) → `check_rule` → (`concept` 만) `verify.leakage`. 통과한 것 중 앞에서 `max_new` 개를 `notes` 에 덧붙인다. `failed` 가 비면 LLM 을 부르지 않고 빈 결과.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
SECRET = "사다리전용표식XYZ"

def test_concept_arm_never_sees_item_text():
    failed = fake_items(2, "p", concepts=["aflow", "aflow"])
    user = np_.build_user("concept", "week09", failed, notes.new_notes("week09", "concept"), "브리프")
    assert "aflow" in user and failed[0]["q"] not in user and failed[0]["options"][0] not in user

def test_seen_arm_sees_question_and_answer_text_but_no_position():
    failed = fake_items(1, "p")
    user = np_.build_user("seen", "week09", failed, notes.new_notes("week09", "seen"), "브리프")
    assert failed[0]["q"] in user and failed[0]["options"][failed[0]["answer"]] in user
    assert "정답: 1" not in user and "1번" not in user

def test_proposer_input_is_built_only_from_its_arguments():
    # 사다리 문항은 build_user 의 인자가 아니다. 모듈이 은행을 직접 읽지 않는지 확인한다.
    src = Path(np_.__file__).read_text(encoding="utf-8")
    assert "load_bank" not in src and "ladder" not in src

def test_propose_filters_and_caps(scripted_llm):
    payload = {"entries": [{"concept": "c", "rule": f"규칙 {i} 이다.", "sources": ["s"]} for i in range(7)]
               + [{"concept": "c", "rule": "3번을 고른다.", "sources": ["s"]}, {"concept": "c", "rule": "출처 없다.", "sources": []}]}
    llm = scripted_llm(lambda *a, **kw: json.dumps(payload, ensure_ascii=False))
    n = notes.new_notes("week09", "seen")
    out = np_.propose_entries("seen", "week09", fake_items(1, "p"), n, llm, public_bank=[], max_new=5)
    assert len(out["added"]) == 5 and len(n["entries"]) == 5
    assert {tuple(r["why"]) for r in out["rejected"]} >= {("option_ref",), ("no_sources",)}

def test_propose_with_garbage_output_adds_nothing(scripted_llm):       # Review Focus 1
    n = notes.new_notes("week09", "seen")
    out = np_.propose_entries("seen", "week09", fake_items(1, "p"), n, scripted_llm(lambda *a, **kw: "죄송합니다"), public_bank=[])
    assert out["added"] == [] and out["raw_n"] == 0 and n["entries"] == []

def test_propose_without_failures_makes_no_call(scripted_llm):
    llm = scripted_llm(lambda *a, **kw: "{}")
    np_.propose_entries("seen", "week09", [], notes.new_notes("week09", "seen"), llm, public_bank=[])
    assert llm.calls == []

def test_concept_arm_applies_leak_check(scripted_llm):
    item = fake_items(1, "p")[0]
    payload = {"entries": [{"concept": "c", "rule": item["q"], "sources": ["s"]}]}     # 기출 문장을 그대로 베낀 규칙
    out = np_.propose_entries("concept", "week09", [item], notes.new_notes("week09", "concept"),
                              scripted_llm(lambda *a, **kw: json.dumps(payload, ensure_ascii=False)), public_bank=[{**item, "week": "week09"}])
    assert out["added"] == [] and out["rejected"][0]["why"] == ["leak"]
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 시스템 프롬프트는 구현자 재량(설계 6절). 반드시 담을 것: 출력은 JSON 하나, 규칙은 3문장 이하의 설명문, 보기 번호·문항 번호를 쓰지 않는다, 브리프에 없는 내용은 쓰지 않는다, 출처는 브리프의 절 이름. `fake_items` 의 문제 문장은 유출 검사에 걸리도록 25자 이상으로 만든다(conftest 수정). mock 응답은 규칙 1개를 내는 JSON.
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: Commit** — `evolve: 갈래별 노트 제안자`

### Task 4: 분해·부트스트랩·판정 (`evolve/ladder.py`)

**Files:**
- Create: `evolve/ladder.py`, `tests/evolve/test_ladder.py`

**Interfaces:**
- Produces (모두 순수 함수, LLM 호출 없음):
  - `item_acc(run: dict) -> dict[str, float]` — `solve.run` 결과에서 `{id: acc}`.
  - `rung_table(public_bank, ladder_bank) -> dict` — `{"T1": [기출 id...], "T2": [짝 id...] (T1 과 같은 순서), "T3": [id...], "dropped_pairs": [기출 id...]}`. 짝(`pair`)이 없는 기출은 T1 에서도 뺀다.
  - `arm_arrays(table, base: dict[str, dict[str, float]], after: dict[str, dict[str, float]]) -> dict` — 단마다 `{"base": [...], "after": [...]}` (table 순서). `base`/`after` 의 키는 `"T1"|"T2"|"T3"`.
  - `decompose(arr) -> dict` — `d1, d2, d3, O_mem, O_facet, G, O` 와 정규화판 `nd1.., nO_mem, nO_facet, nG`(단의 기준선 평균이 1 이면 그 단의 값과 거기서 파생되는 값은 `None`), 단별 `base1, base2, base3`.
  - `joint_bootstrap(arrs: dict[str, dict], n_boot=10000, seed=14) -> dict` — `arrs` 는 `{갈래: arm_arrays 결과}`. 반복마다 짝 번호 한 벌(T1·T2 공용)과 T3 번호 한 벌을 뽑아 **모든 갈래에 같은 번호**를 쓴다. 반환 `{갈래: {통계: {"point", "lo", "hi"}}, "diff": {"A|B": {통계: {...}}}}` (`diff` 는 모든 갈래 쌍의 A−B).
  - `judge(boot: dict, n_pairs: int, exp: str) -> dict` — 설계 3.7 의 표 그대로:
    - `exp1`: `H1` = `"확인"` if `boot["seen"]["O"]["lo"] > 0` else `"확인 못 함"`. `H2`: H1 이 확인이 아니면 `"판정 안 함"`; `boot["seen"]["O_facet-O_mem"]["lo"] > 0` 이고 `nO_facet-nO_mem` 의 `point > 0` 이면 `"확인"`, 아니면 `"구분 못 함"`. `H4`: `{"O": 부호 문자열, "d1": 부호 문자열}` (`diff["concept|seen"]` 의 point 부호. 확인·기각이라는 말을 쓰지 않는다).
    - `exp2`: `H3` = `"확인"` if `diff["seen+rev|seen+ce"]["O"]["lo"] > 0` and `diff["seen+ce|seen+rev"]["d1"]["point"] >= -1 / n_pairs` else `"확인 못 함"`. `seen` 의 `O.lo` 는 `"H1_재현"` 칸에 `"재현"`/`"재현 안 됨"`.
  - 통계 이름 목록에 `"O_facet-O_mem"`, `"nO_facet-nO_mem"` 을 포함한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def arr(b1, a1, b2, a2, b3, a3):
    return {"T1": {"base": b1, "after": a1}, "T2": {"base": b2, "after": a2}, "T3": {"base": b3, "after": a3}}

def test_identity_holds():
    d = ladder.decompose(arr([0, .5, 1], [1, 1, 1], [0, .5, 1], [1, .5, 1], [0, 0, 1, 1], [0, .5, 1, 1]))
    assert d["d1"] == pytest.approx(d["O_mem"] + d["O_facet"] + d["G"])
    assert d["O"] == pytest.approx(d["d1"] - d["d3"])

def test_pure_memorisation_shows_up_as_O_mem():
    d = ladder.decompose(arr([0, 0], [1, 1], [0, 0], [0, 0], [0, 0], [0, 0]))
    assert (d["O_mem"], d["O_facet"], d["G"]) == (1.0, 0.0, 0.0)

def test_normalised_gain_is_none_at_ceiling():                          # Review Focus 5
    d = ladder.decompose(arr([0, 0], [1, 1], [0, 0], [1, 1], [1, 1], [1, 1]))
    assert d["nd3"] is None and d["nO_facet"] is None and d["nd1"] == 1.0

def test_rung_table_drops_unpaired_public_items():
    pub = fake_items(3, "p")
    lad = [{**fake_items(1, "t2")[0], "rung": "T2", "pair": "p-1"}, {**fake_items(1, "t2b")[0], "rung": "T2", "pair": "p-3"}, {**fake_items(1, "t3")[0], "rung": "T3"}]
    t = ladder.rung_table(pub, lad)
    assert t["T1"] == ["p-1", "p-3"] and t["T2"] == ["t2-1", "t2b-1"] and t["dropped_pairs"] == ["p-2"]

def test_bootstrap_is_reproducible_and_joint():
    a = arr([0] * 6, [1, 1, 1, 0, 0, 0], [0] * 6, [1, 1, 1, 0, 0, 0], [0] * 5, [0] * 5)
    b1 = ladder.joint_bootstrap({"seen": a}, n_boot=500, seed=14)
    b2 = ladder.joint_bootstrap({"seen": a}, n_boot=500, seed=14)
    assert b1 == b2
    # T1 과 T2 가 문항마다 같으면 짝 추출에서는 O_mem 이 매번 정확히 0 이다 (따로 뽑으면 0 이 아니다)
    assert b1["seen"]["O_mem"]["lo"] == b1["seen"]["O_mem"]["hi"] == 0.0

def test_arm_diff_uses_same_resample():
    a = arr([0] * 4, [1, 1, 0, 0], [0] * 4, [1, 1, 0, 0], [0] * 4, [0] * 4)
    boot = ladder.joint_bootstrap({"x": a, "y": a}, n_boot=300, seed=14)
    assert boot["diff"]["x|y"]["O"]["lo"] == boot["diff"]["x|y"]["O"]["hi"] == 0.0

def test_judge_exp1_rules():
    def s(point, lo, hi): return {"point": point, "lo": lo, "hi": hi}
    boot = {"seen": {"O": s(.3, .1, .5), "O_facet-O_mem": s(.2, -.05, .4), "nO_facet-nO_mem": s(.2, 0, .4)},
            "diff": {"concept|seen": {"O": s(-.1, -.3, .1), "d1": s(-.05, -.2, .1)}}}
    j = ladder.judge(boot, n_pairs=18, exp="exp1")
    assert j["H1"] == "확인" and j["H2"] == "구분 못 함" and j["H4"] == {"O": "작다", "d1": "작다"}
    boot["seen"]["O"] = s(.1, -.02, .3)
    assert ladder.judge(boot, 18, "exp1")["H2"] == "판정 안 함"

def test_judge_exp2_needs_both_conditions():
    def s(point, lo, hi): return {"point": point, "lo": lo, "hi": hi}
    boot = {"seen": {"O": s(.3, .1, .5)}, "diff": {"seen+rev|seen+ce": {"O": s(.15, .02, .3)}, "seen+ce|seen+rev": {"d1": s(-.10, -.2, 0)}}}
    assert ladder.judge(boot, 18, "exp2")["H3"] == "확인 못 함"          # Δ1 손실이 1/18 보다 크다
    boot["diff"]["seen+ce|seen+rev"]["d1"] = s(-.05, -.2, .1)
    assert ladder.judge(boot, 18, "exp2")["H3"] == "확인"
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 구간은 정렬한 값의 2.5%·97.5% 위치. 정규화 통계는 반복마다 그 표본의 기준선 평균으로 나누고, 분모가 0 인 반복은 그 통계에서 빼며 남은 반복이 전체의 90% 미만이면 구간을 `None` 으로 둔다.
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: Commit** — `evolve: 전이 사다리 분해와 공동 부트스트랩, 가설 판정`

### Task 5: 실험 1 실행기 (`evolve/note_round.py`)

**Files:**
- Create: `evolve/note_round.py`, `tests/evolve/test_note_round.py`

**Interfaces:**
- Consumes: Task 1~4 전부, `diagnose.diagnose` 는 쓰지 않는다(틀린 **문항**이 필요하므로 풀이 결과에서 `acc < 1` 인 문항을 직접 뽑는다).
- Produces:
  - `EXPERIMENTS = {"exp1": ["seen", "concept"], "exp2": ["seen", "seen+ce", "seen+rev"]}`, `ROUNDS = 3`, `K = 3`, `MAX_NEW = 5`
  - `class Store(root: Path)` — `get(key) -> dict | None`, `put(key, obj) -> None`. 키는 `"baseline/T1"`, `"seen/r2/solve"`, `"seen/r2/proposed"`, `"seen/r2/notes"`, `"seen/final/T2"` 같은 경로. 파일은 `root/<key>.json`.
  - `run_experiment(exp: str, week: str, llm, store: Store, *, explore: bool, mock: bool, arms: list[str] | None = None, public_bank=None, ladder_bank=None) -> dict | None` — 탐색 실행이면 사다리를 읽지도 풀지도 않고 `None` 을 돌려준다(1단 라운드별 정답률만 `store` 와 로그에). 확정 실행이면 리포트 dict.
  - 리포트 필드: `exp, week, date, mock, k, rounds, model, n: {T1, T2, T3}, dropped_pairs, baseline: {T1, T2, T3}, arms: {갈래: {"t1_by_round": [r0..r3], "final": {T1, T2, T3}, "decomp": {...}, "notes_n": int, "rejected_n": int}}, boot, judge, freeze: {commit, dirty, ladder_sha256, params}, resumed: [시각...], usage`.
  - CLI: `python evolve/note_round.py --exp exp1 --week week09 [--explore] [--mock] [--arms seen,concept] [--tag NAME]`. 저장 위치 `evolve/runs/<exp>-<week>[-<tag>]/`. 확정 실행은 리포트를 `evolve/reports/ladder-<exp>-<week>.json`, 노트를 `evolve/notes/<exp>/<갈래>/<week>.json`(라운드별 스냅샷 포함) 에 쓰고 `update_report_index()` 를 부른다.
  - 확정 실행 조건: (a) 사다리 은행이 비어 있으면 `SystemExit("사다리 문항이 없습니다 …")`. (b) `mock` 이 아니고 `git status --porcelain -- evolve` 가 비어 있지 않으면 `SystemExit("동결되지 않았습니다 …")`. (c) 같은 저장 위치에 다른 커밋으로 만든 저장 지점이 있으면 중단.
  - `exp1` 에서는 Task 9·10 의 ④ 단계를 부르지 않는다. `exp2` 갈래는 Task 10 에서 붙인다(이 Task 에서는 `NotImplementedError`).

- [ ] **Step 1: 실패하는 테스트 작성** (가짜 문항, `ScriptedLLM`)

```python
def make_llm(correct_ids_with_notes):
    """풀이자: 노트가 있으면 지정한 문항만 맞힌다. 제안자: 규칙 1개를 낸다."""
    ...

def test_exp1_end_to_end_report_shape(tmp_path):
    rep = nr.run_experiment("exp1", "weekXX", llm, nr.Store(tmp_path), explore=False, mock=True, public_bank=pub, ladder_bank=lad)
    assert set(rep["arms"]) == {"seen", "concept"} and rep["n"] == {"T1": 4, "T2": 4, "T3": 3}
    assert len(rep["arms"]["seen"]["t1_by_round"]) == 4
    d = rep["arms"]["seen"]["decomp"]
    assert d["d1"] == pytest.approx(d["O_mem"] + d["O_facet"] + d["G"])
    assert rep["judge"]["H1"] in ("확인", "확인 못 함") and rep["mock"] is True

def test_baseline_is_shared_and_round1_reuses_it(tmp_path):
    # 풀이 호출 수 = 기준선 (4+4+3)*3 + 갈래마다 [r2, r3 풀이 4*3*2 + 최종 평가 (4+4+3)*3]
    assert n_solver_calls(llm) == 33 + 2 * (24 + 33)

def test_explore_never_touches_ladder(tmp_path):
    out = nr.run_experiment("exp1", "weekXX", llm, nr.Store(tmp_path), explore=True, mock=True, public_bank=pub, ladder_bank=lad)
    assert out is None
    assert not any(SECRET in c["user"] for c in llm.calls)        # 사다리 문항의 표식이 어떤 호출에도 없다

def test_ladder_items_never_reach_proposer(tmp_path):
    nr.run_experiment("exp1", "weekXX", llm, nr.Store(tmp_path), explore=False, mock=True, public_bank=pub, ladder_bank=lad)
    assert not any(SECRET in c["user"] for c in llm.calls if c["model"] != nr.WEAK_MODEL)

def test_resume_makes_no_new_calls_and_no_duplicate_entries(tmp_path):     # Review Focus 3
    rep1 = run(); n1 = len(llm.calls)
    rep2 = run()                                                             # 같은 Store 로 다시
    assert len(llm.calls) == n1 and rep2["arms"]["seen"]["notes_n"] == rep1["arms"]["seen"]["notes_n"]

def test_interrupted_run_resumes_midway(tmp_path):
    # 40번째 호출에서 예외를 던지는 LLM 으로 한 번, 정상 LLM 으로 다시 → 완주 리포트가 한 번에 돈 것과 같다
    assert rep_resumed["arms"] == rep_clean["arms"]

def test_round_with_no_failures_still_finishes(tmp_path):                  # Review Focus 2
    # 풀이자가 처음부터 전부 맞힌다 → 제안 호출 0, 리포트의 d1 == 0
    assert rep["arms"]["seen"]["notes_n"] == 0 and rep["arms"]["seen"]["decomp"]["d1"] == 0

def test_confirmatory_without_ladder_stops_with_message(tmp_path):         # Review Focus 4
    with pytest.raises(SystemExit, match="사다리 문항이 없습니다"):
        nr.run_experiment("exp1", "weekXX", llm, nr.Store(tmp_path), explore=False, mock=True, public_bank=pub, ladder_bank=[])
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 흐름: 기준선(확정일 때 세 단, 탐색일 때 1단만) → 갈래마다 라운드 1~3 [풀이(1라운드는 기준선 재사용) → 틀린 문항 → `propose_entries` → 노트 저장] → (확정) 3라운드 뒤 노트로 세 단 풀이 → `ladder` 로 분해·부트스트랩·판정. 단계마다 `store.get` 이 있으면 건너뛴다. `resumed` 에는 저장 지점이 하나라도 있는 상태로 시작한 실행의 시각을 덧붙인다.
- [ ] **Step 4: 통과 확인** — `pytest tests/evolve -q`
- [ ] **Step 5: mock 으로 CLI 확인** — `.venv/bin/python evolve/note_round.py --exp exp1 --week week09 --explore --mock --tag smoke` → 라운드별 1단 정답률 4줄이 찍히고 `evolve/reports/` 에 새 파일이 없다
- [ ] **Step 6: Commit** — `evolve: 노트 루프 실험 1 실행기 (저장 지점, 탐색/확정)`

### Task 6: 9주차 사다리 문항 (비공개, 공개 저장소에 커밋 없음)

**Files (모두 `_heldout/` 아래. 끝나면 `~/workspaces/team14-heldout/` 로 동기화):**
- Create: `_heldout/tools/ladder_items.py`, `_heldout/work/ladder/week09/…`, `_heldout/ladder/index.json`, `_heldout/ladder/week09.json`

**Interfaces:**
- Produces: `common.load_bank("ladder", ["week09"])` 가 읽는 파일. 2단 문항 `{"id": "w09t2-NN", "rung": "T2", "pair": "<기출 id>", …}`, 3단 문항 `{"id": 기존 id 또는 "w09t3-NN", "rung": "T3", …}`. 형식은 공개 은행과 같다(`type, q, options, answer, explanation, concept`).

- [ ] **Step 1: 2단 출제 요청서 만들기** — `ladder_items.py plan --week week09`: 기출 18문항마다 `{pair, original(정답 포함), 요구}` 를 `work/ladder/week09/t2_request.json` 에 쓴다. 요구: 같은 사실·같은 정답 내용, 문제 문장을 다시 쓴다, 보기도 표현을 바꾸고 순서를 바꾼다, 숫자 문항은 수치와 정답을 그대로 둔다, 기출에 없던 단서를 더하지 않는다.
- [ ] **Step 2: 2단 출제** — quiz-writer 하위 에이전트 1명(요청서, 8·9주차 브리프). 산출 `t2_candidates.json`.
- [ ] **Step 3: 3단 보충 대상 계산** — `ladder_items.py gaps --week week09`: 기출의 개념 가운데 9주차 비공개 세트에 문항이 없는 개념 목록. 그 개념마다 1문항을 quiz-writer 에게 요청한다(11/24 의 수정 라운드 규칙: 같은 대상의 근접 오답, 보기 길이 맞춤, 강의 고유 내용).
- [ ] **Step 4: 기계 검사** — `ladder_items.py check`: 형식, 정답 위치 분포, 2단은 기출과 완전히 같은 문장이 아니고 정답 내용이 같은지(객관식은 정답 보기의 핵심 명사·수치가 겹치는지 사람이 보는 표로 출력), 3단 보충분은 공개 세트·기존 비공개 세트와 3-gram 자카드 0.5 미만.
- [ ] **Step 5: 풀이 시험** — quiz-solver-strong 2회(브리프 제공). 2회 모두 정답인 문항만 남긴다.
- [ ] **Step 6: 검증** — quiz-verifier 1명. 2단은 기출과 나란히 놓고 "사실·정답이 같은가, 표현이 실제로 다른가, 새 단서가 생기지 않았는가"를 본다. `pass`/`drop` 만.
- [ ] **Step 7: 수정** — drop 된 2단 문항은 사유를 붙여 quiz-writer 에게 다시(최대 2번). 그래도 통과 못 한 짝은 뺀다.
- [ ] **Step 8: 조립과 점검** — `ladder_items.py assemble`: `ladder/week09.json` (2단 통과분 + 3단 = 기존 비공개 20문항 전부 + 보충 통과분). 출력에서 확인: 2단 짝 수, 3단 수, 3단이 기출의 모든 개념을 덮는가, 파일 sha256.
- [ ] **Step 9: 읽히는지 확인** — `.venv/bin/python /Users/ethan.son/.claude/jobs/ce76e5d4/tmp/count_ladder.py` (은행을 읽어 단별 문항 수만 출력) → `T2 n=…, T3 n=…`
- [ ] **Step 10: 동기화** — `rsync -a --delete --exclude .git _heldout/ ~/workspaces/team14-heldout/`. `git status --short` 에 `_heldout` 이 나오지 않는지 확인.

이 Task 의 풀이 시험은 **강한 풀이자(브리프 제공)** 만 쓴다. 노트를 본 풀이자로 사다리를 푸는 것은 Task 8 의 확정 실행이 처음이다.

### Task 7: 실험실 "전이 사다리" 칸과 사전 등록, 문서

**Files:**
- Modify: `lab/index.html`, `evolve/README.md`, `PLAN.md`

**Interfaces:**
- Consumes: `evolve/reports/index.json` 의 `ladders`, 리포트 필드(Task 5)

- [ ] **Step 1: 사전 등록 문구 추가** — `lab/index.html` 의 사전 등록 칸에 설계 3.7 의 가설 표(H1~H4, 확인 조건), "어느 실행이 무엇을 판정하는가" 표, 동결 목록을 그대로 옮긴다. 게시 날짜를 적는다.
- [ ] **Step 2: `renderLadder(r)` 추가** — 기준선 정답률 한 줄, 갈래 × 단 향상 막대(기존 `bars` 재사용), 갈래별 분해 막대(`O_암기`, `O_측면`, `G`; 구간이 0 을 포함하는 성분은 흐리게), 판정 줄(리포트의 `judge` 문자열 그대로), 반례 지표(있을 때), 동결 정보(커밋, 사다리 해시 앞 8자), `mock` 이면 기존과 같은 mock 알림. `idx.ladders` 가 없거나 비면 "아직 확정 실행 전" 한 줄.
- [ ] **Step 3: 가짜 리포트로 화면 확인** — `.venv/bin/python evolve/note_round.py --exp exp1 --week week09 --mock --tag smoke` 는 사다리가 필요하므로 Task 6 뒤에 돌린다. 로컬 서버(`python -m http.server 8765 --bind 127.0.0.1`)로 `lab/index.html` 을 열어 칸이 그려지고 콘솔 오류가 없고 폭 390px 에서 가로로 넘치지 않는지 본다. 확인 뒤 mock 리포트·노트 파일을 지우고 `git checkout -- evolve/reports/index.json`.
- [ ] **Step 4: 문서** — `evolve/README.md` 에 노트 루프 실행법(탐색/확정, 이어 돌리기, 환경 변수)과 파일 표 추가. `PLAN.md` 3.3 아래에 "O 의 세분: `O = O_암기 + O_측면` (설계 문서 링크)" 한 줄.
- [ ] **Step 5: Commit** — `lab: 전이 사다리 칸과 사전 등록 게시`
- [ ] **Step 6: PR 올리고 머지** — 사전 등록이 확정 실행보다 먼저 공개되도록 Task 8 전에 main 에 넣는다. 머지 뒤 Pages 빌드 확인.

### Task 8: 실험 1 — 탐색, 동결, 확정 실행

- [ ] **Step 1: 독립 검토** — 새 하위 에이전트에게 이 브랜치의 `evolve/` 변경과 설계 3.3~3.7 을 주고 "설계와 다른 동작, 유출 경로, 통계 오류"만 찾게 한다. 사다리 문항은 보여 주지 않는다. 확인된 문제를 고치고 테스트를 다시 돌린다.
- [ ] **Step 2: 탐색 실행** — `env EVOLVE_CLI_ISOLATION=--safe-mode EVOLVE_MAX_USD=25 .venv/bin/python evolve/note_round.py --exp exp1 --week week09 --explore --tag explore1`. 볼 것: 1단 정답률이 라운드마다 오르는가, 버려진 항목의 사유, 노트 항목이 규칙처럼 읽히는가. 프롬프트를 고쳤으면 `--tag explore2` 로 다시. **사다리는 풀지 않는다.**
- [ ] **Step 3: 동결** — 프롬프트·코드를 커밋하고 main 에 머지(PR). 커밋 해시와 사다리 파일 sha256 을 적어 둔다.
- [ ] **Step 4: 확정 실행** — `env EVOLVE_CLI_ISOLATION=--safe-mode EVOLVE_MAX_USD=25 .venv/bin/python evolve/note_round.py --exp exp1 --week week09` (백그라운드). 끊기면 같은 명령을 다시 실행한다.
- [ ] **Step 5: 결과 점검** — 리포트의 `freeze.commit` 이 동결 커밋과 같은지, `freeze.dirty` 가 false 인지, `n`, `dropped_pairs`, 분해 식의 합, `judge` 를 확인한다. 수치는 고치지 않는다.
- [ ] **Step 6: 게시** — 리포트·노트·색인을 커밋 → PR → 머지 → Pages 에서 칸이 보이는지 확인.
- [ ] **Step 7: 보고** — H1·H2·H4 판정과 구간, 한계를 사용자에게 알린다. H1 이 확인되지 않으면 Task 9 로 넘어가기 전에 사용자에게 알리고 멈춘다(설계: H3 는 판정하지 않는다).

### Task 9: 반례 처치와 고쳐 쓰기 (`evolve/counter.py`)

**Files:**
- Create: `evolve/counter.py`, `tests/evolve/test_counter.py`
- Modify: `evolve/common.py` (mock 응답 `ce_generate`, `revise`)

**Interfaces:**
- Consumes: `notes.*`, `solve.run/fmt_question/parse_answer/is_correct`, `common.brief_bundle`
- Produces:
  - `generate(entry: dict, brief: str, llm) -> dict | None` — 반례 1문항 `{"entry_id", "q", "options"(4), "answer", "trap", "evidence": {"quote"}}`. 해석 실패는 `None`.
  - `mechanical_check(ce: dict, brief: str, public_bank: list[dict]) -> list[str]` — 사유 코드: `"format"`(보기 4개 아님, 인덱스 범위 밖), `"trap_is_answer"`, `"quote_not_in_brief"`(공백을 정규화한 인용이 브리프에 없음), `"dup_public"`(기출 문제 문장과 3-gram 자카드 0.5 이상).
  - `overlap_drop(ces: list[dict], ladder_bank: list[dict]) -> tuple[list[dict], dict]` — 사다리 문항과 3-gram 자카드 0.5 이상인 반례를 뺀 목록과 `{"dropped": int, "max": float}`. 문항 글은 로그·반환값에 넣지 않는다. `ladder_bank` 가 비면 `{"dropped": 0, "max": None, "checked": False}`.
  - `validate(ces, brief, llm, k=2) -> list[dict]` — `claude-sonnet-5-5` 가 브리프를 보고 2회 모두 맞힌 반례만.
  - `probe(ces, notes_txt, llm, k=3) -> list[dict]` — 반례마다 `{"entry_id", "acc", "trap_rate"}`.
  - `revise(entry: dict, ce: dict | None, brief: str, llm) -> dict` — `{"action": "rewrite"|"delete"|"keep", "rule": str | None}`. `ce` 가 `None` 이면 반례 없는 고쳐 쓰기 프롬프트("브리프에 비추어 더 정확하고 일반적으로").
  - `treat_ce(notes, new_ids: list[str], brief, llm, public_bank, ladder_bank, passes=2) -> dict` — 설계 3.5 의 1~5. 반환 `{"generated", "passed", "overlap": {...}, "trap_rate": [회차별], "retest_acc": [회차별], "revised": [id...], "deleted": [id...], "rejected_rewrites": int}`. 제약을 어긴 고쳐 쓰기는 버리고 원래 항목을 둔다.
  - `treat_rev(notes, new_ids: list[str], budget: int, brief, llm) -> dict` — 새 항목부터 `budget` 개를 반례 없이 고친다. 반환 `{"revised", "deleted", "rejected_rewrites"}`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_mechanical_check_codes():
    ce = {"q": "가" * 30, "options": ["a", "b", "c", "d"], "answer": 1, "trap": 1, "evidence": {"quote": "브리프에 없는 말"}}
    assert set(counter.mechanical_check(ce, "브리프 본문", [])) == {"trap_is_answer", "quote_not_in_brief"}

def test_overlap_drop_reports_numbers_only():
    kept, info = counter.overlap_drop([{"q": SECRET + "와 같은 긴 문장 하나를 그대로 베낀 반례"}], [{"q": SECRET + "와 같은 긴 문장 하나를 그대로 베낀 반례", "options": []}])
    assert kept == [] and info["dropped"] == 1 and SECRET not in json.dumps(info, ensure_ascii=False)

def test_generator_and_validator_inputs_have_no_ladder_or_public_items(scripted_llm):
    # treat_ce 를 돌린 뒤: 큰 모델 호출의 user 글에 사다리 표식도, 기출 문항 표식도 없다 (노트를 통한 간접 노출만 허용)
    assert not any(SECRET in c["user"] or PUB_MARK in c["user"] for c in llm.calls if c["model"] != WEAK_MODEL)

def test_treat_ce_revises_only_entries_whose_ce_failed(scripted_llm):
    # 항목 n01 의 반례는 풀이자가 틀리고 n02 의 반례는 맞힌다 → revised == ["n01"]
    assert out["revised"] == ["n01"] and n["entries"][1]["history"] == []

def test_treat_ce_second_pass_generates_fresh_ce_for_revised_only(scripted_llm):
    assert n_generate_calls == 2 + 1          # 1회차 항목 2개, 2회차는 고친 n01 만

def test_bad_rewrite_is_rejected_and_original_kept(scripted_llm):          # Review Focus 1
    # 고쳐 쓴 규칙이 "3번을 고른다." → 원래 규칙 유지, rejected_rewrites == 1
    assert n["entries"][0]["rule"] == original and out["rejected_rewrites"] == 1

def test_all_ces_filtered_means_no_revision(scripted_llm):
    # 모든 반례가 mechanical_check 에서 떨어진다 → passed == 0, revised == []
    assert out["passed"] == 0 and out["revised"] == []

def test_treat_rev_respects_budget_and_gets_no_counterexample(scripted_llm):
    out = counter.treat_rev(n, ["n01", "n02", "n03"], budget=2, brief="브리프", llm=llm)
    assert len(out["revised"]) + len(out["deleted"]) <= 2 and not any("반례" in c["user"] for c in llm.calls)
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 프롬프트는 재량. 반례 출제 프롬프트에 반드시: 규칙을 글자 그대로 따르면 고르게 되는 함정 보기 하나, 브리프 인용 한 문장, 출력 JSON. 3-gram 자카드는 공백을 뺀 글자 3-gram(비공개 세트 점검 도구와 같은 정의).
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: Commit** — `evolve: 반례 처치와 고쳐 쓰기 대조`

### Task 10: 실험 2 갈래 (`note_round.py` 확장)

**Files:**
- Modify: `evolve/note_round.py`, `tests/evolve/test_note_round.py`, `lab/index.html`(반례 지표 줄), `evolve/README.md`

**Interfaces:**
- Consumes: `counter.treat_ce`, `counter.treat_rev`
- Produces: `run_experiment("exp2", …)`. 갈래 실행 순서 `seen` → `seen+ce` → `seen+rev`. 리포트의 갈래 칸에 `"treat": [라운드별 treat_* 반환값]`, 리포트에 `"train_calls": {갈래: {"solver", "opus", "sonnet"}}`.
  - 1라운드: `seen+ce`, `seen+rev` 는 `store.get("seen/r1/proposed")` 의 항목을 그대로 받는다(제안자를 부르지 않는다). `--arms` 로 `seen` 없이 실행해 그 저장 지점이 없으면 `SystemExit("seen 갈래를 먼저 실행하세요")`.
  - `seen+rev` 의 r 라운드 예산 = `seen+ce` 가 그 라운드에 `revised + deleted` 한 수. `seen+ce` 의 저장 지점이 없으면 같은 식으로 중단.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_exp2_round1_entries_are_shared(tmp_path):
    rep = run_exp2()
    r1 = lambda arm: [e["rule"] for e in store.get(f"{arm}/r1/proposed")["added"]]
    assert r1("seen") == r1("seen+ce") == r1("seen+rev")
    assert n_proposer_calls_in_round1 == 1

def test_rev_budget_matches_ce_edits(tmp_path):
    rep = run_exp2()
    for r in (1, 2, 3):
        ce, rev = rep["arms"]["seen+ce"]["treat"][r - 1], rep["arms"]["seen+rev"]["treat"][r - 1]
        assert len(rev["revised"]) + len(rev["deleted"]) <= len(ce["revised"]) + len(ce["deleted"])

def test_exp2_judges_only_h3(tmp_path):
    rep = run_exp2()
    assert set(rep["judge"]) == {"H3", "H1_재현"}

def test_exp2_evaluation_calls_equal_across_arms(tmp_path):
    # 최종 평가의 풀이자 호출 수가 세 갈래에서 같다 (T = 0 의 근거)
    assert len({final_eval_calls(a) for a in ("seen", "seen+ce", "seen+rev")}) == 1

def test_running_rev_without_ce_checkpoint_stops(tmp_path):
    with pytest.raises(SystemExit, match="seen\\+ce"):
        nr.run_experiment("exp2", "weekXX", llm, nr.Store(tmp_path), explore=True, mock=True, arms=["seen", "seen+rev"], public_bank=pub)
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `pytest tests/evolve tests/live -q`
- [ ] **Step 5: mock CLI 확인** — `--exp exp2 --week week09 --explore --mock --tag smoke2`
- [ ] **Step 6: Commit** — `evolve: 실험 2 갈래 (반례 처치, 고쳐 쓰기 대조)`

### Task 11: 실험 2 — 탐색, 동결, 확정 실행

- [ ] **Step 1: 독립 검토** — Task 8 Step 1 과 같은 방식으로 `counter.py` 와 실험 2 갈래를 본다.
- [ ] **Step 2: 탐색 실행** — `--exp exp2 --week week09 --explore --tag explore1`. 볼 것: 반례 통과율(절반 미만이면 출제 프롬프트를 고친다), 고쳐 쓴 항목이 제약을 지키는가, `seen+rev` 예산이 맞는가. 사다리는 풀지 않는다.
- [ ] **Step 3: 동결** — 커밋·머지, 해시 기록.
- [ ] **Step 4: 확정 실행** — `--exp exp2 --week week09` (백그라운드, 끊기면 재실행).
- [ ] **Step 5: 결과 점검** — Task 8 Step 5 와 같음 + `train_calls`, 반례 지표, `overlap` 값.
- [ ] **Step 6: 게시** — 커밋 → PR → 머지 → Pages 확인.
- [ ] **Step 7: 마무리** — 메모리 파일 갱신, 이슈 #15 에 사다리 문항 수 댓글, 사용자에게 H3 판정·구간·한계 보고. 발표일이 12/7 이면 설계 4절 넷째 단계(반복 실행, 10주차, Haiku 4.5)를 별도 계획으로 제안한다.

---

## Self-Review 결과

- **설계 대응:** 3.3 노트 루프 → Task 2·3·5 / 3.4 네 갈래와 접근 표 → Task 3·9·10 (테스트로 고정) / 3.5 반례 → Task 9 / 3.6 사다리·분해·통계 → Task 4·6 / 3.7 사전 등록·동결·탐색과 확정 → Task 5·7·8·11 / 3.8 파일 → File Structure / 3.9 비용 → Global Constraints 의 환경 변수와 이어 돌리기(Task 5). 설계 4절 넷째 단계는 이 계획에 없다(Task 11 Step 7 에서 별도 계획으로).
- **빠져 있던 것을 채운 곳:** `claude-haiku-4-5` 단가(넷째 단계에서만 필요하므로 이 계획 밖), 라운드마다 세 단을 푸는 선택 옵션(만들지 않는다. 필요해지면 추가).
- **이름 일치:** 통계 이름 `d1,d2,d3,O_mem,O_facet,G,O,O_facet-O_mem` 과 정규화판 `n*` 을 Task 4·5·7 에서 같은 철자로 쓴다. 갈래 이름은 `seen, concept, seen+ce, seen+rev`. 단 이름은 `T1, T2, T3`(설계의 1·2·3단).
- **Review Focus:** 1 → Task 3·9 / 2·3·4 → Task 5 / 5 → Task 4 에 각각 테스트가 있다.
