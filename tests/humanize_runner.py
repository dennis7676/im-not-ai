"""Live humanize runner — 배포된 humanize-korean 스킬을 `claude -p`로 실제 호출.

살아있는 스킬을 돌려 갓 나온 윤문본을 얻는다. test_humanize_live.py와
generate_fixtures.py가 공유한다. `claude` CLI(Claude Code, 구독 인증)만 있으면 되고
별도 API 키는 필요 없다. 스킬은 이 레포의 skills/humanize-korean 에서 탐색됨
(claude 를 레포 루트에서 실행).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_START, _END = "<<<H>>>", "<<</H>>>"
_SENTINEL = re.compile(re.escape(_START) + r"(.*?)" + re.escape(_END), re.S)

CLAUDE_BIN = shutil.which("claude")


class SkillUnavailable(RuntimeError):
    """claude CLI 부재 / 타임아웃 / 출력 파싱 실패."""


def _prompt(text: str, strict: bool) -> str:
    """스킬 실행 프롬프트.

    두 구절이 계측을 위해 **의도적으로** 들어가 있다 (2026-08-25 실측).

    - 서브에이전트 호출을 명시 요청한다. 헤드리스 세션 프롬프트에
      ``Do not call the AgentTool unless the user requested it`` 이 박혀 있어,
      스킬 절차가 "Agent 도구로 호출"이라 지정해도 그것만으로는 안 불린다.
      이 문장이 없으면 `humanize-monolith` 호출이 **0/11**, 있으면 **3/3** 이었다.
      monolith 가 안 돌면 `final.md` 가 없고 Phase 2.5 게이트도 대상이 없다.
    - **"파일은 만들지 마"를 넣지 않는다.** 검증 단계가 파일 기반이라 그 구절 하나가
      그것을 통째로 죽인다(Bash 호출 0회 대 5회).

    ⚠️ **채점 축의 이름을 프롬프트에 적지 않는다.** `test_content_anchor_contract` 가
    "변경률", "보호 토큰" 등을 막는데, 그것은 옳다 — 재는 축을 알려 주면 이 테스트는
    "스킬이 지키는가"가 아니라 "모델이 지시를 따르는가"를 재게 된다. 요청은 **절차**
    (서브에이전트를 쓰라)까지이고 **기준**(변경률을 낮춰라)이면 안 된다.

    부수 효과: 파이프라인이 돌면 변경률이 0.414~0.667 에서 0.266~0.386 으로 떨어진다.
    monolith 는 `보수` 강도 지시를 받고 고치는데, 인라인 재작성은 그 지시를 안 받는다.

    전문: `docs/validation_2026-08-25_agent-suppression.md`
    """
    mode = "strict(5인 파이프라인)" if strict else "Fast"
    return (
        f"다음 텍스트를 humanize-korean 스킬 {mode} 모드로 윤문해줘. "
        f"스킬 절차대로 서브에이전트를 Agent(Task) 도구로 호출해서 처리해줘. "
        f"설명·헤딩·지표 전부 빼고, 윤문된 본문만 반드시 {_START} 와 {_END} 사이에 "
        f"한 덩어리로 출력해.\n\n텍스트:\n" + text
    )


def run_humanize(
    text: str, *, strict: bool = False, timeout: int = 900, model: str | None = None
) -> str:
    """스킬을 실제 호출해 윤문본을 반환. 실패 시 SkillUnavailable.

    timeout 기본값이 900 인 이유(2026-08-25): 프롬프트가 서브에이전트를 명시 요청하게
    바뀌면서 파이프라인이 실제로 돌기 시작했고, 그러자 호출당 5분을 넘겼다. 300 이던
    이전 값으로는 **모든 fixture 가 타임아웃으로 죽는다** — 실측으로 확인했다.
    파이프라인이 안 돌 때는 인라인 재작성이라 빨랐던 것이지 빠른 게 정상이 아니었다.

    model: `claude --model` 로 넘길 모델 ID(예: "claude-sonnet-5").
           None 이면 CLI 기본 모델. 모델 간 품질 비교(scripts/eval_baseline.py)에 쓴다.
    """
    if not CLAUDE_BIN:
        raise SkillUnavailable("`claude` CLI를 찾을 수 없음 (Claude Code 설치 필요)")
    cmd = [CLAUDE_BIN]
    if model:
        cmd += ["--model", model]
    cmd += ["-p", _prompt(text, strict)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=_REPO_ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SkillUnavailable(f"claude 호출 타임아웃 ({timeout}s)") from exc

    out = proc.stdout or ""
    match = _SENTINEL.search(out)
    if not match:
        raise SkillUnavailable(f"센티넬 파싱 실패. 원출력 앞부분: {out[:200]!r}")
    return match.group(1).strip()
