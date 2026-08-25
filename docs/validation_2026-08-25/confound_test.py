#!/usr/bin/env python3
"""교란 가설을 잰다: 사용자 조각을 화행으로 갈라 nominal_dominance 를 다시 본다.

가설 — 뒤집힘의 원인은 신호가 아니라 사용자 코퍼스가 '지시문'이라는 것이다.
참이면, 사용자 조각 중 **산문에 가까운** 부분집합은 AI 값(0.844) 쪽으로 내려가야 한다.
"""
import json, re, sys, statistics as st
sys.path.insert(0,"/Users/1109698/.claude/forks/im-not-ai/skills/humanize-korean/references")
import metrics_v2 as m

user=open("user_chunks.txt",encoding="utf-8").read().split("\n<<<C>>>\n")
asst=open("asst_chunks.txt",encoding="utf-8").read().split("\n<<<C>>>\n")
sp=json.load(open("split.json"))
A=[asst[i] for i in sp["asst_design"]+sp["asst_holdout"]]

# 명령형 밀도 — 지시문 표지. 문장 끝의 명령·요청형만 센다.
IMP=re.compile(r"(?:해줘|해라|하라|해봐|봐줘|줘|하자|할까|해야|하고싶|알려줘|만들어|정리해|확인해|보내|찾아)[\s.!?,)\]]|"
               r"(?:해줘|해라|하라|해봐|줘|하자)$", re.M)
def imp_density(t):
    b=m._strip_markup(t)
    return len(IMP.findall(b))/max(len(b),1)*1000   # 1천자당

d=[(imp_density(t), m.nominal_dominance(t), t) for t in user]
d.sort(key=lambda x:x[0])
n=len(d); q=n//3
low  = d[:q]        # 명령형 적음 = 산문에 가까움
high = d[-q:]       # 명령형 많음 = 지시문
ai_nd = [m.nominal_dominance(t) for t in A]

print(f"사용자 조각 {n}개를 명령형 밀도로 3등분 (각 {q}개)\n")
print(f"{'구간':<28}{'명령형/1천자 중앙':>18}{'nominal_dominance 중앙':>24}")
print("-"*72)
for label, grp in (("산문에 가까움 (하위 1/3)", low), ("지시문 (상위 1/3)", high)):
    print(f"{label:<28}{st.median(x[0] for x in grp):>18.2f}{st.median(x[1] for x in grp):>24.3f}")
print(f"{'에이전트 (대조)':<28}{'—':>18}{st.median(ai_nd):>24.3f}")

lo=st.median(x[1] for x in low); hi=st.median(x[1] for x in high); ai=st.median(ai_nd)
print()
if lo < hi:
    print(f"-> 명령형이 적을수록 nominal_dominance 가 내려간다 ({hi:.3f} -> {lo:.3f}).")
    print(f"   에이전트 {ai:.3f} 와의 간격이 {hi-ai:+.3f} 에서 {lo-ai:+.3f} 로 좁혀졌다.")
    print("   => 화행 교란 가설 지지.")
else:
    print(f"-> 내려가지 않았다 ({hi:.3f} -> {lo:.3f}). 화행으로 설명되지 않는다.")
