#!/usr/bin/env python3
"""design/holdout 분할 — 계측 이전에 먼저 가른다.

T4 판별기에서 이 순서를 안 지켜 설계셋 1.0 / 홀드아웃 0.6 을 잘못 읽은 전례가 있다.
분할은 조각 인덱스만 보고 하며 본문도 지표도 보지 않는다.
"""
import json, random

SEED = 20260825
user = open("user_chunks.txt", encoding="utf-8").read().split("\n<<<C>>>\n")
asst = open("asst_chunks.txt", encoding="utf-8").read().split("\n<<<C>>>\n")

rng = random.Random(SEED)
# 클래스 균형: 사용자 조각 수에 맞춰 에이전트를 뽑는다
asst_idx = rng.sample(range(len(asst)), len(user))

def halve(idx):
    idx = list(idx)
    rng.shuffle(idx)
    mid = len(idx) // 2
    return idx[:mid], idx[mid:]

u_des, u_hold = halve(range(len(user)))
a_des, a_hold = halve(asst_idx)

split = {"seed": SEED,
         "user_design": u_des, "user_holdout": u_hold,
         "asst_design": a_des, "asst_holdout": a_hold}
json.dump(split, open("split.json", "w"), ensure_ascii=False)
print(f"design: 사람 {len(u_des)} + AI {len(a_des)}   holdout: 사람 {len(u_hold)} + AI {len(a_hold)}")
print("seed:", SEED, "-> split.json 고정")
