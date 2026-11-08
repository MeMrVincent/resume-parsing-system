#!/usr/bin/env python3
"""按原文逐条复核后的人工决定（manual_decisions.json），在合并时应用到副本上。

决定文件放在修复副本目录里（--repair-dir 下的 manual_decisions.json），每条决定都带：
  - 定位：group_id（按成员 JSON 的 sha256 算出，成员不变就不变）、简历序号/语言、列表名、
          条目当前各字段的值（match）——全部对得上才应用，对不上就跳过并记账，不会改到别的条目；
  - 动作：set（改字段）/ delete（删条目）/ move（移到别的列表）/ accept（确认不是错误）/ name（定姓名）；
  - 依据：reason 和从原文逐字复制的 evidence、原文路径。
每一处应用或未能应用都写进 cleaning_ledger（前缀 manual:）。

EN: Manual decisions made after item-by-item review against the source (manual_decisions.json), applied to the copies during merging.

The decision file lives in the repair-copy directory (manual_decisions.json under --repair-dir), and each decision carries:
  - location: group_id (computed from the sha256 of member JSON; unchanged as long as the members do not change), résumé index/language, list name,
          and the current values of each field of the entry (match) — applied only if everything matches; otherwise skipped and logged, so other entries are never changed;
  - action: set (change a field) / delete (delete an entry) / move (move to another list) / accept (confirm it is not an error) / name (fix the name);
  - grounds: reason, evidence copied verbatim from the source, and the source path.
Every application, or failure to apply, is written to cleaning_ledger (prefix manual:).

JA: 原文と 1 件ずつ照合した後の人手の判断（manual_decisions.json）を、統合時にコピーに適用する。

判断のファイルは修復コピーのディレクトリ（--repair-dir 配下の manual_decisions.json）に置き、各判断には次を付ける：
  - 位置：group_id（メンバーの JSON の sha256 から計算。メンバーが変わらなければ変わらない）、履歴書の番号・言語、リスト名、
          項目の各フィールドの現在の値（match）— すべて一致した場合だけ適用し、一致しなければスキップして記録するため、他の項目を変えることはない
  - 処理：set（フィールドを変更）/ delete（項目を削除）/ move（別のリストに移動）/ accept（誤りではないと確認）/ name（氏名を決める）
  - 根拠：reason、原文から一字一句写した evidence、原文のパス。
適用した箇所・適用できなかった箇所はすべて cleaning_ledger（接頭辞 manual:）に書く。
"""
import json
import re
from pathlib import Path


def s(v):
    return "" if v is None else str(v)


RANK = {"博士后": "7", "博士": "6", "硕士": "5", "研究生": "5", "MBA": "5", "EMBA": "5", "本科": "4", "学士": "4",
        "大专": "3", "专科": "3", "高中": "2", "中专": "2", "中技": "2", "职高": "2", "初中": "1"}
RANK_EN = [(r"(post-?doc)", "7"), (r"(doctor|ph\.?\s*d)", "6"), (r"(master|mba|m\.\s*sc)", "5"), (r"(bachelor|b\.\s*sc|b\.\s*a\b)", "4"),
           (r"(associate|diploma|college)", "3"), (r"(high school|senior high)", "2")]


def rank_for(dt):
    dt = s(dt)
    for k, v in RANK.items():
        if dt.startswith(k):
            return v
    for pat, v in RANK_EN:
        if re.search(pat, dt, re.I):
            return v
    return ""


class Manual:
    def __init__(self, repair_dir, C):
        self.C = C
        self.items = {}      # gid -> [decision]
        self.names = {}      # gid -> decision
        self.excluded = {}   # gid -> decision（人工确认不是简历，不输出）
        # EN: gid -> decision (manually confirmed as not a résumé; not output)
        # JA: gid -> decision（人手で履歴書ではないと確認したもの。出力しない）
        self.excluded_records = {}   # 输入 JSON 内容 sha256 -> decision（单个输入文件按原文确认不是简历：招聘启事、访谈记录等；其余成员不受影响）
        # EN: Input JSON content sha256 -> decision (a single input file confirmed against the source as not a résumé: job postings, interview records, etc.; other members are unaffected)
        # JA: 入力 JSON の内容の sha256 -> decision（原文を見て履歴書ではないと確認した単一の入力ファイル：求人広告・面談記録など。他のメンバーには影響しない）
        self.loaded = 0
        self.date_fixes = {}   # gid -> [回源核对后的日期修正]
        # EN: gid -> [date corrections after re-reading the source]
        # JA: gid -> [元ファイルを読み直した後の日付修正]
        self.applied_names = set()
        self.accepted = {}   # (gid, id(obj)) -> set(issue types)
        self.translations = {}  # gid -> 译文记录
        # EN: gid -> translation records
        # JA: gid -> 翻訳の記録
        self.alignments = {}   # gid -> 多语言对齐记录（alignments.json）
        # EN: gid -> multilingual alignment records (alignments.json)
        # JA: gid -> 多言語の対応付けの記録（alignments.json）
        ap = Path(repair_dir) / "alignments.json" if repair_dir else None
        if ap and ap.exists():
            for x in json.loads(ap.read_text(encoding="utf-8")).get("items", []):
                self.alignments[x["group_id"]] = x
        self.aligned_base_fields = {}   # (gid, id(base_info)) -> 对齐时补译的基本字段
        # EN: (gid, id(base_info)) -> basic fields filled by translation during alignment
        # JA: (gid, id(base_info)) -> 対応付けの際に翻訳で補った基本フィールド
        self.aligned = {}      # gid -> 应用统计
        # EN: gid -> application statistics
        # JA: gid -> 適用の統計
        tp = Path(repair_dir) / "translations.json" if repair_dir else None
        if tp and tp.exists():
            for x in json.loads(tp.read_text(encoding="utf-8")).get("translations", []):
                self.translations[x["group_id"]] = x
        p = Path(repair_dir) / "manual_decisions.json" if repair_dir else None
        if p and p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            for d in data.get("date_fixes", []):
                self.date_fixes.setdefault(d["group_id"], []).append(d)
            for d in data.get("decisions", []):
                self.loaded += 1
                if d["kind"] == "name":
                    self.names[d["group_id"]] = d
                elif d["kind"] == "exclude":
                    self.excluded[d["group_id"]] = d
                elif d["kind"] == "exclude_record":
                    self.excluded_records[d["content_sha256"]] = d
                else:
                    self.items.setdefault(d["group_id"], []).append(d)

    # ---------------------------------------------------------------- 条目
    # EN: ---------------------------------------------------------------- Entries
    # JA: ---------------------------------------------------------------- 項目
    def _match(self, it, match):
        if not isinstance(it, dict):
            return False
        return all(s(it.get(f))[:600] == s(v) for f, v in match.items())

    def apply_items(self, gid, resumes, provs, log):
        """第一轮决定（编号 i…）先应用；第二轮（编号 r2-…，按第一轮应用后的状态写的）再应用。

        EN: Round-1 decisions (numbered i…) are applied first; round-2 decisions (numbered r2-…, written against the state after round 1 was applied) are applied next.

        JA: 第 1 回の判断（番号 i…）を先に適用し、第 2 回の判断（番号 r2-…。第 1 回を適用した後の状態に基づいて書かれたもの）を次に適用する。
        """
        decs = self.items.get(gid)
        if not decs:
            return
        # 第 1 轮（i…）、第 2 轮（r2-…）、第 3 轮（r3-…）依次应用；后一轮按前一轮应用后的状态写
        # EN: Round 1 (i…), round 2 (r2-…), round 3 (r3-…) are applied in turn; each later round is written against the state after the previous round was applied
        # JA: 第 1 回（i…）・第 2 回（r2-…）・第 3 回（r3-…）を順に適用する。後の回は前の回を適用した後の状態に基づいて書かれている
        rounds = [[d for d in decs if not d["review_id"].startswith(("r2-", "r3-"))],
                  [d for d in decs if d["review_id"].startswith("r2-")],
                  [d for d in decs if d["review_id"].startswith("r3-")]]
        for rd in rounds:
            self._apply_round(rd, gid, resumes, provs, log)

    def _apply_round(self, decs, gid, resumes, provs, log):  # noqa: C901
        if not decs:
            return
        src = f"group:{gid}"
        # 先把所有决定定位到对象上（按“应用前”的状态），再依次应用，避免先删后找错位
        # EN: First locate all decisions on objects (by the "before application" state), then apply them in turn, to avoid misplacement from deleting first and then searching
        # JA: まずすべての判断の対象のオブジェクトを（「適用前」の状態で）特定してから順に適用し、先に削除してから探すことによるずれを防ぐ
        located = []
        for d in decs:
            ri, lst = d["resume_index"], d["list"]
            path = f"resumes[{ri}]" + (f".{lst}" if lst else "")
            if ri >= len(resumes) or s(resumes[ri].get("resume_languge")) != d["resume_lang"]:
                log.append({"source": src, "field_path": path, "action": f"manual:unmatched:简历版本对不上:{d['review_id']}"})
                continue
            res = resumes[ri]
            if lst == "":
                obj = res
            elif lst == "base_info":
                obj = res.get("base_info")
                if not self._match(obj, d["match"]):
                    obj = None
            else:
                cands = [x for x in (res.get(lst) or []) if self._match(x, d["match"])]
                obj = cands[0] if len(cands) >= 1 else None
            if obj is None:
                log.append({"source": src, "field_path": path, "action": f"manual:unmatched:条目对不上（数据已变）:{d['review_id']}"})
                continue
            located.append((d, ri, lst, obj))
        for d, ri, lst, obj in located:
            res, prov = resumes[ri], (provs[ri] if provs else None)
            act = d["action"]
            tag = f"{d['review_id']}|{d['reason']}|原文：{d.get('evidence', '')[:80]}"
            if act == "accept":
                self.accepted.setdefault((gid, id(obj)), set()).update(d.get("issue_types") or [])
                log.append({"source": src, "field_path": f"resumes[{ri}].{lst}", "action": f"manual:accept:{','.join(d.get('issue_types') or [])}:{tag}"})
                continue
            if act == "add" and lst == "":
                si = 0
                if prov is not None:
                    v = next((x for x in (prov.get("base") or {}).values() if isinstance(x, int)), 0)
                    si = v
                for a in d.get("add") or []:
                    to = a["list"]
                    if to not in self.C.LIST_FIELDS:
                        continue
                    new = {f: "" for f in self.C.LIST_FIELDS[to]}
                    for f, v in (a.get("fields") or {}).items():
                        if f in new:
                            new[f] = s(v)
                    if to == "education_list" and new.get("school_degree_type") and not new.get("school_degree_rank"):
                        new["school_degree_rank"] = rank_for(new["school_degree_type"])
                    obj.setdefault(to, []).append(new)
                    if prov is not None and to in prov["lists"]:
                        prov["lists"][to].append([si])
                    if to in ("project_list", "training_list"):
                        for n, it in enumerate(obj[to], 1):
                            it["sequence_no"] = n
                    log.append({"source": src, "field_path": f"resumes[{ri}].{to}",
                                "action": f"manual:add:{json.dumps({f: s(v)[:60] for f, v in new.items() if s(v)}, ensure_ascii=False)[:240]}:{tag}"})
                continue
            if lst in ("", "base_info") and act in ("delete", "move"):
                log.append({"source": src, "field_path": f"resumes[{ri}].{lst}", "action": f"manual:unmatched:不能删除整份简历/基本信息:{d['review_id']}"})
                continue
            if act == "set":
                for f, v in d["set"].items():
                    if f not in obj:
                        continue
                    old = s(obj.get(f))
                    if old == s(v):
                        continue
                    obj[f] = s(v)
                    log.append({"source": src, "field_path": f"resumes[{ri}].{lst}.{f}", "action": f"manual:set:{old[:120]}->{s(v)[:120]}:{tag}"})
                    if f == "school_degree_type":
                        nr = rank_for(v) if v else ""
                        if s(obj.get("school_degree_rank")) != nr:
                            log.append({"source": src, "field_path": f"resumes[{ri}].{lst}.school_degree_rank",
                                        "action": f"manual:set:{s(obj.get('school_degree_rank'))}->{nr}:{d['review_id']}|随学历名称"})
                            obj["school_degree_rank"] = nr
                    if f == "birth_date" and "birth_year" in obj:
                        y = s(v)[:4] if re.match(r"\d{4}", s(v)) else ""
                        if y and s(obj.get("birth_year")) != y:
                            log.append({"source": src, "field_path": f"resumes[{ri}].base_info.birth_year",
                                        "action": f"manual:set:{s(obj.get('birth_year'))}->{y}:{d['review_id']}|随出生日期"})
                            obj["birth_year"] = y
                continue
            items = res.get(lst) or []
            k = next((j for j, x in enumerate(items) if x is obj), None)
            if k is None:
                continue
            if act == "move":
                to = d["to"]
                new = {f: "" for f in self.C.LIST_FIELDS[to]}
                for f, v in (d.get("fields") or {}).items():
                    if f in new:
                        new[f] = s(v)
                if to == "education_list" and new.get("school_degree_type") and not new.get("school_degree_rank"):
                    new["school_degree_rank"] = rank_for(new["school_degree_type"])
                res.setdefault(to, []).append(new)
                if prov is not None and to in prov["lists"] and lst in prov["lists"] and k < len(prov["lists"][lst]):
                    prov["lists"][to].append(prov["lists"][lst][k])
                if to in ("project_list", "training_list"):
                    for n, it in enumerate(res[to], 1):
                        it["sequence_no"] = n
                log.append({"source": src, "field_path": f"resumes[{ri}].{lst}[{k}]",
                            "action": f"manual:move:{lst}->{to}:{json.dumps(d.get('fields'), ensure_ascii=False)[:200]}:{tag}"})
            else:
                log.append({"source": src, "field_path": f"resumes[{ri}].{lst}[{k}]",
                            "action": f"manual:delete:{json.dumps({f: s(v)[:60] for f, v in obj.items() if s(v)}, ensure_ascii=False)[:240]}:{tag}"})
            del items[k]
            if prov is not None and lst in prov["lists"] and k < len(prov["lists"][lst]):
                del prov["lists"][lst][k]
            if lst in ("project_list", "training_list"):
                for n, it in enumerate(items, 1):
                    it["sequence_no"] = n

    # ---------------------------------------------------------------- 姓名
    # EN: ---------------------------------------------------------------- Names
    # JA: ---------------------------------------------------------------- 氏名
    def name_for(self, gid):
        d = self.names.get(gid)
        return d["name"] if d else ""

    def apply_date_fixes(self, gid, resumes, log):
        """回源核对后的日期修正（manual_decisions.json 里的 date_fixes）。在多语言对齐之后、日期统一之前应用：
        对齐记录按各语言版本的内容校验，所以不能在对齐之前改动内容。按名称+原日期匹配条目，匹配不上就跳过并记账。

        EN: Date corrections made after re-reading the source files (`date_fixes` in manual_decisions.json). Applied after
        multi-language alignment and before date unification: alignment records are verified against each language version's
        content, so the content must not change before alignment. Rows are matched by name plus the original dates; a miss is
        skipped and logged.
        JA: 元ファイルを読み直したうえでの日付修正（manual_decisions.json の date_fixes）。多言語整列の後、日付統一の前に適用する。
        整列記録は各言語版の内容で検証されるため、整列の前に内容を変更してはならない。名称と元の日付で行を照合し、
        一致しなければスキップして記録する。
        """
        for d in self.date_fixes.get(gid, []):
            res = next((r for r in resumes if s(r.get("resume_languge")) == d["resume_lang"]), None)
            items = (res or {}).get(d["list"]) or []
            it = next((x for x in items if self._match(x, d["match"])), None)
            if it is None:
                log.append({"source": f"group:{gid}", "field_path": f"{d['resume_lang']}.{d['list']}",
                            "action": f"manual:unmatched:日期修正对不上（数据已变）:{d['review_id']}"})
                continue
            for f, v in d["set"].items():
                old = s(it.get(f))
                if f in it and old != s(v):
                    it[f] = s(v)
                    log.append({"source": f"group:{gid}", "field_path": f"{d['resume_lang']}.{d['list']}.{f}",
                                "action": f"manual:date_fix:{old[:40]}->{s(v)[:40]}:{d['review_id']}|{s(d.get('reason'))[:120]}"})

    def apply_name(self, gid, resumes, log):
        d = self.names.get(gid)
        if not d:
            return ""
        name = d["name"]
        simp = self.C.to_simplified_name(name) if re.search(r"[一-鿿]", name) else name
        for i, res in enumerate(resumes):
            b = res.get("base_info") or {}
            lang = s(res.get("resume_languge"))
            want = simp if lang == "zh" else (name if self.C.name_quality(s(b.get("full_name")))[0] != "valid" else "")
            if want and s(b.get("full_name")) != want:
                log.append({"source": f"group:{gid}", "field_path": f"resumes[{i}].base_info.full_name",
                            "action": f"manual:name:{s(b.get('full_name'))}->{want}:{d['review_id']}|{d['reason']}|原文：{d.get('evidence', '')[:80]}"})
                b["full_name"] = want
        self.applied_names.add(gid)
        return simp

    def adjust_issue(self, gid, res_obj_for_path, iss):
        """人工确认过的问题降为 low，并注明。

        EN: Issues confirmed manually are downgraded to low, with a note.

        JA: 人手で確認した問題は low に下げ、注記を付ける。
        """
        t = iss["issue_type"]
        if gid in self.applied_names and t.startswith("name_"):
            iss["severity"] = "low"
            iss["note"] = (s(iss.get("note")) + " 人工按原文确定了姓名").strip()
            return
        obj = res_obj_for_path(iss["field_path"])
        if obj is not None and iss["field_path"].rsplit(".", 1)[-1] in self.aligned_base_fields.get((gid, id(obj)), set()):
            iss["severity"] = "low"
            iss["note"] = (s(iss.get("note")) + " 多语言对齐补出的译文，照搬另一语言版本的原样内容").strip()
            return
        acc = self.accepted.get((gid, id(obj)), set()) if obj is not None else set()
        if obj is not None and (t in acc or "*" in acc):
            iss["severity"] = "low"
            iss["note"] = (s(iss.get("note")) + " 人工核对原文：不是错误").strip()


    # ---------------------------------------------------------------- 多语言对齐
    # EN: ---------------------------------------------------------------- Multilingual alignment
    # JA: ---------------------------------------------------------------- 多言語の対応付け
    BASE_NEUTRAL = ("age", "birth_date", "birth_year", "height_cm", "weight_kg", "postal_code", "platform_resume_id", "platform_from")
    BASE_NEUTRAL_CN = ("gender", "marital_status", "children_status", "political_status", "nationality")  # 目标是中/日文版时，这些取值本来就是中文常量，直接互补
    # EN: When the target is the Chinese/Japanese version, these values are Chinese constants anyway; complement them directly
    # JA: 対象が中国語・日本語版の場合、これらの値はもともと中国語の定数なので、そのまま相互に補う
    NO_COPY = ("sequence_no", "fingerprint")

    @staticmethod
    def resume_sha(res):
        import hashlib
        return hashlib.sha256(json.dumps(res, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def base_gaps(self, resumes):
        """各语言版本之间，某个基本字段这一版为空、别的版本有值：返回 (需要翻译的缺口, 可直接互补的缺口数)。用于导出与应用。

        EN: Between language versions, when a basic field is empty in one version but has a value in another: returns (gaps needing translation, number of gaps that can be complemented directly). Used for export and application.

        JA: 言語版の間で、ある基本フィールドがこの版では空で別の版には値がある場合：(翻訳が必要な欠け, 直接相互に補える欠けの数) を返す。出力と適用に使う。
        """
        text, neutral = [], []
        for i, r in enumerate(resumes):
            b = r.get("base_info") or {}
            lang = s(r.get("resume_languge"))
            for f in b:
                if s(b.get(f)) or f in ("full_name", "phone", "email"):
                    continue
                src = next(((j, s((o.get("base_info") or {}).get(f))) for j, o in enumerate(resumes) if j != i and s((o.get("base_info") or {}).get(f))), None)
                if not src:
                    continue
                if f in self.BASE_NEUTRAL or (f in self.BASE_NEUTRAL_CN and lang in ("zh", "jp") and re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", src[1])):
                    neutral.append((i, f, src[1]))
                else:
                    text.append({"lang": lang, "field": f, "from": s(resumes[src[0]].get("resume_languge")), "value": src[1]})
        return text, neutral

    def apply_alignment(self, gid, resumes, provs, log):
        """多语言简历：各语言版本的基本字段、各个列表逐项对齐（去重、缺的补上）。
        alignments.json 的记录按各版本内容的 sha256 核对，对不上就跳过并记账。

        EN: Multilingual résumés: align the basic fields and each list item by item across language versions (dedup, fill what is missing).
        Records in alignments.json are checked against the sha256 of each version's content; if they do not match they are skipped and logged.

        JA: 多言語の履歴書：各言語版の基本フィールドと各リストを 1 項目ずつ対応付ける（重複を除き、欠けているものを補う）。
        alignments.json の記録は各版の内容の sha256 で照合し、一致しなければスキップして記録する。
        """
        x = self.alignments.get(gid)
        if not x or len(resumes) < 2:
            return False
        langs = [s(r.get("resume_languge")) for r in resumes]
        want = x["src_sha256"]
        if sorted(want) != sorted(langs) or any(self.resume_sha(r) != want[l] for r, l in zip(resumes, langs)):
            log.append({"source": f"group:{gid}", "field_path": "resumes", "action": f"alignment:unmatched:各语言版本内容已变，未应用:{x['id']}"})
            return False
        lidx = {l: i for i, l in enumerate(langs)}
        n_base = n_new = n_merge = n_drop = 0
        # 基本字段：可直接互补的先补，需要翻译的按记录补
        # EN: Basic fields: fill those that can complement each other directly first; those needing translation are filled per record
        # JA: 基本フィールド：直接相互に補えるものを先に補い、翻訳が必要なものは記録に従って補う
        _text, neutral = self.base_gaps(resumes)
        for i, f, v in neutral:
            resumes[i]["base_info"][f] = v
            n_base += 1
        for l, fields in (x.get("base") or {}).items():
            b = resumes[lidx[l]]["base_info"]
            for f, v in fields.items():
                if not s(b.get(f)) and s(v):
                    b[f] = s(v)
                    self.aligned_base_fields.setdefault((gid, id(b)), set()).add(f)
                    n_base += 1
        # 列表
        # EN: Lists
        # JA: リスト
        for lst, rows in (x.get("lists") or {}).items():
            LF = self.C.LIST_FIELDS[lst]
            for l in langs:
                seen = sorted(i for row in rows for i in row["idx"].get(l, []))
                if seen != list(range(len(resumes[lidx[l]].get(lst) or []))):
                    log.append({"source": f"group:{gid}", "field_path": f"{lst}", "action": f"alignment:unmatched:{lst} 的索引没有恰好覆盖 {l} 版的每一条，整份对齐未应用:{x['id']}"})
                    return False
        for lst, rows in (x.get("lists") or {}).items():
            LF = self.C.LIST_FIELDS[lst]
            olds = {l: list(resumes[lidx[l]].get(lst) or []) for l in langs}
            oprov = {l: list((provs[lidx[l]]["lists"].get(lst) or [])) for l in langs} if provs is not None else {}
            for l in langs:
                new_items, new_prov = [], []
                for row in rows:
                    if row.get("drop"):
                        n_drop += 1
                        continue
                    idxs = row["idx"].get(l, [])
                    if idxs:
                        it = olds[l][idxs[0]]
                        for j in idxs[1:]:
                            for f in LF:
                                if f not in self.NO_COPY and not s(it.get(f)) and s(olds[l][j].get(f)):
                                    it[f] = olds[l][j][f]
                            n_merge += 1
                        new_items.append(it)
                        new_prov.append(oprov[l][idxs[0]] if oprov and idxs[0] < len(oprov[l]) else [0])
                    else:
                        sl = row["from"]
                        srcs = row["idx"][sl]
                        src = olds[sl][srcs[0]]
                        it = {f: src.get(f, "") for f in LF}
                        for f, v in (row.get("new", {}).get(l) or {}).items():
                            if f in it and f not in self.NO_COPY:
                                it[f] = s(v)
                        self.accepted[(gid, id(it))] = {"*"}   # 译文条目照搬来源条目的原样内容（含来源里的解析残留），质量检查放行；审计按 alignments.json 的译文内容核对
                        # EN: Translated entries copy the source entry's content as-is (including parse leftovers in the source), and the quality check lets them through; the audit checks against the translated content in alignments.json
                        # JA: 訳文の項目は元の項目の内容をそのまま写す（元にある解析の残骸も含む）ため、品質チェックは通す。監査は alignments.json の訳文の内容と照合する
                        new_items.append(it)
                        new_prov.append(oprov[sl][srcs[0]] if oprov and srcs[0] < len(oprov[sl]) else [0])
                        n_new += 1
                if lst in ("project_list", "training_list"):
                    for k, it in enumerate(new_items, 1):
                        it["sequence_no"] = k
                        if "fingerprint" in it:
                            it["fingerprint"] = ""
                resumes[lidx[l]][lst] = new_items
                if provs is not None:
                    provs[lidx[l]]["lists"][lst] = new_prov
        self.aligned[gid] = {"base": n_base, "new_items": n_new, "merged_duplicates": n_merge, "dropped": n_drop}
        log.append({"source": f"group:{gid}", "field_path": "resumes", "action": f"alignment:多语言对齐：补基本字段 {n_base} 个、补列表条目 {n_new} 条、合并重复 {n_merge} 条、丢弃残留行 {n_drop} 条(按语言版本计):{x['id']}"})
        return True

    # ---------------------------------------------------------------- 翻译
    # EN: ---------------------------------------------------------------- Translation
    # JA: ---------------------------------------------------------------- 翻訳
    def apply_translation(self, gid, resumes, provs, log):
        """没有中文版的人：把外文版复制一份放到 resumes[0]，内容换成中文译文。
        只有外文版内容与翻译时完全一致（sha256 相同）才应用，否则跳过并记账。返回源语言或空。

        EN: People without a Chinese version: copy the foreign version into resumes[0] and replace its content with the Chinese translation.
        Applied only if the foreign content is exactly the same as at translation time (same sha256); otherwise skipped and logged. Returns the source language or empty.

        JA: 中国語版がない人：外国語版を 1 つコピーして resumes[0] に置き、内容を中国語訳に置き換える。
        外国語版の内容が翻訳時と完全に同じ（sha256 が同じ）場合だけ適用し、そうでなければスキップして記録する。元の言語か空を返す。
        """
        import hashlib
        x = self.translations.get(gid)
        if not x or any(s(r.get("resume_languge")) == "zh" for r in resumes):
            return ""
        for k, r in enumerate(resumes):
            if s(r.get("resume_languge")) != x["source_lang"]:
                continue
            sha = hashlib.sha256(json.dumps(r, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            if sha != x["source_sha256"]:
                log.append({"source": f"group:{gid}", "field_path": f"resumes[{k}]", "action": f"translation:unmatched:外文版内容已变，未应用译文:{x['id']}"})
                return ""
            zh = json.loads(json.dumps(x["resume_zh"], ensure_ascii=False))
            zh["resume_languge"] = "zh"
            resumes.insert(0, zh)
            if provs is not None:
                provs.insert(0, json.loads(json.dumps(provs[k])))
            log.append({"source": f"group:{gid}", "field_path": "resumes[0]",
                        "action": f"translation:{x['source_lang']}->zh:由 resumes[{k}]（{x['source_lang']}）复制并翻译为中文，放在 resumes[0]:{x['id']}"})
            # 译成中文后，原文里不同写法的条目可能变得完全相同（如 日本語 / 日語 都译作 日语）：只保留第一条
            # EN: After translation into Chinese, entries written differently in the original may become identical (e.g. 日本語 / 日語 both translate to 日语): keep only the first
            # JA: 中国語に訳した後、原文で書き方の異なる項目がまったく同じになることがある（例：日本語／日語 がどちらも 日语 になる）。最初のものだけを残す
            for lst, items in list(zh.items()):
                if not isinstance(items, list):
                    continue
                seen, keep = [], []
                for j, it in enumerate(items):
                    key = json.dumps({a: b for a, b in it.items() if a != "sequence_no"}, ensure_ascii=False, sort_keys=True) if isinstance(it, dict) else str(it)
                    if key in seen:
                        log.append({"source": f"group:{gid}", "field_path": f"resumes[0].{lst}[{j}]", "action": "translation:译文与前一条完全相同，删除"})
                        continue
                    seen.append(key)
                    keep.append(j)
                if len(keep) != len(items):
                    zh[lst] = [items[j] for j in keep]
                    if provs is not None and lst in provs[0].get("lists", {}):
                        pl = provs[0]["lists"][lst]
                        provs[0]["lists"][lst] = [pl[j] for j in keep if j < len(pl)]
                    if lst in ("project_list", "training_list"):
                        for n, it in enumerate(zh[lst], 1):
                            it["sequence_no"] = n
            return x["source_lang"]
        return ""
