#!/usr/bin/env python3
"""코퍼스 정제 + 1,500자 조각화.

⚠️ 원본(2026-08-25) 필터를 모른다. 그래서 **재현했다고 주장하지 않는다.**
   여기서 하는 일은 이 세션이 쓸 코퍼스의 정의를 명시하고 고정하는 것뿐이고,
   앞 세션 기준선(사용자 16.4 대 에이전트 54.5)과 직접 비교하지 않는다.

필터는 양쪽에 **대칭으로** 건다:
  - 한글 비율 >= 0.30  (붙여넣은 트레이스백·로그·코드 덩어리 배제)
  - 길이 20~2000자     (장문 붙여넣기 스펙 문서 배제)
"""
import re, os, statistics as st

SRC = os.path.expanduser("~/dp_corpus")
CHUNK = 1500

def load(name):
    return open(os.path.join(SRC, name), encoding="utf-8").read().split("\n\n<<<CHUNK>>>\n\n")

def keep(t):
    if not (20 <= len(t) <= 2000):
        return False
    return len(re.findall(r"[가-힣]", t)) / len(t) >= 0.30

def chunks(texts):
    body = "\n".join(t for t in texts if keep(t))
    return [body[i:i+CHUNK] for i in range(0, len(body), CHUNK) if len(body[i:i+CHUNK]) >= CHUNK//2]

for src, dst in (("user_utterances.txt", "user_chunks.txt"),
                 ("asst_responses.txt", "asst_chunks.txt")):
    raw = load(src)
    kept = [t for t in raw if keep(t)]
    ck = chunks(raw)
    out = os.path.join(SRC, dst)
    open(out, "w", encoding="utf-8").write("\n<<<C>>>\n".join(ck))
    print(f"{src}: 원본 {len(raw)}건 -> 통과 {len(kept)}건 {sum(len(t) for t in kept)}자 -> 조각 {len(ck)}개")
