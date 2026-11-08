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
import json,sys
A=_load('A','claude_align_assemble.v3.py')
b=sys.argv[1]
try: res=json.load(open(f'{ALIGN}/results/{b}.json',encoding='utf-8'))
except Exception as e: print('JSON 无法解析' " / JSON cannot be parsed / JSON を解析できません",e); sys.exit(1)
tasks=[json.loads(l) for l in open(f'{ALIGN}/batches/{b}.jsonl',encoding='utf-8')]
bad=0
for t in tasks:
    g=t['gid']
    if g not in res: print(g,'缺失' " / Missing / 欠落"); bad+=1; continue
    d=json.load(open(f'{A.EXP}/{g}.json',encoding='utf-8'))
    e=A.validate(t,res[g],d)
    if e: bad+=1; print(g,e[:8])
extra=set(res)-{t['gid'] for t in tasks}
if extra: print('多余' " / Extra / 余分",extra)
print('ok' if not bad and not extra else f'不合格 {bad} 份 / {bad} failed / 不合格 {bad} 件')
