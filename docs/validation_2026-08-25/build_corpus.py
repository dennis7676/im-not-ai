#!/usr/bin/env python3
"""세션 로그에서 사용자 발화와 에이전트 응답을 뽑아 코퍼스를 재생성한다.

원본(2026-08-25 홈맥)은 사용자 1,500건 276,770자 대 에이전트 2,814,379자였다.
재생성본이 그 수치와 정확히 같을 필요는 없으나, **다르면 다르다고 보고한다** —
같은 척 하면 앞 세션 기준선과 비교할 수 없는 것을 비교하게 된다.
"""
import json, os, re, sys, glob

ROOT = os.path.expanduser("~/.claude/projects")
OUT = os.path.expanduser("~/dp_corpus")
os.makedirs(OUT, exist_ok=True)

# 사람이 친 것이 아닌 것들 — 훅 주입, 시스템 리마인더, 커맨드 확장, 도구 결과
NOISE = re.compile(
    r"<system-reminder>|<command-name>|<command-message>|<local-command|"
    r"UserPromptSubmit hook|Caveat: The messages below|"
    r"\[Request interrupted|<user-memory-input>|tool_use_id"
)

def texts(content):
    if isinstance(content, str):
        return [content]
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                out.append(b["text"])
    return out

user_chunks, asst_chunks = [], []
files = glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True)
for fp in files:
    try:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                t = rec.get("type")
                msg = rec.get("message") or {}
                if t == "user":
                    if rec.get("isMeta") or rec.get("isCompactSummary"):
                        continue
                    for tx in texts(msg.get("content")):
                        tx = tx.strip()
                        if not tx or NOISE.search(tx):
                            continue
                        if tx.startswith("/"):          # 슬래시 커맨드는 발화가 아니다
                            continue
                        if len(re.findall(r"[가-힣]", tx)) < 5:
                            continue
                        user_chunks.append(tx)
                elif t == "assistant":
                    for tx in texts(msg.get("content")):
                        tx = tx.strip()
                        if not tx or NOISE.search(tx):
                            continue
                        if len(re.findall(r"[가-힣]", tx)) < 5:
                            continue
                        asst_chunks.append(tx)
    except Exception:
        continue

def dump(name, chunks):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n<<<CHUNK>>>\n\n".join(chunks))
    return path, len(chunks), sum(len(c) for c in chunks)

for name, chunks in (("user_utterances.txt", user_chunks), ("asst_responses.txt", asst_chunks)):
    path, n, chars = dump(name, chunks)
    print(f"{name}: {n}건 {chars}자 -> {path}")
