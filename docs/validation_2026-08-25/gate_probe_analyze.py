#!/usr/bin/env python3
import json,re,sys,os
sys.path.insert(0,'/Users/1109698/.claude/forks/im-not-ai/skills/humanize-korean/references')
import metrics_v2 as m
src=open('/tmp/fx_in.txt',encoding='utf-8').read()
GATE=("verify_gates.py","verify_change_rate.py")
print(f"{'run':<6}{'도구':>5}{'Bash':>6}{'prepare':>9}{'게이트':>8}{'변경률':>9}  {'가드 초과':>9}")
print("-"*60)
rows=[]
for n in (1,2,3,4,5):
    f=f"/tmp/gate_run{n}.jsonl" if n>1 else "/tmp/gate_trace2.jsonl"
    if not os.path.exists(f): continue
    tools=[];texts=[];done=False
    for line in open(f,encoding='utf-8'):
        try: r=json.loads(line)
        except: continue
        if not isinstance(r,dict): continue
        if r.get('type')=='result':
            done=True
            if r.get('result'): texts.append(str(r['result']))
        msg=r.get('message')
        if not isinstance(msg,dict): continue
        c=msg.get('content')
        if not isinstance(c,list): continue
        for b in c:
            if not isinstance(b,dict): continue
            if b.get('type')=='tool_use':
                inp=b.get('input') if isinstance(b.get('input'),dict) else {}
                tools.append((b.get('name'), str(inp.get('command') or inp.get('file_path') or inp.get('skill') or '')))
            if b.get('type')=='text': texts.append(b.get('text') or '')
    if not done: print(f"run{n}: 미완료 — 제외"); continue
    bash=sum(1 for x,_ in tools if x=="Bash")
    prep=sum(1 for _,d in tools if "prepare_monolith_input" in d)
    gate=sum(1 for _,d in tools if any(g in d for g in GATE))
    out=''.join(texts); hits=re.findall(r"<<<H>>>(.*?)<<</H>>>",out,re.S); mm=max(hits,key=len) if hits else None
    cr=m.change_rate(src, mm.strip()) if mm else None
    over = "예" if (cr is not None and cr>=0.50) else ("아니오" if cr is not None else "—")
    print(f"{'run'+str(n):<6}{len(tools):>5}{bash:>6}{prep:>9}{gate:>8}{(round(cr,3) if cr is not None else '—'):>9}  {over:>9}")
    rows.append({"run":n,"tools":len(tools),"bash":bash,"prepare":prep,"gate":gate,"change_rate":round(cr,4) if cr else None})
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"gate_probe.json"),"w"), ensure_ascii=False, indent=2)
if rows:
    print(f"\n게이트 스크립트 실행: {sum(1 for r in rows if r['gate']>0)}/{len(rows)}회")
    print(f"가드 초과(>=0.50): {sum(1 for r in rows if r['change_rate'] and r['change_rate']>=0.5)}/{len(rows)}회")
