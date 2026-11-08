import os, sys, importlib.util
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置
# EN: noqa: E402  project-wide configuration
# JA: noqa: E402  プロジェクト共通設定
HERE = os.path.dirname(os.path.abspath(__file__))
ALIGN = os.environ.get("CLAUDE_ALIGN_DIR") or str(_rc.path("align_dir"))   # 数据目录：export2/ tasks2/ batches/ results/
# EN: Data directories: export2/ tasks2/ batches/ results/
# JA: データのディレクトリ：export2/ tasks2/ batches/ results/
def _load(name, fname):
    sp = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname)); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
import json,os,sys,collections
_A=_load('A','claude_align_auto.v3.py'); auto,L=_A.auto,_A.L
EXP=ALIGN+'/export2'; OUT=ALIGN+'/tasks2'; os.makedirs(OUT,exist_ok=True)
def compact(it,i): 
    d={'idx':i}; d.update({k:v for k,v in it.items() if v not in ('',None) and k not in('sequence_no','fingerprint')}); return d
meta=[]
for f in sorted(os.listdir(EXP)):
    d=json.load(open(f'{EXP}/{f}',encoding='utf-8')); rs=d['resumes']; langs=[r['resume_languge'] for r in rs]
    a=auto(d); lists={}
    for lst,rows in a.items():
        miss=[k for k,r in enumerate(rows) if any(not r[lg] for lg in langs)]
        if not miss: continue
        lists[lst]=[{'id':f'r{k}','items':{lg:[compact(rs[langs.index(lg)][lst][i],i) for i in rows[k][lg]] for lg in langs if rows[k][lg]}} for k in miss]
    gaps=d['base_text_gaps']
    if not lists and not gaps: continue
    t={'gid':d['group_id'],'langs':langs,'lists':lists,'base_gaps':gaps}
    sz=len(json.dumps(t,ensure_ascii=False)); meta.append((d['group_id'],sz))
    json.dump(t,open(f"{OUT}/{d['group_id']}.json",'w',encoding='utf-8'),ensure_ascii=False)
json.dump(meta,open(ALIGN+'/meta2.json','w'))
print(len(meta),sum(s for _,s in meta))
