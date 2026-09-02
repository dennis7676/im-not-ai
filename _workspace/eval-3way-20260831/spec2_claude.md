# humanize-korean 3자 eval — 작업자: claude

## 할 일

아래 픽스처 3개를 humanize-korean 스킬로 윤문하고, 각각 지정된 경로에 결과만 저장한다.

| 입력 | 출력 |
|---|---|
| /Users/1109698/.claude/forks/im-not-ai/_workspace/eval-3way-20260831/input/fx_m1.txt | /Users/1109698/.claude/forks/im-not-ai/_workspace/eval-3way-20260831/out2/fx_m1.claude.md |
| /Users/1109698/.claude/forks/im-not-ai/_workspace/eval-3way-20260831/input/fx_m2.txt | /Users/1109698/.claude/forks/im-not-ai/_workspace/eval-3way-20260831/out2/fx_m2.claude.md |
| /Users/1109698/.claude/forks/im-not-ai/_workspace/eval-3way-20260831/input/fx_legacy.txt | /Users/1109698/.claude/forks/im-not-ai/_workspace/eval-3way-20260831/out2/fx_legacy.claude.md |

## 스킬 위치

- 절차: `~/.codex/skills/humanize-korean/SKILL.md`
- 룰북: `~/.codex/skills/humanize-korean/references/quick-rules.md`
- 분류 체계 본진(필요할 때만): `~/.codex/skills/humanize-korean/references/ai-tell-taxonomy.md`

스킬 절차를 읽고 그대로 수행한다. 요약본을 지어내지 말고 실제 파일을 읽는다.

## 불변 규칙

- 출력 파일에는 **윤문된 본문만** 쓴다. 헤딩, 설명, 지표, 코드펜스, 감상 전부 금지
- 사실, 수치, 고유명사, 인용은 한 글자도 바꾸지 않는다
- 원문의 격식을 유지한다. 격식체는 격식체로, 구어는 구어로
- 원문에 없던 수사나 상투구를 새로 넣지 않는다
- 윤문은 두 방향이다. 과잉 수사는 덜어내고, 과압축(조사·어미 탈락, 서술어 없는 종결,
  성분 생략)은 복원한다. **단 복원할 근거가 원문 안에 없으면 그 문장은 그대로 둔다**

## 완료 보고 형식

파일 3개를 쓴 뒤 한 줄로만 보고한다: `완료 3/3 — {각 파일 글자 수}`
파일을 못 쓴 것이 있으면 그 사유를 한 줄 덧붙인다.
