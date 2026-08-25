#!/usr/bin/env python3
"""장르별 변경률 밴드 — 8편에 윤문을 태우고 전후 변경률을 잰다."""
import os, sys, json, time
FORK="/Users/1109698/.claude/forks/im-not-ai"
sys.path.insert(0, os.path.join(FORK,"tests"))
sys.path.insert(0, os.path.join(FORK,"skills/humanize-korean/references"))
import humanize_runner as hr
import metrics_v2 as m2

HERE=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.join(HERE,"authorship")
OUT=os.path.join(HERE,"bands"); os.makedirs(OUT, exist_ok=True)
GENRE={"A1":"검토물","A2":"검토물","B1":"블로그","B2":"블로그"}

rows=[]
for author in ("claude","codex"):
    for i in ("A1","A2","B1","B2"):
        src=os.path.join(SRC,f"{author}_{i}.txt")
        before=open(src,encoding="utf-8").read().strip()
        dst=os.path.join(OUT,f"{author}_{i}.out.txt")
        if os.path.exists(dst):
            after=open(dst,encoding="utf-8").read()
        else:
            t0=time.time()
            after=hr.run_humanize(before, strict=False)
            open(dst,"w",encoding="utf-8").write(after)
            print(f"  {author}_{i} 윤문 {time.time()-t0:.0f}초", flush=True)
        cr=m2.change_rate(before, after)
        rows.append({"author":author,"id":i,"genre":GENRE[i],
                     "change_rate":round(cr,4),
                     "len_before":len(before),"len_after":len(after),
                     "vague_before":round(m2.vague_noun_rate(before),1),
                     "vague_after":round(m2.vague_noun_rate(after),1)})
json.dump(rows, open(os.path.join(HERE,"band_results.json"),"w"), ensure_ascii=False, indent=2)
print("\n"+f"{'표본':<14}{'장르':<8}{'변경률':>9}{'포괄어 전':>10}{'후':>8}{'길이비':>9}")
print("-"*60)
for r in rows:
    print(f"{r['author']+'_'+r['id']:<14}{r['genre']:<8}{r['change_rate']:>9.3f}{r['vague_before']:>10}{r['vague_after']:>8}{r['len_after']/r['len_before']:>9.2f}")
