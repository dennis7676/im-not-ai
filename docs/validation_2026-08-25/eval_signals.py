#!/usr/bin/env python3
"""L-1 + KatFish 신호 3종의 정밀도·재현율. 임계는 design 에서만 고른다."""
import json, sys, statistics as st
sys.path.insert(0, "/Users/1109698/.claude/forks/im-not-ai/skills/humanize-korean/references")
import metrics_v2 as m

user = open("user_chunks.txt", encoding="utf-8").read().split("\n<<<C>>>\n")
asst = open("asst_chunks.txt", encoding="utf-8").read().split("\n<<<C>>>\n")
sp = json.load(open("split.json"))

SIGNALS = {
    "vague_noun_rate":    (m.vague_noun_rate,    "high"),   # 높을수록 AI
    "nominal_dominance":  (m.nominal_dominance,  "high"),
    "spacing_uniformity": (m.spacing_uniformity, "low"),    # 낮을수록 AI(기계적 균일)
    "noun_string_max":    (m.noun_string_max,    "high"),
    "light_verb_rate":    (m.light_verb_rate,    "high"),
}

def vals(fn, texts, idx):
    return [fn(texts[i]) for i in idx]

def prf(pos_ai, pos_hu):
    """pos_* = 각 클래스에서 'AI다'로 판정된 수"""
    tp, fp = pos_ai, pos_hu
    fn = None
    return tp, fp

def score(thr, direction, ai_v, hu_v):
    hit = (lambda v: v >= thr) if direction == "high" else (lambda v: v <= thr)
    tp = sum(1 for v in ai_v if hit(v))
    fp = sum(1 for v in hu_v if hit(v))
    fn = len(ai_v) - tp
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1

def auc(ai_v, hu_v, direction):
    """Mann-Whitney U 기반 AUC. 동점은 0.5로 센다."""
    if direction == "low":
        ai_v = [-v for v in ai_v]; hu_v = [-v for v in hu_v]
    wins = ties = 0
    for a in ai_v:
        for h in hu_v:
            if a > h: wins += 1
            elif a == h: ties += 1
    n = len(ai_v) * len(hu_v)
    return (wins + 0.5 * ties) / n if n else 0.0

rows = []
for name, (fn, direction) in SIGNALS.items():
    ai_d = vals(fn, asst, sp["asst_design"]);  hu_d = vals(fn, user, sp["user_design"])
    ai_h = vals(fn, asst, sp["asst_holdout"]); hu_h = vals(fn, user, sp["user_holdout"])

    # 임계 후보는 design 값들만 본다
    cands = sorted(set(ai_d + hu_d))
    best = max(((score(t, direction, ai_d, hu_d), t) for t in cands), key=lambda x: x[0][2])
    (p_d, r_d, f_d), thr = best
    p_h, r_h, f_h = score(thr, direction, ai_h, hu_h)   # 임계 그대로 적용
    rows.append({
        "signal": name, "dir": direction, "thr": round(thr, 4),
        "design": (round(p_d,3), round(r_d,3), round(f_d,3)),
        "holdout": (round(p_h,3), round(r_h,3), round(f_h,3)),
        "auc_holdout": round(auc(ai_h, hu_h, direction), 4),
        "med_ai": round(st.median(ai_h),3), "med_hu": round(st.median(hu_h),3),
    })

print(f"{'신호':<20}{'임계':>9}{'design F1':>11}{'holdout P':>11}{'holdout R':>11}{'holdout F1':>12}{'AUC':>8}")
print("-"*84)
for r in rows:
    print(f"{r['signal']:<20}{r['thr']:>9}{r['design'][2]:>11}{r['holdout'][0]:>11}{r['holdout'][1]:>11}{r['holdout'][2]:>12}{r['auc_holdout']:>8}")
print()
for r in rows:
    print(f"  {r['signal']}: 중앙값 AI {r['med_ai']} 대 사람 {r['med_hu']} ({r['dir']}=AI신호)")
json.dump(rows, open("eval_results.json","w"), ensure_ascii=False, indent=2)
