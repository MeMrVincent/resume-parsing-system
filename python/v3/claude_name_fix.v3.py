#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claude_name_fix.v3.py —— 姓名回源核对（在所有模板重新解析之后运行，结果作为最后一层修复副本）。

对每个 JSON，拿当前姓名和它的原文件比：
  * 候选姓名只从原文件取：原文里“姓名：X”标签后的名字，或文件名 / 上级文件夹名里的人名；
    候选名必须是有效中文姓名、首字是常见姓氏，并且在原文正文里出现（繁简、日文字形按同一字比较）。
  * 以下情况才改名：
      1. 当前姓名无效（空、标签词、职位词，如“性别”“日语翻译”“有無既婚”）；
      2. 当前姓名是候选名后面粘了一个字（“江锡峰性”←“江锡峰性别”）；
      3. 当前姓名在原文和文件路径里都找不到，而候选名在原文里有。
  * 其余情况不动；当前名和候选名都在原文里、但不一致的，写进 name_review.csv 供人工核对。
不改原 JSON；输出副本到 <out>/v2、<out>/v1，每处改动写 name_fix_ledger.csv。

EN: claude_name_fix.v3.py -- name verification against the source (runs after all template re-parsing; its result is the last layer of repair copies).

For each JSON, compare the current name with its original file:
  * candidate names are taken only from the original file: the name after the "姓名：X" label in the source, or a personal name in the file name / parent folder name;
    a candidate must be a valid Chinese name whose first character is a common surname, and must appear in the source body (traditional/simplified/Japanese glyphs compared as the same character).
  * the name is changed only in these cases:
      1. the current name is invalid (empty, a label word, a position word, e.g. "性别" (gender), "日语翻译" (Japanese translator), "有無既婚");
      2. the current name is the candidate with one extra character stuck on (e.g. "<name>性" ← "<name>性别");
      3. the current name is found neither in the source nor in the file path, while the candidate is in the source.
  * otherwise nothing changes; when both the current name and the candidate are in the source but differ, they are written to name_review.csv for manual checking.
The original JSON is not changed; copies are output to <out>/v2 and <out>/v1, and every change is written to name_fix_ledger.csv.

JA: claude_name_fix.v3.py —— 氏名を原文と照合する（すべてのテンプレートの再解析の後に実行し、結果は修復コピーの最後の層となる）。

各 JSON について、現在の氏名を元のファイルと比較する：
  * 候補の氏名は元のファイルからだけ取る：原文の「姓名：X」のラベルの後の名前、またはファイル名・親フォルダ名にある人名。
    候補名は有効な中国語の氏名で先頭の字がよくある姓であり、かつ原文の本文に現れること（繁体字・簡体字・日本の字体は同じ字として比較する）。
  * 次の場合だけ氏名を変える：
      1. 現在の氏名が無効（空、ラベルの語、職位の語。例：「性别」（性別）、「日语翻译」（日本語翻訳）、「有無既婚」）。
      2. 現在の氏名が候補名の後ろに 1 文字くっついたもの（例：「<氏名>性」←「<氏名>性别」）。
      3. 現在の氏名が原文にもファイルのパスにも見つからず、候補名は原文にある。
  * それ以外は変えない。現在の名前と候補名がどちらも原文にあるが一致しない場合は、name_review.csv に書いて人手で確認する。
元の JSON は変更しない。コピーを <out>/v2、<out>/v1 に出力し、変更はすべて name_fix_ledger.csv に書く。
"""

import argparse
import collections
import copy
import csv
import json
import re
import sys
from pathlib import Path, PureWindowsPath
import importlib.util

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("claude_merge_common_v3_nf", HERE / "claude_merge_common.v3.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
s = C.s

SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾"
    "夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷"
    "詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农"
    "司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘"
    "池查麻苑迟邝官封谈匡鞠惠荆乐冀郁胥南班储原栗燕楚鄢劳谌奚皮粟冼蔺楼盘满闻位厉伊仝区郜海阚花权强帅屠豆朴盖练廉禹井祖漆巴丰"
    "支卿国狄平计索宣晋相初门云容敬来扈晁芮都普阙浦戈伏鹿薄邸雍辜羊阿乌母裘亓修邰赫杭况那宿鲜印逯隆茹诸战慕危玉银亢嵇公哈湛宾"
    "戎勾茅利於呼居揭干但尉冶斯元束檀衣信展阴昝智幸奉植衡富尧闭由殳贠嵇傅暨邸禇荀靖钮蓬郦满"
)
FIELD_NAME_RE = re.compile(r"(?:姓[ \u3000]*名|氏[ \u3000]*名|名[ \u3000]*前|Name)[ \u3000]*[：:\t][ \u3000\t]*([一-鿿](?:[ \u3000]?[一-鿿]){1,3})(?![一-鿿])")
GLUE_LABEL_RE = re.compile(r"^([一-鿿]{2,4})(性别|性別|年龄|年齢|出生|生年月日)$")
GLUE_CHARS = set("性出印求地的中単单简専专生")
JOB_WORD_RE = re.compile(r"(管理|经理|主管|企划|企画|策划|运营|销售|营业|営業|程序|工程|设计|開発|开发|助理|专员|银行|銀行|金融|证券|保险|"
                         r"行业|事务|翻译|通讯|电子|电气|机械|化工|医药|医疗|物流|贸易|采购|财务|会计|人事|行政|客服|市场|品质|质量|生产|"
                         r"技术|研发|教育|培训|法务|审计|投资|咨询|广告|媒体|外贸|商务|电商|网络|软件|硬件|汽车|数据|供应|日语|英语|日文|英文|信贷|文案|策划|前台|总务|秘书|文秘|国语)")
COMPANY_AFTER_RE = r"[ \u3000]*(有限|公司|株式|集团|集團|银行|銀行|（|\(|科技|电子|電子|工业|工業|贸易|商事|实业|製作|制作|中国|中國)"
STRIP_WORDS_RE = re.compile(r"(的?个人简历|的简历|简历|履歴書|履历书|職務経歴書|职务经历书|推荐报告|候选人|resume|cv)", re.I)
SPLIT_RE = re.compile(r"[\s_\-—–()（）\[\]【】{}<>《》,，、.。;；:：&+#@!！~～'\"“”·•・|/\\]+|\d+|[A-Za-z]+")


def simp(x: str) -> str:
    return re.sub(r"\s+", "", C.to_simplified_name(s(x)))


def simp_keep_breaks(x: str) -> str:
    """简体化，去掉汉字之间的空格（“陈 磊”→“陈磊”），保留其他分隔。

    EN: Convert to simplified characters and remove spaces between Han characters ("<surname> <given name>" → "<surname><given name>"), keeping other separators.

    JA: 簡体字にし、漢字の間の空白を除く（「<姓> <名>」→「<姓><名>」）。その他の区切りは残す。
    """
    y = C.to_simplified_name(s(x))
    return re.sub(r"(?<=[一-鿿])[ \u3000]+(?=[一-鿿])", "", y)


def person_like(n: str) -> bool:
    n = simp(n)
    return (2 <= len(n) <= 4 and re.fullmatch(r"[一-鿿]+", n) is not None and n[0] in SURNAMES
            and C.name_quality(n)[0] == "valid" and not re.search(r"(先生|女士|小姐)$", n) and not JOB_WORD_RE.search(n)
            and not re.search(r"[语文秘]$|^安川$", n))


def filename_candidates(path: str):
    """[(姓名, 强/弱, 出处)]。强：整个文件名就是姓名，或平台文件名里的姓名位置；弱：文件名里的其他词、上级文件夹名。

    EN: [(name, strong/weak, source)]. Strong: the whole file name is the name, or the name position in a platform file name; weak: other words in the file name, the parent folder name.

    JA: [(氏名, 強／弱, 出所)]。強：ファイル名全体が氏名、またはプラットフォームのファイル名の氏名の位置。弱：ファイル名中のその他の語、親フォルダ名。
    """
    p = PureWindowsPath(path)
    out = []
    stem = unicodedata_nfkc(p.stem)
    m = re.match(r"\s*智联招聘_(.+?)_", stem) or re.match(r"\s*51job_(.+?)\(", stem)
    if m:
        out.append((re.sub(r"\s+", "", m.group(1)), "strong", "文件名"))
    liepin = "猎聘" in stem
    b = STRIP_WORDS_RE.sub(" ", stem).strip()
    if re.fullmatch(r"[一-鿿]{1,2}[ \u3000]*[一-鿿]{1,3}", b):  # “包兴龙.docx”“朱 隆荣.docx”“欧阳 亮.docx”
    # EN: Names like "<name>.docx" with or without a space inside (e.g. "<surname> <given name>.docx")
    # JA: 「<氏名>.docx」のような名前（途中に空白があるもの、例：「<姓> <名>.docx」を含む）
        out.append((re.sub(r"\s+", "", b), "strong", "文件名"))
    if not liepin:  # 猎聘文件名里只有“X先生/女士”是人名位置，其余是职位、公司
    # EN: In Liepin file names only "X先生/女士" (Mr/Ms X) is the person-name position; the rest are positions and companies
    # JA: Liepin のファイル名では「X先生／女士」（X さん）だけが人名の位置で、それ以外は職位と会社
        for tok in SPLIT_RE.split(b):
            if tok:
                out.append((tok, "weak", "文件名"))
    out.append((unicodedata_nfkc(p.parent.name).strip(), "weak", "文件夹名"))
    seen, res = set(), []
    for n, strength, where in out:
        if n in seen or not person_like(n):
            continue
        if strength == "weak" and JOB_WORD_RE.search(n):
            continue
        seen.add(n)
        res.append((n, strength, where))
    return res


def unicodedata_nfkc(x):
    import unicodedata
    return unicodedata.normalize("NFKC", x)


ORG_FOLDERS = set()  # 下面放着很多不同人简历的文件夹（整理人、公司、类别），由 main() 按清单统计
# EN: Folders containing résumés of many different people (named after the organiser, company or category), counted by main() from the list
# JA: 多くの異なる人の履歴書を入れたフォルダ（整理した人・会社・分類の名前）。main() が一覧から集計する


def decide(cur: str, text: str, paths):
    """按原文核对姓名。返回 (动作, 新名, 原因, 证据, 候选名)；动作: fix | review | ""。

    EN: Check the name against the source. Returns (action, new name, reason, evidence, candidate names); action: fix | review | "".

    JA: 原文と照合して氏名を確認する。戻り値：(処理, 新しい名前, 理由, 証拠, 候補名)。処理：fix | review | ""。
    """
    text = unicodedata_nfkc(text)
    hay = simp(text)
    path_hay = simp(" ".join(PureWindowsPath(p).name + " " + PureWindowsPath(p).parent.name for p in paths))
    cur = s(cur)
    # 候选：原文“姓名：”标签，其次文件名 / 文件夹名
    # EN: Candidates: the "姓名：" (name:) label in the source, then the file name / folder name
    # JA: 候補：原文の「姓名：」（氏名：）のラベル、次にファイル名・フォルダ名
    cands = []
    strong_best = False
    for m in FIELD_NAME_RE.finditer(text):
        n = re.sub(r"[ \u3000]+[性出男女年]$", "", m.group(1))  # “吴玲玲 性别”
        # EN: "<name> 性别" (name + gender)
        # JA: 「<氏名> 性别」（氏名 + 性別）
        n = re.sub(r"\s+", "", n)
        if person_like(n):
            cands.append((n, "原文姓名栏：" + m.group(0).strip()[:40]))
            strong_best = True
            break
    for p in paths:
        for n, strength, where in filename_candidates(p):
            sn = simp(n)
            pos = hay.find(sn)
            if pos < 0 or any(sn == simp(c) for c, _ in cands):
                continue
            if strength == "weak":
                # 弱候选：须在原文开头 800 字内单独出现（前后不连着别的汉字，姓名通常在最前），且后面不跟公司字样
                # EN: Weak candidates: must appear on their own within the first 800 characters of the source (not joined to other Han characters before or after; names usually come first), and not be followed by company words
                # JA: 弱い候補：原文の先頭 800 文字以内に単独で現れること（前後が他の漢字とつながっていない。氏名は通常最初にある）、かつ後ろに会社を示す語が続かないこと
                head = simp_keep_breaks(text)[:800]
                if not re.search(r"(?<![一-鿿])" + re.escape(sn) + r"(?![一-鿿])", head) or re.search(re.escape(sn) + COMPANY_AFTER_RE, hay):
                    continue
            src = PureWindowsPath(p).name if where == "文件名" else PureWindowsPath(p).parent.name + "\\"
            if not cands and strength == "strong":
                strong_best = True
            cands.append((n, f"{where}：{src[:60]}（原文中出现）"))
    sc0 = simp(cur)
    if (C.name_quality(cur)[0] == "valid" and sc0 and sc0 not in hay
            and any(sc0 == simp(part) and part in ORG_FOLDERS for p in paths for part in PureWindowsPath(p).parts[:-1])):
        # 当前名只是上级文件夹名（整理简历的人按人名建的文件夹，如“胖子\徐仁洁\财务\…”），原文里没有这个名字
        # EN: The current name is just the parent folder name (folders created by the person organising résumés named after people, like "<nickname>\<name>\财务\…"), and the name does not occur in the source
        # JA: 現在の名前が親フォルダの名前にすぎない（履歴書を整理した人が人名でフォルダを作ったもの。例：「<あだ名>\<氏名>\财务\…」）、かつ原文にその名前がない
        if cands:
            return "fix", cands[0][0], "原姓名是文件夹名、原文中没有", cands[0][1], cands[0][0]
        return "fix", "", "原姓名是文件夹名、原文中没有", "文件夹：" + cur, ""
    if not cands:
        return "", "", "", "", ""
    best, evidence = cands[0]
    q = C.name_quality(cur)[0]
    gm = GLUE_LABEL_RE.match(simp(cur))
    reason, new_name = "", best
    sc, sb = simp(cur), simp(best)
    if gm and C.name_quality(gm.group(1))[0] == "valid" and gm.group(1) in hay:
        reason, new_name, evidence = "原姓名粘连了标签", re.sub(r"(性别|性別|年龄|年齢|出生|生年月日)$", "", re.sub(r"\s+", "", cur)), \
            "去掉粘连的“" + gm.group(2) + "”"
    elif q != "valid":
        reason = "原姓名无效"
    elif sc != sb and sc.startswith(sb) and len(sc) == len(sb) + 1 and sc[-1] in GLUE_CHARS:
        reason = "原姓名后面粘了一个字"
    elif sc != sb and re.fullmatch(r"[一-鿿]+", sc) and sc not in path_hay and (
            sc[0] not in SURNAMES or JOB_WORD_RE.search(sc) or re.search(r"(部|课|科|室|学士|硕士|博士|标签|工作|头像|家庭)$", sc)):
        reason = "原姓名不像人名"
    elif (sc != sb and len(sb) == len(sc) + 1 and (sb.endswith(sc) or sb.startswith(sc)) and re.fullmatch(r"[一-鿿]+", sc)
          and sb[-1] not in "男女性"):
        reason = "原姓名缺字"
    elif sc != sb and len(sc) == len(sb) + 1 and sc.endswith(sb) and sc[0] == sb[0]:
        reason = "原姓名姓氏重复"  # “段段志宽”
        # EN: A name with a duplicated first character (e.g. "段段志宽")
        # JA: 先頭の字が重複した氏名（例：「段段志宽」）
    elif (sc != sb and strong_best and re.fullmatch(r"[一-鿿]+", sc) and sc not in path_hay
          and sb not in sc and sc not in sb and not re.search(r"(姓名|氏名|名前)[:：\s]*" + re.escape(sc), simp_keep_breaks(text))):
        # 原文姓名栏 / 整个文件名给出的姓名，而当前名既不在文件名里、也不是原文姓名栏里的名字（多为地名、栏目名）
        # EN: The name given by the source's name field / the whole file name, while the current name is neither in the file name nor the name in the source's name field (mostly place names or section names)
        # JA: 原文の氏名欄やファイル名全体が示す氏名があるのに、現在の名前がファイル名にも原文の氏名欄にもない場合（多くは地名や欄の名前）
        reason = "原姓名不是原文姓名栏/文件名中的姓名"
    elif sc != sb and not any(simp(c) == sc for c, _ in cands) and re.fullmatch(r"[一-鿿]+", sc):
        # 当前名和原文候选名都有效但不一致：不自动改，列出供人工核对
        # EN: Both the current name and the source candidate are valid but differ: do not change automatically; list for manual checking
        # JA: 現在の名前と原文の候補名がどちらも有効だが一致しない：自動では変えず、人手で確認するために一覧にする
        return "review", "", "", evidence, best
    if not reason:
        return "", "", "", "", best
    return "fix", new_name, reason, evidence, best


def main():  # noqa: C901
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-dir", type=Path, required=True)
    ap.add_argument("--text-dir", type=Path, required=True)
    ap.add_argument("--overlay", type=Path, required=True, help="已叠加好的修复副本目录（repair + 各模板重新解析）" " / Directory of already-overlaid repair copies (repair + re-parse of each template) / 重ね済みの修復コピーのディレクトリ（repair + 各テンプレートの再解析）")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    for v in ("v2", "v1"):
        (a.out / v).mkdir(parents=True, exist_ok=True)
    manifest = collections.defaultdict(list)
    for r in csv.DictReader(open(a.pack_dir / "manifest.csv", encoding="utf-8-sig")):
        if r["kind"] == "original" and r["exists"] == "True":
            manifest[r["input_json"]].append((r["pack_key"], r["path"]))
    per_folder = collections.defaultdict(set)
    for input_json, items in manifest.items():
        for _, p in items:
            for part in PureWindowsPath(p).parts[1:-1]:
                per_folder[part].add(PureWindowsPath(input_json).stem.split("_")[0])
    ORG_FOLDERS.update(f for f, names in per_folder.items() if len(names) >= 15)
    ledger, review = [], []
    stats = collections.Counter()
    for input_json, items in manifest.items():
        ver = "v2" if "complete-v2" in input_json else "v1"
        name = PureWindowsPath(input_json).name
        texts = []
        for key, _ in items:
            tp = a.text_dir / "texts" / (Path(key).stem + ".txt")
            if tp.exists():
                texts.append(tp.read_text(encoding="utf-8", errors="ignore"))
        if not texts:
            continue
        stats["files"] += 1
        src_p = a.overlay / ver / name
        if not src_p.is_file():
            src_p = a.pack_dir / "inputs" / ver / name
        if not src_p.is_file():
            continue
        d = json.loads(src_p.read_text(encoding="utf-8"))
        resumes = (d.get("structured_data") or {}).get("resumes") or []
        if not resumes:
            continue
        text = "\n".join(texts)
        paths = [p for _, p in items]
        cur = s((resumes[0].get("base_info") or {}).get("full_name"))
        action, new_name, reason, evidence, best = decide(cur, text, paths)
        if action == "review":
            stats["review"] += 1
            sc = simp(cur)
            review.append({"input_json": input_json, "version": ver, "current_name": cur, "candidate": best, "evidence": evidence,
                           "current_in_text": sc in simp(unicodedata_nfkc(text)),
                           "current_in_path": sc in simp(" ".join(PureWindowsPath(p).name + " " + PureWindowsPath(p).parent.name for p in paths))})
            continue
        if action != "fix":
            continue
        new = copy.deepcopy(d)
        changed = []
        for i, r in enumerate(new["structured_data"]["resumes"]):
            b = r.setdefault("base_info", {})
            old = s(b.get("full_name"))
            if old == cur or C.name_quality(old)[0] != "valid" or GLUE_LABEL_RE.match(simp(old)):
                if old != new_name:
                    b["full_name"] = new_name
                    changed.append(f"resumes[{i}]")
        if not changed:
            continue
        sd = new["structured_data"]
        sd.update(C.build_snapshots(sd["resumes"]))
        new["raw_text"] = C.build_raw_text(sd["resumes"])
        new.setdefault("source_repair", {})["claude_name_fix_v3"] = {"old_name": cur, "new_name": new_name, "reason": reason,
                                                                    "evidence": evidence}
        (a.out / ver / name).write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        stats["fixed"] += 1
        stats[reason] += 1
        ledger.append({"input_json": input_json, "version": ver, "old_name": cur, "new_name": new_name, "reason": reason,
                       "evidence": evidence, "fields": ";".join(changed)})

    def wcsv(fn, rows, head):
        with open(a.out / fn, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else head)
            w.writeheader()
            w.writerows(rows)
    wcsv("name_fix_ledger.csv", ledger, ["input_json"])
    wcsv("name_review.csv", review, ["input_json"])
    (a.out / "name_fix_summary.json").write_text(json.dumps(dict(stats), ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(dict(stats), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
