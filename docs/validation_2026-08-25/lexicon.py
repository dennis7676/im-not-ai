#!/usr/bin/env python3
"""치환 사전 후보 — 사용자는 쓰는데 에이전트는 안 쓰는 '구체어'.

앞 시도의 결함 둘을 고쳤다:
 1) 분모를 105조각 균형표본으로 썼더니 흔한 말이 0 으로 잡혔다(희소성 artifact).
    -> 에이전트는 **전체 코퍼스**(1,406조각)를 분모로 쓴다.
 2) 명령형·대화체("찾아봐", "알려줘", "~해줘")가 상위를 덮었다. 이건 어휘 선호가
    아니라 화행(speech act) 차이다. -> 용언·명령형을 걸러 명사류만 남긴다.
"""
import re, json, sys
from collections import Counter
sys.path.insert(0,"/Users/1109698/.claude/forks/im-not-ai/skills/humanize-korean/references")
import metrics_v2 as m

user=open("user_chunks.txt",encoding="utf-8").read().split("\n<<<C>>>\n")
asst=open("asst_chunks.txt",encoding="utf-8").read().split("\n<<<C>>>\n")   # 전량

TOK=re.compile(r"[가-힣]{2,}")
JOSA=re.compile(r"(?:은|는|이|가|을|를|의|에서|에|으로|로|와|과|도|만|들|이라|이고)$")
# 용언·대화체 꼬리 — 화행 차이라 치환 사전 대상이 아니다
VERBY=re.compile(r"(?:해줘|하자|해봐|봐|줘|해서|하고|하는|한다|합니다|했|하며|되는|되고|된다|입니다|이다|어요|아요|네요|겠|자|음|기)$")

def freq(texts):
    c=Counter(); n=0
    for t in texts:
        b=m._strip_markup(t); n+=len(b)
        for w in TOK.findall(b):
            w=JOSA.sub("",w)
            if len(w)<2 or VERBY.search(w): continue
            c[w]+=1
    return c,n

cu,nu=freq(user); ca,na=freq(asst)
print(f"사용자 {nu:,}자 / 에이전트 {na:,}자 (배수 {na/nu:.1f})")

rows=[]
for w,ku in cu.items():
    if ku<8: continue                      # 사용자 8회 이상만 (우연 배제)
    ru=ku/nu*100000; ra=ca.get(w,0)/na*100000
    ratio = ru/ra if ra else float("inf")
    if ratio>=3.0:
        rows.append((ratio,w,ku,ca.get(w,0),round(ru,1),round(ra,1)))
rows.sort(key=lambda r:(-r[0],-r[2]))
print(f"\n{'말':<12}{'사용자':>7}{'AI':>8}{'10만자당 U':>12}{'10만자당 A':>12}{'배수':>9}")
print("-"*62)
for r in rows[:30]:
    rt = "∞" if r[0]==float("inf") else f"{r[0]:.1f}"
    print(f"{r[1]:<12}{r[2]:>7}{r[3]:>8}{r[4]:>12}{r[5]:>12}{rt:>9}")
out=[{"word":r[1],"user_n":r[2],"asst_n":r[3],"user_per100k":r[4],"asst_per100k":r[5],
      "ratio":(None if r[0]==float('inf') else round(r[0],2))} for r in rows]
json.dump(out, open("lexicon_candidates.json","w"), ensure_ascii=False, indent=2)
print(f"\n후보 {len(rows)}건 -> lexicon_candidates.json")
print("\n=== 핸드오프가 지목한 '덩어리' 대조 ===")
print(f"덩어리: 사용자 {cu.get('덩어리',0)}회 / 에이전트 {ca.get('덩어리',0)}회")
