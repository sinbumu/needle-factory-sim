# Needle Factory Sim — Coding Agent 실행 지시서 v1.0

## 0. 당신의 역할

현재 열려 있는 Git 저장소 `needle-factory-sim`에서 **3~4시간 이내에 기획 → 구현 → 검증 → GitHub v0.1.0 Release까지 완료하는 것**이 목표다.

이 프로젝트는 완성도 높은 게임을 만드는 것이 목적이 아니다.

핵심은 다음 Edge AI 아키텍처를 실제 동작하는 데스크톱 PoC로 시연하는 것이다.

> 명시적 단일 제어 명령은 14MB Needle 2 Local SLM이 Tool Call로 변환하고, 공장 전체 상태를 고려해야 하는 목표 지향 요청은 Cloud LLM이 실행 계획을 생성한다. 어느 AI가 명령을 만들더라도 실제 상태 변경은 deterministic FactoryController가 최종 검증한다.

우선순위는 다음과 같다.

```text
AI 기술 데모 70
게임 / 시각적 시뮬레이션 30
```

과도한 설계, 추가 기능, 범용 프레임워크화는 하지 않는다.

---

# 1. 작업 시작 시 반드시 할 일

먼저 현재 저장소를 확인한다.

```bash
pwd
git status
git branch --show-current
git remote -v
```

다음을 확인한다.

- 현재 위치가 의도한 `needle-factory-sim` 저장소인가
- 기존 파일이 있는가
- 사용자가 만든 기존 변경사항이 있는가
- 현재 Python 및 `uv` 사용 가능 여부
- Windows 환경 여부

잘못된 저장소임이 명백한 경우에는 수정하지 않는다.

기존 파일이 있다면 임의로 제거하지 말고 가능한 한 유지·통합한다.

사용자에게 중간 설계 승인을 요청하면서 멈추지 말고, 본 지시서 범위 안에서는 자율적으로 진행한다.

단, 다음은 임의로 하지 않는다.

- 다른 저장소 수정
- 사용자 자격증명 저장
- 기존 관련 없는 파일 삭제
- 프로젝트 범위를 임의로 확대
- Needle 대신 다른 Local LLM로 교체
- Demo 결과를 하드코딩하거나 가짜 AI 응답으로 연출

---

# 2. Source of Truth 우선순위

설계 충돌이 발생하면 다음 순서를 따른다.

1. **본 실행 지시서의 제품 요구사항 및 아키텍처**
2. 현재 설치된 Needle 2 API와 upstream `cactus-compute/needle`의 `llms.txt`
3. upstream `doc/apis.md`
4. 현재 저장소의 기존 코드
5. 일반적인 구현 판단

Needle 저장소의 오래된 README나 예전 API 예제가 최신 `llms.txt`와 충돌하면 **`llms.txt` / `doc/apis.md`를 우선한다.**

Needle API를 추측하지 않는다.

현재 공식 API에서 확인된 핵심 계약은 다음과 같다.

```text
needle.Needle(...)
agent.complete(...)
agent.reset()
```

`agent.run()`은 Python Tool을 실제 실행하는 agentic loop이므로 이 프로젝트에서는 사용하지 않는다.

---

# 3. 기술 스택

## Target

```text
Primary OS      Windows 11 x64
Python          3.11
UI              PySide6
Local AI        cactus-needle / Needle 2 Base Model
Cloud AI        OpenAI API
Validation      Pydantic v2
Package         pyproject.toml + uv
Tests           pytest
```

Python package requirement는 최소한 Python 3.11에서 정상 동작하도록 한다.

프로젝트 의존성은 대략 다음을 사용한다.

```text
cactus-needle
PySide6
pydantic
openai
pytest (dev)
```

실제로 설치된 버전은 `uv.lock`으로 재현 가능하게 만든다.

Fine-tuning은 하지 않는다.

Needle Base Model만 사용한다.

---

# 4. 권장 저장소 구조

과도하게 쪼개지 말되 최소한 책임은 분리한다.

```text
needle-factory-sim/
├─ pyproject.toml
├─ uv.lock
├─ README.md
├─ run.bat
├─ .gitignore
│
├─ src/
│  └─ needle_factory_sim/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ app.py
│     ├─ constants.py
│     │
│     ├─ models.py
│     ├─ controller.py
│     ├─ simulation.py
│     ├─ plan_executor.py
│     │
│     ├─ ai/
│     │  ├─ __init__.py
│     │  ├─ needle_adapter.py
│     │  ├─ router.py
│     │  └─ cloud_planner.py
│     │
│     └─ ui/
│        ├─ __init__.py
│        ├─ main_window.py
│        ├─ factory_view.py
│        ├─ ai_monitor.py
│        └─ cloud_settings.py
│
├─ scripts/
│  └─ needle_spike.py
│
└─ tests/
   ├─ test_controller.py
   ├─ test_routing.py
   ├─ test_plan_validation.py
   └─ test_reset.py
```

필요하면 파일 수는 약간 조정해도 된다.

단 다음 책임 경계는 유지한다.

```text
AI Output
  ↓
Validation
  ↓
FactoryController
  ↓
Factory State
```

AI Adapter가 Factory State를 직접 수정하면 안 된다.

---

# 5. 전체 아키텍처

구현 구조는 다음과 같다.

```text
User
 ↓
Desktop UI
 ↓
CommandRouter
 ↓
Needle 2 Local Adapter
 ↓
┌─────────────────────────────────────┐
│ confidence + function_calls 평가    │
└─────────────────────────────────────┘
      ↓                         ↓
    LOCAL                     CLOUD
      ↓                         ↓
Action Candidate       CloudPlannerContext
      ↓                         ↓
FactoryController        OpenAI Planner
      ↓                         ↓
Factory State         ExecutionPlan JSON
                                ↓
                         PlanValidator
                                ↓
                         PlanExecutor
                                ↓
                        FactoryController
                                ↓
                         Factory State
```

Local과 Cloud 모두 최종적으로 동일한 `FactoryController`를 사용한다.

Cloud LLM이 직접 Tool을 실행하지 않는다.

---

# 6. Factory Map

맵은 고정한다.

```text
┌─────────┬─────────┬─────────┐
│ S       │ A       │ B       │
│ Start   │ Cold    │ Hot     │
│ 30°C    │ 10°C    │ 55°C    │
├─────────┼─────────┼─────────┤
│ X       │ C       │ E       │
│ Wall    │ Hazard  │ Goal    │
│         │ 50°C    │ 30°C    │
└─────────┴─────────┴─────────┘
```

Adjacency:

```text
S <-> A
A <-> B
A <-> C
B <-> E
C <-> E
```

`X`는 Wall이며 Tool의 target enum에도 포함하지 않는다.

---

# 7. 초기 Factory State

## Sector

### S

```text
kind = START
current_temperature = 30
target_temperature = 30
```

### A

```text
kind = NORMAL
current_temperature = 10
target_temperature = 10
```

### B

```text
kind = DOOR
current_temperature = 55
target_temperature = 55
door_open = false
```

### C

```text
kind = CONTAMINATED
current_temperature = 50
target_temperature = 50
used = false
needs_reset = false
```

### E

```text
kind = GOAL
current_temperature = 30
target_temperature = 30
```

## Robot

```text
current_sector = S
```

## Cargo

```text
HP = 100
Safe Temperature = 20°C ~ 40°C
Damage outside safe range = 10 HP / second
```

---

# 8. Simulation 규칙

## Temperature

```text
Cold    current < 20
Safe    20 <= current <= 40
Hot     current > 40
```

`set_temperature()`는 현재 온도를 직접 변경하지 않는다.

```text
current_temperature
    ↓ gradually
target_temperature
```

전이 속도:

```text
10°C / second
```

여러 Sector의 온도 전이는 동시에 진행된다.

---

# 9. SimulationClock 구현

`asyncio` 기반 clock을 추가하지 않는다.

PySide6 `QTimer`를 사용한다.

```text
tick interval = 100 ms
```

단 온도 변경량을 단순히 tick당 1°C로 고정하지 않는다.

`time.monotonic()` 등을 이용하여 실제 elapsed time을 계산한다.

개념:

```text
delta_temperature =
    TEMPERATURE_RATE_C_PER_SECOND
    × elapsed_seconds
```

Cargo damage도 동일한 elapsed time을 사용한다.

```text
damage =
    10 HP
    × elapsed_seconds
```

HP는 0 아래로 내려가지 않는다.

UI에는 적당히 반올림해서 표시한다.

---

# 10. 이동 규칙

Robot은 한 Action에 한 Sector만 이동한다.

`move_robot(target)` 실행 전 Controller가 다음을 검증한다.

```text
1. Simulation이 Emergency Stop이 아닌가
2. Cargo HP > 0인가
3. target이 실제 Sector인가
4. 현재 위치와 target이 adjacency 관계인가
5. target의 현재 온도가 Safe인가
6. target == B이면 B Door가 열려 있는가
```

하나라도 실패하면 상태를 바꾸지 않는다.

AI가 잘못된 Tool Call을 생성해도 게임오버시키지 않는다.

```text
REJECTED
state_changed = false
```

---

# 11. Door 규칙

Door는 B에만 존재한다.

```text
B.door_open
```

B에 **진입할 때만** Door Open이 요구된다.

Door Open/Close는 즉시 적용되며 별도 물리 시간이 없다.

---

# 12. Contaminated Sector C 규칙

C에 Robot이 진입하면:

```text
C.used = true
```

Robot이 C에서 다른 Sector로 이동하면:

```text
C.needs_reset = true
```

`reset_sector(C)` 성공 시 정확히 다음만 수행한다.

```text
C.used = false
C.needs_reset = false
```

다음은 변경하지 않는다.

```text
current_temperature
target_temperature
기타 Factory 상태
```

Reset 조건:

```text
C.needs_reset == true
AND
Robot.current_sector != C
```

C를 사용한 뒤 E에 도착했는데 `needs_reset == true`이면:

```text
GOAL_REACHED / CLEANUP_REQUIRED
```

완전한 Mission Success가 아니다.

이 상태에서는 `reset_sector(C)`를 허용한다.

Reset 완료 후:

```text
MISSION_SUCCESS
```

---

# 13. Mission 상태

필요한 상태 Enum을 구현한다.

예:

```text
RUNNING
MISSION_SUCCESS
GOAL_REACHED_CLEANUP_REQUIRED
GAME_OVER
EMERGENCY_STOPPED
```

Cargo HP가 0이면:

```text
GAME_OVER
```

GAME_OVER 이후 일반 Action은 거부한다.

Reset Simulation은 항상 가능해야 한다.

---

# 14. Local Needle Tool

Needle에는 정확히 **5개 Tool**만 제공한다.

```text
move_robot
set_temperature
toggle_door
reset_sector
emergency_stop
```

Needle Tool은 **FactoryController와 연결하지 않는다.**

Tool 함수는 schema 생성용 pure function이어야 한다.

어떤 경우에도 Needle Tool 자체에서 State Mutation을 하지 않는다.

---

# 15. Needle Tool Signature

가능하면 `Literal` 및 Needle Field constraint를 사용해 grammar 범위를 제한한다.

## move_robot

개념:

```python
move_robot(
    target_sector: Literal["S", "A", "B", "C", "E"]
)
```

설명 의미:

```text
Move the transport robot to exactly one explicitly named adjacent sector.
This tool does not plan a route.
The user must explicitly identify the target sector.
```

---

## set_temperature

```python
set_temperature(
    sector_id: Literal["S", "A", "B", "C", "E"],
    target_c: int  # 0 ~ 60
)
```

설명:

```text
Set the target temperature of one explicitly named factory sector.
The user must explicitly provide both the sector and target temperature.
This starts a gradual temperature transition and does not wait.
```

---

## toggle_door

```python
toggle_door(
    sector_id: Literal["B"],
    open: bool
)
```

설명:

```text
Open or close the entry door for sector B.
The user must explicitly request the door state.
```

---

## reset_sector

```python
reset_sector(
    sector_id: Literal["C"]
)
```

설명:

```text
Reset the contamination state of sector C after the robot has left it.
Use only when the user explicitly requests a sector reset.
```

---

## emergency_stop

```python
emergency_stop()
```

설명:

```text
Immediately stop the factory simulation when the user explicitly requests an emergency stop.
```

---

# 16. Needle 사용 규칙 — 매우 중요

현재 공식 Needle 2 API를 사용한다.

```python
agent = needle.Needle(...)
```

명령 처리는 반드시:

```python
agent.complete(...)
```

로 한다.

## 금지

```python
agent.run(...)
```

을 사용하지 않는다.

이유:

`run()`은 Needle이 Python Tool을 직접 실행하는 agentic loop이다.

본 프로젝트에서는:

```text
Needle → Candidate
Controller → Execution
```

경계를 반드시 유지해야 한다.

---

# 17. Needle Session 규칙

Needle instance 자체는 앱 실행 동안 재사용한다.

매 사용자 Command 시작 전에:

```python
agent.reset()
```

을 실행한다.

그 후 사용자 입력으로 **한 번의 `complete()`만 호출**한다.

이번 프로젝트에서는 Local Needle을 multi-turn Agent로 사용하지 않는다.

Controller 결과를 다시 `complete()`에 전달해서 Agent loop를 계속하지 않는다.

즉:

```text
agent.reset()

response = agent.complete(user_text)

끝
```

이다.

이렇게 해야 Demo A의 문맥이 Demo B/C에 영향을 주지 않는다.

---

# 18. Needle system facts

Factory State를 Needle의 system prompt에 넣지 않는다.

Needle은 전체 Factory를 알면 안 된다.

필요하다면 고정 environment fact 정도만 사용한다.

예:

```text
locale: ko-KR
device: Windows desktop
```

Needle system 영역을 일반 LLM system prompt처럼 지시문을 넣는 용도로 사용하지 않는다.

---

# 19. Needle 초기화 상태

앱 실행과 동시에 Needle engine을 UI thread 밖에서 초기화한다.

상태:

```text
INITIALIZING
READY
ERROR
```

UI Monitor에 표시한다.

예:

```text
Needle Engine
INITIALIZING...
```

준비 완료:

```text
Needle Engine
READY
Local inference available
```

최초 `Needle(...)` 실행 시 engine provisioning/download가 필요할 수 있다.

README에 다음 사실을 명확히 설명한다.

```text
최초 provisioning 시 인터넷 연결 필요
이후 local inference 자체는 network를 사용하지 않음
```

Engine binary를 임의로 Git 저장소에 commit하지 않는다.

---

# 20. Needle Response에서 사용해야 할 항목

최소 다음을 읽는다.

```text
type
success
error
error_code
function_calls
reasoning
confidence
prefill_tps
decode_tps
peak_ram_mb
```

추가 필드는 optional하게 처리한다.

키 누락 때문에 앱 전체가 crash하지 않게 한다.

---

# 21. Routing Mode

UI에는 다음 Mode를 지원한다.

```text
AUTO
FORCE LOCAL
FORCE CLOUD
```

기본:

```text
AUTO
```

---

# 22. AUTO Routing

AUTO에서는 항상 Needle을 먼저 호출한다.

다음 조건을 **모두 만족하면 LOCAL 후보**다.

```text
Needle inference 성공
confidence가 숫자로 존재
confidence >= threshold
function_calls가 정확히 1개
Action이 Local whitelist에 존재
Arguments가 Local schema와 일치
```

기본 threshold:

```text
0.75
```

LOCAL 후보라고 하더라도 반드시 FactoryController 검증을 통과해야 한다.

---

# 23. CLOUD Routing

다음 중 하나라도 해당하면 Cloud escalation 대상이다.

```text
confidence < threshold
confidence is None
function_calls == []
function_calls가 2개 이상
Needle inference error
Needle response contract 위반
```

Cloud가 설정되어 있지 않으면:

```text
CLOUD FALLBACK REQUIRED
Cloud provider is not configured.
```

Factory State는 변경하지 않는다.

사용자 Input Text는 유지한다.

---

# 24. FORCE LOCAL

FORCE LOCAL에서도 Needle을 호출한다.

Cloud escalation만 금지한다.

Needle 결과가:

```text
empty
multiple calls
invalid
```

이라면 이를 임의로 실행하지 않는다.

오류를 Monitor에 표시한다.

FactoryController 검증 역시 절대로 bypass하지 않는다.

---

# 25. FORCE CLOUD

FORCE CLOUD에서는 Needle 호출 없이 바로 Cloud Planner를 사용해도 된다.

Monitor에 반드시:

```text
ROUTE = CLOUD
OVERRIDE = TRUE
```

를 표시한다.

AUTO 결과처럼 보이게 하지 않는다.

---

# 26. Cloud Settings UX

환경변수를 사용하지 않는다.

`.env`를 사용하지 않는다.

API Key를 파일로 저장하지 않는다.

Cloud Settings Dialog를 만든다.

Field:

```text
Provider
API Key
Model ID
Confidence Threshold
```

Provider:

```text
OpenAI
```

고정 표시.

API Key:

```text
Password Masked Input
```

Model ID:

```text
User Input
```

Threshold:

```text
default = 0.75
```

버튼:

```text
Apply for this session
Clear Key
Cancel
```

---

# 27. API Key 저장 정책

API Key는 프로세스 메모리에만 존재한다.

앱 종료 시 사라져야 한다.

다음에 저장하면 안 된다.

```text
.env
config file
registry
README
console log
AI Monitor
crash log
Git
```

OpenAI Client 생성 시:

```text
session에서 받은 API key를 코드에서 직접 전달
```

한다.

SDK가 자동으로 environment variable을 읽는 방식에 의존하지 않는다.

Monitor에는:

```text
Cloud: Configured
```

또는

```text
Cloud: Not configured
```

만 보여준다.

Key 일부도 출력하지 않는다.

---

# 28. Cloud Provider

MVP에서는 OpenAI 하나만 구현한다.

다중 Provider Adapter 시스템을 만들지 않는다.

사용자가 Model ID를 입력하므로 특정 모델명을 코드에 하드코딩하지 않는다.

Cloud Planner는 **OpenAI Tool Calling Agent로 구현하지 않는다.**

Cloud LLM은 Tool을 실행하지 않고 **ExecutionPlan 구조화 데이터만 생성**한다.

가능하면 현재 OpenAI SDK의 structured output 기능을 사용한다.

SDK/API 버전상 해당 기능 적용이 어려우면:

```text
JSON response
↓
Pydantic strict validation
```

으로 처리한다.

API 문법은 현재 설치된 OpenAI SDK와 공식 문서를 확인해서 구현하되, 제품 구조는 변경하지 않는다.

---

# 29. Cloud Planner의 허용 Action

Cloud에는 다음 5개 Action + orchestration primitive를 제공한다.

```text
move_robot
set_temperature
toggle_door
reset_sector
wait
```

주의:

```text
emergency_stop
```

은 Cloud Planner에 제공하지 않는다.

E-Stop은 사용자에게서 명시적으로 들어온 Local safety command 또는 UI 버튼의 역할이다.

---

# 30. Cloud 전용 wait

```text
wait(seconds)
```

Constraint:

```text
seconds integer
1 <= seconds <= 10
```

Plan 전체:

```text
max steps = 8
max single wait = 10 sec
max total wait = 15 sec
```

`wait`는 AI가 sleep하는 개념이 아니다.

Cloud가 Plan에:

```json
{
  "action": "wait",
  "arguments": {
    "seconds": 3
  }
}
```

를 넣으면 `PlanExecutor`가 Timer를 관리한다.

UI thread를 block하지 않는다.

wait 중에도:

```text
SimulationClock
Temperature Transition
Cargo Damage
```

는 계속 진행된다.

---

# 31. CloudPlannerContext

Cloud 요청 직전에 현재 Factory State Snapshot을 생성한다.

최소 구조:

```text
request_id
user_request

goal
robot
cargo
simulation
map
sectors
rules
available_actions
```

---

# 32. Cloud Rules Context

Cloud에는 Factory 규칙을 명시적으로 제공한다.

최소 다음 의미를 포함한다.

```json
{
  "movement": {
    "adjacent_only": true,
    "target_temperature_must_be_safe": true,
    "sector_b_requires_open_door": true
  },
  "temperature": {
    "safe_min_c": 20,
    "safe_max_c": 40,
    "transition_rate_c_per_second": 10
  },
  "contamination": {
    "sector": "C",
    "enter_sets_used": true,
    "leave_sets_needs_reset": true,
    "reset_required_for_full_success": true,
    "reset_only_when_robot_outside_sector": true
  },
  "mission": {
    "goal_sector": "E",
    "cargo_hp_must_be_above_zero": true,
    "no_pending_reset_for_full_success": true
  }
}
```

또한 다음을 전달한다.

```text
actions execute sequentially
temperature transitions run concurrently
max plan steps = 8
max single wait = 10
max total wait = 15
```

Cloud는 현재온도뿐 아니라 `target_temperature`도 받아야 한다.

---

# 33. Cloud System Contract

Cloud LLM에 다음 의미의 System Prompt를 사용한다.

가능하면 아래 문구를 그대로 기반으로 구현한다.

```text
You are a deterministic planning component for a factory simulation.

You do not execute tools.
Return exactly one ExecutionPlan that conforms to the provided schema.

Use only the actions explicitly listed in the context.
Do not invent sectors, paths, doors, temperatures, rules, or hidden state.

All plan actions execute sequentially in their listed order.

set_temperature changes a sector's target temperature immediately,
but its current temperature changes gradually over time.

Temperature transitions in different sectors run concurrently.

Use wait when physical time must pass before a later action becomes safe.

Never move the robot into a sector whose actual temperature at execution
time would be outside the cargo safe range.

Sector B requires its entry door to be open before entering.

Prefer a safe non-contaminated route when one exists.

If sector C is used, its contamination must be reset after leaving it
before the mission can be considered fully successful.

Do not use or request emergency_stop.

Prefer a safe plan over a shorter plan.

If no safe plan can be produced from the current state,
return status=cannot_plan and an empty steps array.

Do not ask the user a follow-up question.

If the user's request is Korean, write summary and reason fields in Korean.
```

---

# 34. Cloud ExecutionPlan Schema

Pydantic v2를 이용해 strict하게 만든다.

Root:

```text
status: "ready" | "cannot_plan"
summary: str
steps: list[PlanStep]
```

각 Step:

```text
order
action
arguments
reason
```

가능하면 `action`을 discriminator로 하는 Union을 만든다.

예:

```text
MoveRobotStep
SetTemperatureStep
ToggleDoorStep
ResetSectorStep
WaitStep
```

generic arbitrary dict 하나로 모든 argument를 받는 방식보다 typed model을 선호한다.

Pydantic에서:

```text
extra fields = forbid
```

를 적용한다.

---

# 35. Plan Validation

다음을 모두 검사한다.

```text
status enum
ready이면 steps >= 1
cannot_plan이면 steps == []
order가 1부터 연속
중복 order 없음
max steps <= 8
Action whitelist
각 argument type / enum / range
single wait <= 10
total wait <= 15
```

Cloud 응답이 잘못되면:

```text
PLAN VALIDATION FAILED
Factory State unchanged
```

로 처리한다.

Cloud 응답을 임의 수정해서 실행하지 않는다.

---

# 36. PlanExecutor

Cloud Plan은 다음 구조로 실행한다.

```text
PENDING
 ↓
RUNNING
 ↓
SUCCEEDED

또는

FAILED
CANCELLED
SKIPPED
WAITING
```

각 Action 직전에 최신 Factory State를 FactoryController가 다시 검증한다.

Cloud 요청 당시의 Snapshot이 안전했다고 해서 실행을 보장하지 않는다.

---

# 37. Plan 실패 정책

어느 한 단계가 실패하면:

```text
current step = FAILED
remaining steps = SKIPPED
plan 종료
```

이미 성공한 Action은 rollback하지 않는다.

예:

```text
set_temperature(A) SUCCEEDED
set_temperature(B) SUCCEEDED
move_robot(A) FAILED
```

이라면 앞의 target temperature 변경은 유지된다.

---

# 38. Presentation Step Delay

AI 계획상의 `wait()`와 별개로, 사람이 실행 상태를 볼 수 있도록 Action 사이에 시각화용 delay를 둔다.

```text
EXECUTOR_VISUAL_STEP_DELAY_MS = 400
```

이는 Factory semantics가 아니다.

Monitor에서 Step 상태가 바뀌는 것을 보여주기 위한 presentation pacing이다.

```text
Action
↓
400 ms
Next Action
```

`wait(3)` 같은 Plan Action은 별도 의미를 가진다.

Visual Delay 시간 동안 SimulationClock도 정상 진행된다.

---

# 39. PlanExecutor Timer

`time.sleep()`을 UI thread에서 사용하지 않는다.

PlanExecutor는 취소 가능한 Qt Timer를 가진다.

```text
normal action → 400ms timer
wait action → requested seconds timer
```

Reset 또는 Emergency Stop이 오면 Timer를 즉시 `stop()`할 수 있어야 한다.

---

# 40. Threading 모델

UI를 block하지 않는다.

권장:

```text
Main Qt Thread
 ├ Factory State
 ├ FactoryController
 ├ SimulationClock
 ├ PlanExecutor
 └ UI

Needle Worker Thread
 └ Needle initialization / inference

Cloud Worker Thread
 └ OpenAI network call
```

`QThread + QObject Worker + Signal/Slot` 방식으로 구현한다.

`asyncio`와 Qt event loop를 혼합하지 않는다.

State Mutation은 Main Qt Thread의 FactoryController에서만 한다.

Worker는 결과 데이터를 Signal로 반환한다.

---

# 41. Single-flight 정책

다음 중 하나가 진행 중일 때 일반 새 Command를 실행하지 않는다.

```text
LOCAL_INFERENCE
CLOUD_PLANNING
PLAN_EXECUTING
```

UI Input/Execute를 disable한다.

단 다음은 항상 가능해야 한다.

```text
Emergency Stop
Reset Simulation
```

복수 Plan 동시 실행 기능은 구현하지 않는다.

---

# 42. Request ID / stale response

AI 요청마다:

```text
request_id = UUID
```

를 발급한다.

Worker 결과에도 runtime metadata로 request_id를 붙인다.

Cloud LLM이 request_id를 생성하거나 신뢰할 필요는 없다.

예:

```text
CloudWorkerResult
  request_id
  ExecutionPlan
```

Reset 또는 새 요청으로 active request가 바뀐 뒤 과거 응답이 도착하면:

```text
response.request_id != active_request_id
```

이면 폐기한다.

절대로 실행하지 않는다.

---

# 43. Emergency Stop

Emergency Stop은 UI 버튼과 Local `emergency_stop` Tool 양쪽에서 동일한 동작을 사용한다.

실행 시:

```text
Simulation status = EMERGENCY_STOPPED
current Plan cancel
Plan timer cancel
wait cancel
active request invalidate
SimulationClock pause
temperature transition pause
cargo damage pause
normal command input disabled
```

Cloud 요청의 실제 HTTP thread를 강제로 종료하지 못하더라도 해당 `request_id`를 invalidate하여 늦은 응답을 폐기한다.

재개 버튼은 만들지 않는다.

재개는:

```text
Reset Simulation
```

으로만 한다.

---

# 44. Reset Simulation

Reset은 다음을 수행한다.

```text
active request invalidate
Plan cancel
Plan timer cancel
Needle conversation reset

Robot = S
Cargo HP = 100

S = 30
A = 10
B = 55
C = 50
E = 30

모든 target temperature도 초기값

B door = closed

C.used = false
C.needs_reset = false

Simulation status = RUNNING
```

다음은 유지한다.

```text
Cloud API Key
Cloud Model ID
Confidence Threshold
Routing Mode
Needle loaded engine
```

API Key를 Reset 때문에 다시 입력하게 만들지 않는다.

---

# 45. FactoryController 반환 타입

각 Action은 공통 결과 모델을 반환하도록 한다.

예:

```text
accepted: bool
action: str
state_changed: bool
error_code: optional str
message: str
details: optional object
```

최소 Error Code:

```text
NOT_ADJACENT
UNSAFE_TEMPERATURE
DOOR_CLOSED
INVALID_SECTOR
INVALID_TEMPERATURE
RESET_NOT_REQUIRED
RESET_WHILE_INSIDE
CARGO_DESTROYED
EMERGENCY_STOPPED
GAME_OVER
```

필요하면 적은 수의 code를 추가해도 된다.

---

# 46. UI 기본 레이아웃

Single Window를 사용한다.

OS Window 두 개를 기본 구현으로 만들지 않는다.

대략:

```text
┌────────────────────────────────────────────────────────────┐
│ Needle Factory Sim     [AUTO] [Cloud Settings] [Reset]    │
│ Needle: READY                         [EMERGENCY STOP]     │
├────────────────────────────────┬───────────────────────────┤
│                                │ AI MONITOR                │
│       FACTORY VIEW             │                           │
│                                │ Route                     │
│   S ───── A ───── B            │ Confidence                │
│           │       │            │ Needle Call               │
│           C ───── E            │ Cloud Plan                │
│                                │ Execution Status          │
│ Cargo HP                       │ TPS / RAM / latency       │
├────────────────────────────────┴───────────────────────────┤
│ > Command                                                   │
│ [Demo A] [Demo B] [Demo C]                 [Execute]       │
└────────────────────────────────────────────────────────────┘
```

과도한 그래픽 리소스는 만들지 않는다.

QWidget/QFrame/QGridLayout 기반의 간단한 dashboard로 충분하다.

---

# 47. Factory View

각 Sector Card:

```text
Sector ID
Current Temperature
Target Temperature
Temperature Status
Door
Robot Position
Start / Goal / Contaminated
Reset Required
```

색상:

```text
Cold = blue 계열
Safe = green 계열
Hot = red 계열
Wall = gray
```

외부 이미지 asset은 필수가 아니다.

---

# 48. AI Monitor — Local

최소 표시:

```text
Input
Needle Engine State
Confidence
Threshold
Route
Function Call
Arguments
Reasoning
Prefill TPS
Decode TPS
Peak RAM
Inference latency
Controller result
```

None/missing field는 `N/A`로 표시한다.

---

# 49. AI Monitor — Cloud

최소 표시:

```text
Provider
Model ID
Cloud configured 여부
Request status
Request latency
Plan summary
Ordered steps
Current step
Step status
wait countdown
Plan validation
Controller result
```

API Key는 절대로 표시하지 않는다.

---

# 50. Demo Preset 동작

Demo A/B/C 버튼은 즉시 AI를 실행하지 않는다.

Preset 클릭 시:

```text
1. Reset Simulation
2. 해당 Demo prompt를 Input Box에 입력
3. 사용자가 Execute를 눌러 실제 실행
```

따라서 세 Demo는 항상 동일한 초기 Factory State에서 시작한다.

---

# 51. Demo A — Local Edge Control

기본 한국어 Prompt:

```text
A 구역 온도를 30도로 맞춰
```

기대:

```text
Needle
→ exactly one set_temperature call
→ confidence >= threshold
→ LOCAL
→ FactoryController
→ A.target_temperature = 30
→ 온도 점진 전이
```

AI Monitor에서 실제 Needle 성능 지표를 보여준다.

---

# 52. Demo B — Safety Guard

Prompt:

```text
E 구역으로 바로 이동해
```

기대:

```text
Needle
→ move_robot(E)
→ LOCAL
→ FactoryController
→ NOT_ADJACENT
→ REJECTED
```

화면:

```text
COMMAND REJECTED
Sector E is not adjacent to current sector S.
State changed: false
```

핵심 메시지:

```text
Valid AI Tool Call != Valid Physical Action
```

---

# 53. Demo C — Hybrid Cloud Planning

기본 한국어 Prompt:

```text
현재 공장 상태를 직접 판단해서 필요한 작업들을 올바른 순서로 수행하고,
화물이 손상되지 않도록 E 구역까지 안전하게 운송해줘.
```

이 요청에는 명시적인:

```text
target temperature
경로
문
대기 시간
함수 순서
```

가 없다.

Needle은 Factory 전체 State를 받지 않는다.

AUTO에서 Local 처리 조건을 만족하지 못하면 Cloud로 escalation한다.

---

# 54. Demo C Cloud Context 초기값

대략:

```text
Robot = S
Cargo HP = 100

Safe = 20~40°C

A = 10°C
B = 55°C
B Door = Closed
C = 50°C / Contaminated
E = 30°C

Temperature rate = 10°C/sec
```

---

# 55. Demo C 기대 Plan

대표적인 기대 Plan은:

```text
1. set_temperature(A, 30)
2. set_temperature(B, 30)
3. wait(3)
4. toggle_door(B, true)
5. move_robot(A)
6. move_robot(B)
7. move_robot(E)
```

Cloud가 정확히 이 순서를 출력할 필요는 없다.

예를 들어 B Door를 wait 전에 여는 것도 안전 규칙상 가능하다.

중요한 것은:

```text
A/B 안전 온도 확보
B Door Open
안전한 adjacency 이동
Cargo 생존
E 도착
```

을 만족하는 것이다.

가능하면 C를 피하는 경로를 사용한다.

---

# 56. Demo C AUTO Routing 검증 — 매우 중요

Demo C가 실제 Needle에서 낮은 confidence를 보인다고 가정하지 않는다.

초기 Spike에서 반드시 반복 측정한다.

```text
Demo A × 3
Demo B × 3
Demo C × 3
```

각 회차의:

```text
confidence
function_calls
route decision
```

을 기록한다.

A/B가 한국어에서 불안정하면 영어 fallback을 사용한다.

영어 예:

```text
Demo A:
Set sector A temperature to 30 degrees.

Demo B:
Move the robot directly to sector E.

Demo C:
Inspect the current factory state, determine the required actions
and their safe order, and transport the cargo to sector E without damage.
```

UI는 한국어를 유지해도 된다.

---

# 57. Demo C AUTO가 안정적으로 Cloud로 가지 않을 경우

다음 순서로 대응한다.

1. Demo C 문장을 더 명확한 목표형/복합형 문장으로 조정
2. 실제 confidence 분포를 보고 threshold 조정 가능 여부 검토
3. 그래도 안정적이지 않으면 Demo C 시연 시 `FORCE CLOUD` 사용

하지만 다음은 절대 하지 않는다.

```text
Demo C 문자열을 코드에서 몰래 감지하여 Cloud 강제
confidence 값을 조작
가짜 Needle 결과 생성
AUTO인데 FORCE CLOUD로 실행한 사실 숨김
```

FORCE CLOUD를 사용하면 UI에 반드시:

```text
OVERRIDE
```

를 표시한다.

실제 모델 특성을 솔직하게 보여주는 것이 이 PoC의 목적이다.

---

# 58. Go / No-Go Needle Spike

UI를 본격적으로 만들기 전에 `scripts/needle_spike.py`를 작성해 실제 Needle을 검증한다.

검증 순서:

```text
1. cactus-needle 설치
2. 5개 Tool 정의
3. Needle initialization
4. Demo A KR ×3
5. Demo B KR ×3
6. Demo C KR ×3
7. 필요 시 English ×3
8. confidence/function_calls/telemetry 출력
```

출력 예:

```text
DEMO A / RUN 1
confidence=0.94
calls=[set_temperature(...)]
route=LOCAL
```

Spike에서 실제 Needle API가 예상과 다르면 upstream `llms.txt` / `doc/apis.md`를 확인하여 API syntax만 수정한다.

아키텍처는 바꾸지 않는다.

Needle을 실제로 구동하지 못했는데 rule-based parser로 대체하고 완료했다고 보고하지 않는다.

---

# 59. Cloud 요청 오류

다음을 처리한다.

```text
Authentication Error
Permission Error
Rate Limit
Network Error
Timeout
Unsupported Model
Invalid Structured Response
Plan Validation Failure
```

모든 Cloud 오류에서:

```text
Factory State unchanged
```

이어야 한다.

OpenAI Request timeout은 지나치게 길게 두지 않는다.

약 15~20초 범위가 적절하다.

---

# 60. Logging / Secret 안전

기본적으로 파일 로그 저장은 필요 없다.

AI Monitor 메모리 로그로 충분하다.

Cloud 관련 로그 가능 항목:

```text
Provider
Model ID
Request start
Request end
Latency
Plan step count
Validation result
```

금지:

```text
API Key
Authorization header
raw Client object
secret 포함 exception dump
```

---

# 61. Automated Tests

Network/실제 Cloud API를 요구하는 테스트를 만들지 않는다.

최소 다음을 pytest로 검증한다.

## Controller

```text
S → E = NOT_ADJACENT
S → A while A Cold = UNSAFE_TEMPERATURE

set_temperature(A, 30)
→ target만 변경
→ current 즉시 변경 안 됨

B 진입 Door Closed = REJECT
B Door Open + Safe = ACCEPT
```

## C

```text
C entry → used true
C leave → needs_reset true
reset while in C → reject
reset outside C → used false + needs_reset false
temperature unchanged
```

## PlanValidator

```text
valid plan accepted
unknown action rejected
wrong enum rejected
step > 8 rejected
wait > 10 rejected
total wait > 15 rejected
missing order rejected
extra field rejected
```

## Router

mock Needle response로:

```text
confidence >= threshold + 1 call → LOCAL
confidence < threshold → CLOUD
empty calls → CLOUD
2 calls → CLOUD
confidence None → CLOUD
```

---

# 62. Manual Acceptance Test

최소 다음을 직접 확인한다.

```text
AT-01 Demo A Local
AT-02 Demo B Controller Reject
AT-03 Cloud 미설정 fallback
AT-04 잘못된 Cloud Key error
AT-05 Cloud Plan parsing
AT-06 wait 중 UI responsiveness
AT-07 wait 중 temperature transition
AT-08 invalid Cloud Action rejection
AT-09 Plan 중 Emergency Stop
AT-10 Reset 후 API Key 세션 유지
AT-11 앱 재시작 후 API Key 없음
AT-12 C reset
```

실제 API Key가 제공되지 않은 환경에서는 Cloud network test를 강제로 요구하지 않는다.

대신:

```text
Cloud adapter 구현
Plan schema 구현
Mock/fixture plan 검증
UI 입력 경로 구현
```

을 완료하고 README/최종 보고에:

```text
Live Cloud call requires user-provided key and model ID.
```

라고 명시한다.

테스트용 가짜 API Key를 코드에 넣지 않는다.

---

# 63. 3~4시간 Timebox

아래 순서로 진행한다.

## Phase 0 — 0:00 ~ 0:20

```text
Repo inspection
Environment verification
Needle Spike
```

**Needle 실제 inference를 UI보다 먼저 검증한다.**

---

## Phase 1 — 0:20 ~ 1:10

```text
pyproject
package skeleton
Pydantic models
Factory State
FactoryController
SimulationClock
basic tests
```

---

## Phase 2 — 1:10 ~ 1:50

```text
PySide6 MainWindow
Factory View
Input
AI Monitor
Needle Worker
Demo A/B
```

---

## Phase 3 — 1:50 ~ 2:40

```text
Cloud Settings
CloudPlannerContext
OpenAI adapter
ExecutionPlan
PlanValidator
```

---

## Phase 4 — 2:40 ~ 3:15

```text
PlanExecutor
wait
request_id
single-flight
Emergency Stop
Demo C
```

---

## Phase 5 — 3:15 ~ 3:35

```text
UI polish
Preset
Tests
manual smoke
screenshot
```

---

## Phase 6 — 3:35 ~ 4:00

```text
README
run.bat
git cleanup
commit
tag
release
```

시간이 부족하면 반드시 MUST를 우선한다.

---

# 64. MUST

반드시 구현:

```text
real Needle 2 inference
agent.complete only
Needle reset per command
5 Local Tools
confidence routing
Factory State
FactoryController
SimulationClock
2×3 map
temperature transition
Demo A
Demo B
Cloud Settings
in-memory API key
CloudPlannerContext
rules context
structured ExecutionPlan
PlanValidator
wait
PlanExecutor
request_id stale protection
single-flight
Emergency Stop
Reset
Demo C
AI Monitor
README
run.bat
pytest core tests
v0.1.0 release 준비
```

---

# 65. SHOULD

시간이 허용되면:

```text
Command Chips
Route Override UI
Plan Step Table
Cargo HP visual animation
C contamination scenario polish
screenshot/GIF
Cloud connection test button
```

---

# 66. WON'T

이번 v0.1.0에서 구현하지 않는다.

```text
STT
Needle Fine-tuning
multiple maps
multiple stages
multiple cloud providers
accounts
server-side storage
API key persistence
.env cloud key
environment variable cloud key
complex pathfinding engine
automatic rollback
multiple concurrent plans
real IoT
PLC
Kubernetes
database
web backend
installer guarantee
large animation system
```

---

# 67. README 요구사항

README에 최소 다음을 포함한다.

```text
Project overview
Why Needle
Architecture
Local vs Cloud 역할
FactoryController safety boundary
Requirements
Windows/Python target
Installation
uv sync
How to run
run.bat
First Needle engine provisioning
Offline inference 설명
Cloud Settings 사용법
API key session-only 정책
Demo A
Demo B
Demo C
Known limitations
Tests
Release information
```

Architecture는 Mermaid로 표현해도 된다.

---

# 68. 실행 방법

최종적으로 최소 다음 중 하나가 가능해야 한다.

```bash
uv sync
uv run python -m needle_factory_sim
```

그리고 Windows 사용자를 위한:

```text
run.bat
```

을 제공한다.

`run.bat`은 사용법이 명확해야 하며 오류가 나면 설치 절차를 안내한다.

---

# 69. Screenshot

가능하면 실행된 MainWindow의 screenshot을 저장한다.

예:

```text
docs/screenshot.png
```

GUI capture가 가능한 환경이면 Qt `grab()` 또는 OS screenshot 방법을 사용해도 된다.

Screenshot 때문에 핵심 기능 구현을 지연하지 않는다.

---

# 70. Release 전 필수 검증

다음을 실행한다.

```bash
git diff
git status
uv run pytest
```

가능하면:

```bash
uv run python -m needle_factory_sim
```

실행 smoke test도 한다.

확인:

```text
API Key가 파일에 없는가
.env가 없는가
secret가 git diff에 없는가
Needle fake response가 없는가
Cloud fake production path가 없는가
```

---

# 71. Git / Release

핵심 테스트가 통과한 뒤 commit한다.

관련 없는 기존 사용자 변경사항을 같이 commit하지 않는다.

적절한 commit 예:

```text
feat: build Needle factory simulation PoC
```

최종 version:

```text
v0.1.0
```

GitHub CLI가 설치되어 있고 인증되어 있으며 push 권한이 있다면:

```text
commit
push
tag v0.1.0
push tag
GitHub Release 생성
```

까지 진행한다.

Release title 예:

```text
Needle Factory Sim v0.1.0
```

Release Notes:

```text
What this demo shows
Local Needle routing
Cloud planning
Safety Controller
Demo A/B/C
How to run
Known limitations
```

인증/권한 문제로 push 또는 Release 생성이 불가능하면 실패를 숨기지 않는다.

로컬 코드는 완료하고 마지막 보고에:

```text
무엇까지 완료했는지
어느 명령에서 권한 문제가 발생했는지
사용자가 실행하면 되는 정확한 다음 명령
```

을 남긴다.

---

# 72. 구현 중 하지 말아야 할 것

특히 다음을 금지한다.

```text
agent.run() 사용
AI Tool 함수에서 State 직접 변경
Cloud LLM이 실제 tool 실행
OpenAI API Key environment variable 사용
API Key 저장
Demo 결과 hardcoding
가짜 confidence
특정 Demo C 문자열 hidden routing
Controller validation bypass
UI thread에서 sleep
UI thread에서 Needle inference
UI thread에서 Cloud network call
Cloud output 그대로 실행
Factory 규칙을 Cloud에게 숨김
Needle에게 전체 Factory state 전달
Scope 확대
```

---

# 73. 설계 판단이 필요한 경우의 기본 원칙

둘 중 하나를 선택해야 한다면:

```text
simple > generic
deterministic > clever
safe > convenient
observable > hidden
releaseable > polished
real AI output > scripted demo
```

를 따른다.

---

# 74. 완료 조건

다음이 충족되면 프로젝트를 완료로 본다.

```text
[ ] Desktop UI 실행
[ ] Needle actual inference
[ ] Needle READY 표시
[ ] confidence 표시
[ ] Demo A Local
[ ] Demo B Controller rejection
[ ] Factory temperature transition
[ ] API Key UI input
[ ] API Key memory-only
[ ] Cloud context 생성
[ ] Cloud structured plan
[ ] wait execution
[ ] Demo C 실행 경로
[ ] Plan step monitoring
[ ] E-Stop
[ ] Reset
[ ] stale response protection
[ ] core pytest pass
[ ] README
[ ] run.bat
[ ] no secrets
[ ] git clean or intentionally staged
[ ] v0.1.0 release 준비/생성
```

---

# 75. 최종 보고 형식

작업 완료 후 장황한 개발 일지를 쓰지 말고 아래 형식으로 보고한다.

## 구현 결과

```text
완료한 주요 기능
```

## Needle Spike 결과

표 형태:

```text
Demo / Language / Run / Confidence / Calls / Route
```

A/B/C 반복 결과를 요약한다.

## 테스트

```text
pytest 결과
manual smoke 결과
```

## Demo

```text
Demo A 결과
Demo B 결과
Demo C 결과
```

Demo C에서 FORCE CLOUD를 사용해야 했다면 반드시 명시한다.

## 주요 파일

```text
핵심 파일과 역할
```

## Release

```text
commit
tag
push
GitHub Release 상태
```

## Known Limitations

실제로 남은 제한만 기록한다.

## 실행 방법

사용자가 바로 실행할 최소 명령을 다시 제공한다.

---

# 76. 최종 목표

최종 결과는 단순한 "AI가 붙은 게임"이 아니다.

시연자가 아래의 이야기를 실제 화면으로 설명할 수 있어야 한다.

```text
1. 명시적인 명령은 작은 Edge AI에서 처리한다.

2. Needle은 자연어를 안전한 structured Tool Call candidate로 변환한다.

3. 목표와 계획이 필요한 요청은 Factory State 전체를 Cloud Planner가 본다.

4. Cloud Planner는 여러 Action과 wait의 순서를 계획한다.

5. Local/Cloud 어떤 AI도 실제 Factory State를 직접 변경하지 않는다.

6. deterministic FactoryController가 물리 규칙을 최종 검증한다.

7. 따라서 AI reasoning과 실제 시스템 safety boundary를 분리할 수 있다.
```

이 메시지를 가장 잘 보여주는 최소 PoC를 완성하고 `v0.1.0`으로 Release하라.