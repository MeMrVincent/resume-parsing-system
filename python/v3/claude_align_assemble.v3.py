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
import json,os,sys,collections,re
_A=_load('A','claude_align_auto.v3.py'); auto,L,DATES,ym=_A.auto,_A.L,_A.DATES,_A.ym
C=_load('C','claude_merge_common.v3.py')
EXP=ALIGN+'/export2'
NEUTRAL_FIELDS={'sequence_no','fingerprint','position_start','position_resigned','school_start_ym','school_end_ym','start_ym','end_ym','certificate_time','language_certificate_time','communicate_time','school_degree_rank','annual_salary_min','annual_salary_max','expected_annual_salary_min','expected_annual_salary_max','employment_type','status','expected_employment_type','expected_start_date','company_employees'}
PRIO=['zh','jp','en','de']
def rows_after(rows,langs,merges):
    """merges: [[id,..],...]；返回最终行 [(minid, row)]

    EN: merges: [[id,..],...]; returns the final rows [(minid, row)]

    JA: merges: [[id,..],...]。最終的な行 [(minid, row)] を返す
    """
    by={f'r{k}':r for k,r in enumerate(rows)}
    grp=[]; used=set()
    for g in merges:
        g=[x for x in g if x in by and x not in used]
        if len(g)>=2:
            row={lg:[] for lg in langs}
            for x in g:
                used.add(x)
                for lg in langs: row[lg]=sorted(set(row[lg])|set(by[x][lg]))
            grp.append((g[0],row))
    out=[]
    ing={g0 for g0,_ in grp}
    gm={g0:row for g0,row in grp}
    for k,r in enumerate(rows):
        i=f'r{k}'
        if i in used and i not in ing: continue
        out.append((i,gm.get(i,r)))
    return out
def validate(task,res,d):
    errs=[]; langs=task['langs']; rs=d['resumes']
    a=auto(d)
    for lst,rows in a.items():
        need_ids=[f'r{k}' for k,r in enumerate(rows) if any(not r[lg] for lg in langs)]
        if not need_ids: continue
        rl=(res.get('lists') or {}).get(lst)
        if rl is None: errs.append(f'{lst}: 缺少'); continue
        merges=rl.get('merge') or []
        for g in merges:
            for x in g:
                if x not in need_ids: errs.append(f'{lst}: merge 里的 {x} 不在待处理行里')
        fin=rows_after(rows,langs,merges)
        news=rl.get('new') or {}
        drops=set(rl.get('drop') or [])
        for x in drops:
            if x not in [i for i,_ in fin]: errs.append(f'{lst}: drop 里的 {x} 不是最终行')
        for i,row in fin:
            if i in drops: continue
            miss=[lg for lg in langs if not row[lg]]
            if i not in need_ids and not miss: continue
            if not miss: continue
            nv=news.get(i)
            if nv is None: errs.append(f'{lst}: 行 {i} 缺 {miss} 的译文'); continue
            for lg in miss:
                if lg not in nv or not isinstance(nv[lg],dict): errs.append(f'{lst}: 行 {i} 缺 {lg} 的译文')
                else:
                    for f,v in nv[lg].items():
                        if f not in C.LIST_FIELDS[lst] or f in NEUTRAL_FIELDS or not isinstance(v,str): errs.append(f'{lst}: 行 {i} {lg} 字段 {f} 不该出现或不是字符串')
        for i in news:
            if i in drops: errs.append(f'{lst}: 行 {i} 既 drop 又有 new')
            if i not in [x for x,_ in fin]: errs.append(f'{lst}: new 里的 {i} 不是最终行')
    gaps={(g['lang'],g['field']) for g in task['base_gaps']}
    for lg,fs in (res.get('base') or {}).items():
        for f,v in fs.items():
            if (lg,f) not in gaps: errs.append(f'base {lg}.{f} 不在缺口里')
            elif not isinstance(v,str): errs.append(f'base {lg}.{f} 不是字符串')
    for lg,f in gaps:
        if f not in ((res.get('base') or {}).get(lg) or {}): errs.append(f'base 缺 {lg}.{f}')
    return errs
def sim_item(row,lg,langs,rs,lst):
    LF=C.LIST_FIELDS[lst]
    if row['idx'][lg]:
        it=dict(rs[langs.index(lg)][lst][row['idx'][lg][0]])
    else:
        sl=row['from']; src=rs[langs.index(sl)][lst][row['idx'][sl][0]]
        it={f:src.get(f,'') for f in LF}
        for f,v in (row.get('new',{}).get(lg) or {}).items():
            if f in it and f not in ('sequence_no','fingerprint'): it[f]=v
    it.pop('sequence_no',None); it.pop('fingerprint',None)
    return json.dumps(it,ensure_ascii=False,sort_keys=True)
def dedupe_rows(fr,langs,rs,lst):
    dropped=[r for r in fr if r.get('drop')]; fr=[r for r in fr if not r.get('drop')]
    changed=True
    while changed:
        changed=False
        for lg in langs:
            seen={}
            for k,row in enumerate(fr):
                key=sim_item(row,lg,langs,rs,lst)
                if key in seen:
                    a=fr[seen[key]]
                    for l2 in langs: a['idx'][l2]=sorted(set(a['idx'][l2])|set(row['idx'][l2]))
                    nw={}
                    for l2 in langs:
                        if not a['idx'][l2]:
                            v=(a.get('new') or {}).get(l2) or (row.get('new') or {}).get(l2)
                            nw[l2]=v
                    if nw:
                        a['new']=nw; a['from']=next(x for x in PRIO if x in langs and a['idx'][x])
                    else: a.pop('new',None); a.pop('from',None)
                    del fr[k]; changed=True; break
                seen[key]=k
            if changed: break
    return fr+dropped
def build_item(gid,d,res,idn):
    langs=[r['resume_languge'] for r in d['resumes']]
    a=auto(d); out={'id':idn,'group_id':gid,'src_sha256':d['src_sha256'],'base':res.get('base') or {},'lists':{}}
    for lst,rows in a.items():
        rl=(res.get('lists') or {}).get(lst) or {}
        fin=rows_after(rows,langs,rl.get('merge') or [])
        news=rl.get('new') or {}
        drops=set(rl.get('drop') or [])
        fr=[]
        for i,row in fin:
            r={'idx':{lg:row[lg] for lg in langs}}
            miss=[lg for lg in langs if not row[lg]]
            if i in drops: r['drop']=True
            elif miss:
                r['from']=next(lg for lg in PRIO if lg in langs and row[lg])
                r['new']={lg:news[i][lg] for lg in miss}
            fr.append(r)
        if lst in DATES:
            fs=DATES[lst][0]
            def key(r):
                ks=[ym(d['resumes'][langs.index(lg)][lst][j].get(fs)) for lg in langs for j in r['idx'][lg][:1]]
                ks=[k for k in ks if k]
                return (0,tuple(-ord(c) for c in max(ks))) if ks else (1,())
            fr=[x for _,x in sorted(enumerate(fr),key=lambda t:(key(t[1]),t[0]))]
        fr=dedupe_rows(fr,langs,d['resumes'],lst)
        out['lists'][lst]=fr
    return out
if __name__=='__main__':
    resdir=sys.argv[1]; outp=sys.argv[2]
    items=[]; bad=collections.OrderedDict(); n=0
    allres={}
    for f in sorted(os.listdir(resdir)):
        if f.endswith('.json'): allres.update(json.load(open(f'{resdir}/{f}',encoding='utf-8')))
    for gid,res in sorted(allres.items()):
        d=json.load(open(f'{EXP}/{gid}.json',encoding='utf-8'))
        task=json.load(open(f'{ALIGN}/tasks2/{gid}.json',encoding='utf-8'))
        e=validate(task,res,d)
        if e: bad[gid]=e; continue
        n+=1; items.append(build_item(gid,d,res,f'a{n:04d}'))
    json.dump({'version':'alignment-v1','created':'2026-09-29','items':items},open(outp,'w',encoding='utf-8'),ensure_ascii=False)
    print('ok',len(items),'bad',len(bad)); 
    json.dump(bad,open(outp+'.bad.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
