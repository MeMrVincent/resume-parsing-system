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
import json,os,sys
meta=json.load(open(ALIGN+'/meta2.json')); meta.sort(key=lambda x:x[0])
os.makedirs(ALIGN+'/batches',exist_ok=True)
cap=int(sys.argv[1]) if len(sys.argv)>1 else 90000
bs=[];cur=[];sz=0
for g,s in meta:
    if cur and (sz+s>cap or len(cur)>=40): bs.append(cur);cur=[];sz=0
    cur.append(g);sz+=s
if cur: bs.append(cur)
for i,b in enumerate(bs):
    with open(f'{ALIGN}/batches/b{i:03d}.jsonl','w',encoding='utf-8') as f:
        for g in b: f.write(open(f'{ALIGN}/tasks2/{g}.json',encoding='utf-8').read().strip()+'\n')
print(len(bs),[len(b) for b in bs][:10])
