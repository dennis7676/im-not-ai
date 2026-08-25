#!/usr/bin/env python3
"""저자 불변성 — 같은 프롬프트를 클로드와 코덱스에 주고 AI 티 신호를 대조한다.

묻는 것 하나: **우리 계측기는 "AI"를 재는가, "클로드"를 재는가.**
클로드에서만 신호가 뜨면 taxonomy 의 근거가 흔들린다.
"""
import os, sys, json, statistics as st
R="/Users/1109698/.claude/forks/im-not-ai/skills/humanize-korean/references"
sys.path.insert(0,R)
import metrics_v2 as m2, metrics as m1

HERE=os.path.dirname(os.path.abspath(__file__))
IDS=["A1","A2","B1","B2"]
GENRE={"A1":"검토물","A2":"검토물","B1":"블로그","B2":"블로그"}
SIG=[("vague_noun_rate",m2.vague_noun_rate),
     ("nominal_dominance",m2.nominal_dominance),
     ("spacing_uniformity",m2.spacing_uniformity),
     ("noun_string_max",m2.noun_string_max),
     ("light_verb_rate",m2.light_verb_rate),
     ("comma_inclusion_rate",m1.comma_inclusion_rate),
     ("ending_comma_rate",m1.ending_comma_rate),
     ("hanja_nominalizer_density",m1.hanja_nominalizer_density)]

def load(author,i):
    p=os.path.join(HERE,"authorship",f"{author}_{i}.txt")
    if not os.path.exists(p): return None
    t=open(p,encoding="utf-8").read().strip()
    return t or None

data={}
for a in ("claude","codex"):
    for i in IDS:
        t=load(a,i)
        if t is None: print(f"  ⚠️ 없음: {a}_{i}"); continue
        data[(a,i)]={"len":len(t), **{n:round(f(t),4) for n,f in SIG}}

print(f"{'표본':<14}{'장르':<8}{'자수':>6}", end="")
for n,_ in SIG: print(f"{n[:13]:>15}", end="")
print("\n"+"-"*(28+15*len(SIG)))
for i in IDS:
    for a in ("claude","codex"):
        d=data.get((a,i))
        if not d: continue
        print(f"{a+'_'+i:<14}{GENRE[i]:<8}{d['len']:>6}", end="")
        for n,_ in SIG: print(f"{d[n]:>15}", end="")
        print()

print("\n=== 저자별 중앙값 (짝지은 4편씩) ===")
print(f"{'신호':<26}{'클로드':>12}{'코덱스':>12}{'차이':>12}")
print("-"*62)
verdict=[]
for n,_ in SIG:
    cl=[data[("claude",i)][n] for i in IDS if ("claude",i) in data]
    cx=[data[("codex",i)][n] for i in IDS if ("codex",i) in data]
    if not cl or not cx: continue
    a,b=st.median(cl),st.median(cx)
    print(f"{n:<26}{a:>12.4f}{b:>12.4f}{b-a:>+12.4f}")
    verdict.append((n,a,b))
json.dump({f"{k[0]}_{k[1]}":v for k,v in data.items()}, open(os.path.join(HERE,"authorship_metrics.json"),"w"), ensure_ascii=False, indent=2)
print("\n-> authorship_metrics.json")
