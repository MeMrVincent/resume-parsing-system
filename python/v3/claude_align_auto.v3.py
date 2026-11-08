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
import json,os,sys,re,collections
import importlib
C=importlib.import_module('claude_merge_common.v3'.replace('.v3','')) if False else None
C=_load('C','claude_merge_common.v3.py')
L=['work_experiences','education_list','certificate_list','language_list','skills_list','project_list','training_list','expected_list','communication_list']
NAME={'work_experiences':'company_name','education_list':'school_name','certificate_list':'certificate_name','language_list':'language_name','skills_list':'skill_name','project_list':'project_name','training_list':'training_name','communication_list':'communicate_content'}
DATES={'work_experiences':('position_start','position_resigned'),'education_list':('school_start_ym','school_end_ym'),'project_list':('start_ym','end_ym'),'training_list':('start_ym','end_ym')}
def s(v): return '' if v is None else str(v)
def nn(t):
    t=re.sub(r'[\s\W_]+','',s(t).lower()); return t
def ym(v): 
    k=C.ym_key(v); return k or ''
def compat_dates(a,b,lst):
    if lst not in DATES: return True
    fs,fe=DATES[lst]; sa,ea,sb,eb=ym(a.get(fs)),ym(a.get(fe)),ym(b.get(fs)),ym(b.get(fe))
    if not (sa or ea) or not (sb or eb): return True
    return (sa and sa==sb) or (ea and ea==eb)
def same_item(a,b,lst):
    if lst=='expected_list':
        ka={k:v for k,v in a.items() if s(v)}; kb={k:v for k,v in b.items() if s(v)}
        small,big=(ka,kb) if len(ka)<=len(kb) else (kb,ka)
        return bool(small) and all(big.get(k)==v for k,v in small.items())
    na,nb=nn(a.get(NAME[lst])),nn(b.get(NAME[lst]))
    if not na or not nb: return False
    if not (na==nb or (min(len(na),len(nb))>=4 and (na in nb or nb in na))): return False
    return compat_dates(a,b,lst)
def cluster(items,lst):
    cl=[]
    for i,it in enumerate(items):
        for c in cl:
            if any(same_item(items[j],it,lst) for j in c): c.append(i); break
        else: cl.append([i])
    return cl
def dkey(items,c,lst,which):
    if lst not in DATES: return ''
    f=DATES[lst][which]
    for i in c:
        k=ym(items[i].get(f))
        if k: return k
    return ''
def match(lst,piv,pi,oth,oi):
    """piv/oth: clusters（索引列表）；返回 {pivot簇号: 其他语言簇号}

    EN: piv/oth: clusters (lists of indexes); returns {pivot cluster number: other-language cluster number}

    JA: piv/oth：クラスター（番号のリスト）。{pivot のクラスター番号: 他の言語のクラスター番号} を返す
    """
    res={}; used=set()
    def try_pass(keyf):
        for a,ca in enumerate(piv):
            if a in res: continue
            ka=keyf(pi,ca)
            if not ka: continue
            cands=[b for b,cb in enumerate(oth) if b not in used and keyf(oi,cb)==ka]
            if len(cands)==1: res[a]=cands[0]; used.add(cands[0])
    if lst in DATES:
        try_pass(lambda it,c:(dkey(it,c,lst,0),dkey(it,c,lst,1)) if dkey(it,c,lst,0) and dkey(it,c,lst,1) else '')
        try_pass(lambda it,c:dkey(it,c,lst,0))
        try_pass(lambda it,c:dkey(it,c,lst,1))
    elif lst=='expected_list':
        pass
    else:
        try_pass(lambda it,c:nn(it[c[0]].get(NAME[lst])))
    return res
def auto(d):
    rs=d['resumes']; langs=[r['resume_languge'] for r in rs]; out={}
    for lst in L:
        items={lg:(r.get(lst) or []) for lg,r in zip(langs,rs)}
        if sum(len(v) for v in items.values())==0: continue
        cls={lg:cluster(items[lg],lst) for lg in langs}
        # pivot = 条目最多的语言（同数取靠前）
        # EN: pivot = the language with the most entries (on a tie, the earlier one)
        # JA: pivot = 項目が最も多い言語（同数なら前のもの）
        pv=max(langs,key=lambda lg:(len(cls[lg]),-langs.index(lg)))
        rows=[{lg:([] ) for lg in langs} for _ in cls[pv]]
        for k,c in enumerate(cls[pv]): rows[k][pv]=c
        left={}
        for lg in langs:
            if lg==pv: continue
            m=match(lst,cls[pv],items[pv],cls[lg],items[lg])
            for a,b in m.items(): rows[a][lg]=cls[lg][b]
            left[lg]=[cls[lg][b] for b in range(len(cls[lg])) if b not in m.values()]
        # 非 pivot 语言之间的剩余簇：不再自动配对，留给人工/翻译
        # EN: Remaining clusters between non-pivot languages: no longer paired automatically; left for manual work / translation
        # JA: pivot 以外の言語の間に残ったクラスター：自動では対応付けず、人手・翻訳に任せる
        for lg,cs in left.items():
            for c in cs:
                r={x:[] for x in langs}; r[lg]=c; rows.append(r)
        out[lst]=rows
    return out
if __name__=='__main__':
    EXP=ALIGN+'/export2'
    tot=collections.Counter(); chars=0; nfile=0; rows_all={}
    for f in sorted(os.listdir(EXP)):
        d=json.load(open(f'{EXP}/{f}',encoding='utf-8')); langs=[r['resume_languge'] for r in d['resumes']]
        a=auto(d); rows_all[d['group_id']]=a
        need=False
        for lst,rows in a.items():
            for r in rows:
                miss=[lg for lg in langs if not r[lg]]
                if miss:
                    tot['rows_missing']+=1; need=True
                    for lg in langs:
                        for i in r[lg]: chars+=len(json.dumps(d['resumes'][langs.index(lg)][lst][i],ensure_ascii=False))
                tot['rows']+=1
        nfile+=need
    print(tot,nfile,chars)
    json.dump(rows_all,open(ALIGN+'/auto_rows.json','w'))
