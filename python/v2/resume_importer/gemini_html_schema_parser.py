from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from .structured_parser import candidate_name_hint_from_path
from .parser import ResumeParser

# 按 Rank 从高到低降序排列，确保优先匹配高学历（硕士 5 优先于 大学 4）
# EN: Sort by Rank from high to low so higher degrees match first (master's 5 before university 4)
# JA: Rank の高い順に並べ、高い学歴が先にマッチするようにする（修士 5 を大学 4 より優先）
EDUCATION_RANKS_ORDERED = [
    ("7", ["博士后"]),
    ("6", ["博士"]),
    ("5", ["硕士", "研究生", "修士", "大学院", "院生"]),
    ("4", ["本科", "学士", "大学", "大卒", "専門", "本科卒"]),
    ("3", ["大专", "专科", "短大", "専門学校", "高职"]),
    ("1", ["高中", "中专", "职高", "中学"])
]

EDUCATION_TYPE_MAP = {
    "7": "全日制研究生",
    "6": "全日制研究生",
    "5": "全日制研究生",
    "4": "全日制大学",
    "3": "全日制大专",
    "1": "全日制高中"
}

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

class GeminiHtmlSchemaParser:
    """Gemini 基于 Word 导出 HTML DOM 的结构化解析器。

    该文件是 Gemini 版本的隔离副本，正式跑批只引用本类，不修改原始
    ``gemini_html_schema_parser.py``，便于两套规则并行对比。

    EN: Gemini's structured parser based on the HTML DOM exported from Word.

    This file is an isolated copy of the Gemini version; formal batch runs reference only this class and do not modify the original
    ``gemini_html_schema_parser.py``, so the two rule sets can be compared side by side.

    JA: Word からエクスポートした HTML DOM に基づく Gemini の構造化パーサー。

    このファイルは Gemini 版の分離コピーで、正式なバッチ実行ではこのクラスだけを参照し、元の
    ``gemini_html_schema_parser.py`` は変更しない。2 つのルールを並べて比較しやすくするため。
    """

    def _html_to_clean_text(self, html_content: str) -> str:
        """使用 BeautifulSoup 将 HTML DOM 节点转化为换行清晰、语义完备的文本块（彻底剥离声明杂质）

        EN: Use BeautifulSoup to turn HTML DOM nodes into text blocks with clear line breaks and complete semantics (fully stripping disclaimer noise)

        JA: BeautifulSoup で HTML DOM ノードを、改行が明確で意味の揃ったテキストブロックに変換する（声明文などの不要部分を完全に除去）
        """
        if not html_content: return ""

        # 彻底剥离猎聘/智联网声明与底部的操作时间文本块（避免进入正文）
        # EN: Completely strip the Liepin/Zhaopin disclaimers and the operation-time text block at the bottom (keep them out of the body)
        # JA: Liepin／Zhaopin の声明文と末尾の操作日時のテキストブロックを完全に除去する（本文に入れない）
        html_content = re.sub(r"声明：[\s\S]*?(?:操作人[^\n]*|\n|$)", "", html_content)

        if HAS_BS4 and ("<html" in html_content.lower() or "<table" in html_content.lower() or "<div" in html_content.lower()):
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                # 剔除 style / script / meta
                # EN: Remove style / script / meta
                # JA: style / script / meta を除去する
                for tag in soup(["style", "script", "meta", "link"]):
                    tag.decompose()
                
                # 为表格 cell 加上分割符，方便按列抓取
                # EN: Add separators to table cells to make column-wise extraction easier
                # JA: 列単位で取り出しやすいよう、表のセルに区切り文字を付ける
                for td in soup.find_all(["td", "th"]):
                    td.append("  ")
                for tr in soup.find_all("tr"):
                    tr.append("\n")
                for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "li", "br"]):
                    p.append("\n")
                    
                text = soup.get_text()
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                return "\n".join(lines)
            except Exception:
                pass
        # 降级正则剥离 HTML 标签
        # EN: Fallback: strip HTML tags with regular expressions
        # JA: 代替：正規表現で HTML タグを除去する
        clean = re.sub(r"<style[\s\S]*?</style>", "", html_content, flags=re.IGNORECASE)
        clean = re.sub(r"<script[\s\S]*?</script>", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", "\n", clean)
        lines = [l.strip() for l in clean.splitlines() if l.strip()]
        return "\n".join(lines)

    def parse(self, raw_text: str, filename: str = "", source_path: str = "") -> dict[str, Any]:
        raw_html = raw_text or ""
        raw = raw_text or ""
        # 0. 如果传入的是 HTML 内容，先进行 HTML DOM 节点清洗
        # EN: 0. If HTML content is passed in, clean the HTML DOM nodes first
        # JA: 0. HTML の内容が渡された場合は、まず HTML DOM ノードをクレンジングする
        if "<html" in raw.lower() or "<table" in raw.lower() or "<div" in raw.lower() or "<body" in raw.lower():
            raw = self._html_to_clean_text(raw)
            
        # 1. 规范化所有日期格式（强力支持斜杠/、全角／、长音符–—～、波浪号~~ 及 日文'から今迄'）
        # EN: 1. Normalise all date formats (robust support for slash /, full-width ／, dashes –—～, tildes ~~ and Japanese 'から今迄')
        # JA: 1. すべての日付形式を正規化する（スラッシュ /、全角 ／、ダッシュ –—～、波線 ~~、日本語の「から今迄」に確実に対応）
        text = re.sub(r"((?:19|20)\d{2})\s*[-./年/\ufffd／]\s*(0?[1-9]|1[0-2])\s*(?:月|日)?\s*[-—–~∼～\u2014\u2013\uff0d¡£`\-./\ufffd~〜ー]{1,4}\s*((?:19|20)\d{2})\s*[-./年/\ufffd／]\s*(0?[1-9]|1[0-2])", 
                      lambda m: f"{m.group(1)}.{int(m.group(2)):02d} - {m.group(3)}.{int(m.group(4)):02d}", raw)
        text = re.sub(r"((?:19|20)\d{2})\s*[-./年/\ufffd／]\s*(0?[1-9]|1[0-2])\s*(?:月|日)?\s*(?:[-—–~∼～\u2014\u2013\uff0d¡£`\-./\ufffd~〜ー]{1,4}|から)\s*(至今|现在|目前|Present|今迄|現在)", 
                      lambda m: f"{m.group(1)}.{int(m.group(2)):02d} - 至今", text)

        # 检查是否同时存在中文与日文/英文双语版块
        # EN: Check whether both Chinese and Japanese/English bilingual sections exist
        # JA: 中国語と日本語・英語の両方の言語ブロックが存在するかをチェックする
        lang_blocks = self._split_language_blocks(text)
        
        is_pure_foreign = (len(lang_blocks) == 1 and lang_blocks[0][0] in ("jp", "en"))
        
        resumes = []
        
        if is_pure_foreign:
            # 纯外文简历规范处理：
            # EN: Standard handling of foreign-language-only résumés:
            # JA: 外国語のみの履歴書の標準処理：
            f_lang, f_text = lang_blocks[0]
            f_res = self._parse_single_block(f_text, f_lang, filename, source_path, raw_html=raw_html)
            
            zh_placeholder = {
                "resume_languge": "zh",
                "base_info": {
                    "full_name": "", "gender": "", "age": "", "birth_date": "",
                    "birth_year": "", "marital_status": "", "children_status": "",
                    "political_status": "", "height_cm": "", "weight_kg": "",
                    "household_registration": "", "address": "", "postal_code": "",
                    "platform_from": f_res["base_info"]["platform_from"],
                    "platform_resume_id": "",
                    "phone": f_res["base_info"]["phone"],
                    "email": f_res["base_info"]["email"],
                    "city": "", "nationality": "", "pr": ""
                },
                "expected_info": [],
                "work_experiences": [],
                "education_list": [],
                "certificate_info": [],
                "language_info": [],
                "skills_info": []
            }
            resumes.append(zh_placeholder)
            resumes.append(f_res)
            
            empty_base = {
                "full_name": "", "gender": "", "age": "", "birth_date": "",
                "birth_year": "", "marital_status": "", "children_status": "",
                "political_status": "", "height_cm": "", "weight_kg": "",
                "household_registration": "", "address": "", "postal_code": "",
                "platform_from": f_res["base_info"]["platform_from"],
                "platform_resume_id": "",
                "phone": f_res["base_info"]["phone"],
                "email": f_res["base_info"]["email"],
                "city": "", "nationality": "", "pr": ""
            }
            return {
                "base_info": empty_base,
                "expected_info": [],
                "current_info": self._build_empty_current_info(),
                "education_info": self._build_empty_education_info(),
                "certificate_info": [],
                "language_info": [],
                "skills_info": [],
                "resumes": resumes
            }
        else:
            # 双语简历或中文简历处理
            # EN: Handling of bilingual or Chinese résumés
            # JA: バイリンガルまたは中国語の履歴書の処理
            parsed_blocks = []
            for l_type, b_text in lang_blocks:
                sub_res = self._parse_single_block(b_text, l_type, filename, source_path, raw_html=raw_html)
                resumes.append(sub_res)
                parsed_blocks.append((l_type, sub_res))

            zh_block = next((b for l_type, b in parsed_blocks if l_type == "zh"), parsed_blocks[0][1] if parsed_blocks else {})
            
            base_info = zh_block.get("base_info", {})
            expected_info = zh_block.get("expected_info", [])
            work_experiences = zh_block.get("work_experiences", [])
            education_list = zh_block.get("education_list", [])
            
            current_info = self._build_current_info(work_experiences)
            education_info = self._build_highest_education_info(education_list)
            
            return {
                "base_info": base_info,
                "expected_info": expected_info,
                "current_info": current_info,
                "education_info": education_info,
                "certificate_info": zh_block.get("certificate_info", []),
                "language_info": zh_block.get("language_info", []),
                "skills_info": zh_block.get("skills_info", []),
                "resumes": resumes
            }

    def _split_language_blocks(self, text: str) -> list[tuple[str, str]]:
        """智能拆分中文与日文/英文双语板块

        EN: Smartly split Chinese and Japanese/English bilingual blocks

        JA: 中国語と日本語・英語の言語ブロックを賢く分割する
        """
        m_jp = re.search(r"\n\s*(?:日语简历|日語简历|日語|日本語|履歴書|職務経歴書)", text)
        m_en = re.search(r"\n\s*(?:英文简历|English Resume|Curriculum Vitae)", text, re.IGNORECASE)
        
        blocks = []
        if m_jp and m_jp.start() > 50:
            zh_text = text[:m_jp.start()].strip()
            jp_text = text[m_jp.start():].strip()
            blocks.append(("zh", zh_text))
            blocks.append(("jp", jp_text))
        elif m_en and m_en.start() > 50:
            zh_text = text[:m_en.start()].strip()
            en_text = text[m_en.start():].strip()
            blocks.append(("zh", zh_text))
            blocks.append(("en", en_text))
        else:
            lang = self._detect_language(text, "")
            blocks.append((lang, text))
        return blocks

    def _detect_language(self, text: str, filename: str) -> str:
        kana_count = len(re.findall(r"[\u3040-\u30ff]", text))
        if kana_count >= 5 or re.search(r"履歴書|職務経歴書|生年月日|学歴|職歴|志望|希望職種|個人情報|キーワード|卒業学校|仕事内容|です|ました", text):
            return "jp"
        elif len(re.findall(r"[\u4e00-\u9fff]", text)) > 20:
            return "zh"
        elif re.search(r"\b(Resume|CV|Curriculum Vitae|Experience|Education)\b", text, re.IGNORECASE):
            return "en"
        return "zh"

    def _parse_single_block(self, text: str, lang: str, filename: str, source_path: str, raw_html: str = "") -> dict[str, Any]:
        full_name = self._extract_name(text, filename, source_path, raw_html=raw_html)
        gender = self._extract_gender(text)
        birth_date, birth_year, age = self._extract_birth(text)
        marital, children = self._extract_marital_and_children(text)
        phone = self._extract_phone(text)
        email = self._extract_email(text)
        city, address = self._extract_city_and_address(text)
        pr = self._extract_pr(text)
        platform_from = self._detect_platform(text, filename)
        
        height_cm = self._extract_pattern(text, r"(?:身\s*高|身長)\s*[:：\t\s\n]*(\d{2,3})(?:cm)?")
        weight_kg = self._extract_pattern(text, r"(?:体\s*重|体重)\s*[:：\t\s\n]*(\d{2,3})(?:kg)?")
        h_reg = self._extract_pattern(text, r"(?:户口所在地|户籍|籍贯|戸籍|出身地)\s*[:：\t\s\n]*([^\n\t]+)")
        
        expected_info = self._extract_expected_info(text)
        # 关键修复：DOM 路径用 raw_html，正则备用路径必须用 clean text，不能有 HTML 标签
        # EN: Key fix: the DOM path uses raw_html; the regex fallback path must use clean text with no HTML tags
        # JA: 重要な修正：DOM の経路では raw_html を使い、正規表現の代替経路では HTML タグのない clean text を使わなければならない
        work_experiences = self._filter_work_experiences(
            self._extract_work_experiences(text, lang, raw_html=raw_html)
        )
        education_list = self._extract_education_list(text, lang, raw_html=raw_html)
        education_list = self._filter_education_entries(education_list, work_experiences)
        certificate_info = self._normalize_certificates(self._extract_certificates(text))
        language_info = self._extract_languages(text)
        skills_info = self._extract_skills(text)
        language_info, skills_info = self._normalize_language_and_skills(language_info, skills_info, text)
        
        base_info = {
            "full_name": full_name,
            "gender": gender,
            "age": str(age) if age else "",
            "birth_date": birth_date,
            "birth_year": str(birth_year) if birth_year else "",
            "marital_status": marital,
            "children_status": children,
            "political_status": "",
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "household_registration": h_reg,
            "address": address,
            "postal_code": "",
            "platform_from": platform_from,
            "platform_resume_id": "",
            "phone": phone or "",
            "email": email or "",
            "city": city,
            "nationality": "",
            "pr": pr
        }
        
        return {
            "resume_languge": lang,
            "base_info": base_info,
            "expected_info": expected_info,
            "work_experiences": work_experiences,
            "education_list": education_list,
            "certificate_info": certificate_info,
            "language_info": language_info,
            "skills_info": skills_info
        }

    def _filter_work_experiences(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """剔除被日期正则误切出的培训/证书清单，避免伪造工作经历。

        EN: Remove training/certificate lists wrongly cut out by the date regex, to avoid fabricating work history.

        JA: 日付の正規表現で誤って切り出された研修・資格の一覧を除去し、架空の職歴を作らないようにする。
        """
        kept = []
        for row in entries or []:
            company = str(row.get("company_name") or "").strip()
            company = re.sub(r"^(?:名称|公司|单位|企业)\s*[:：]\s*", "", company).strip()
            company = re.sub(r"\s*\[[^\]]*(?:年|个月|month|year)[^\]]*\]\s*$", "", company, flags=re.I).strip()
            row["company_name"] = company
            position = str(row.get("position") or "").strip()
            responsibilities = str(row.get("position_responsibilities") or "").strip()
            if not company:
                continue
            if not row.get("position_start") and not row.get("position_resigned"):
                continue
            if len(company) > 120 and not position and not responsibilities:
                continue
            if (re.search(r"培训中心|职业技术学校|国际标准认证|咨询中心", company)
                    and not position and not responsibilities):
                continue
            if len(re.findall(r"(?:19|20)\d{2}\s*[./年-]\s*\d{1,2}", company)) >= 2 and not position:
                continue
            kept.append(row)
        return kept

    def _filter_education_entries(self, entries: list[dict[str, Any]], works: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """教育经历只保留学校/学院等教育机构，剔除校内职务和工作公司。

        EN: Education history keeps only educational institutions such as schools/colleges, removing campus posts and employers.

        JA: 学歴には学校・学院などの教育機関だけを残し、学内の役職や勤務先は除く。
        """
        if not entries:
            return []
        work_names = {re.sub(r"\s+", "", str(w.get("company_name", "")).lower()) for w in works}
        kept: list[dict[str, Any]] = []
        campus_terms = ("校内职务", "学生会", "学生会社", "社团", "部长", "干事", "委员", "班长", "生活委员", "自管部", "实践团", "校团委", "校园")
        company_terms = ("有限公司", "有限责任公司", "股份有限公司", "公司", "银行", "咨询公司", "事务所",
                         "corporation", "company", "bank", "kpmg", "control risks", "mitsubishi", "firm")
        school_terms = ("大学", "学院", "学校", "高中", "中学", "研究院", "大学院", "university", "college", "institute")
        seen = set()
        for entry in entries:
            row = dict(entry)
            school = re.sub(r"[\x00-\x1f\x7f]", "", str(row.get("school_name", ""))).strip(" \t\r\n:：|│·•▲()（）[]【】")
            embedded_date = re.search(r"((?:19|20)\d{2}[./年-]\d{1,2}月?)\s*[-—–~～至到－]+\s*((?:19|20)\d{2}[./年-]\d{1,2}月?)", school)
            if embedded_date:
                row["school_start_ym"] = row.get("school_start_ym") or self._format_date(embedded_date.group(1))
                row["school_end_ym"] = row.get("school_end_ym") or self._format_date(embedded_date.group(2))
                school = school[embedded_date.end():].strip(" \t:：|│·•▲()（）[]【】")
            major = re.sub(r"[\x00-\x1f\x7f]", "", str(row.get("school_major_name", ""))).strip(" /|│")
            if len(major) > 40 or re.search(r"GPA|荣誉奖项|相关课程|是研究|主要目标|创造出", major, re.I):
                major = ""
            row["school_name"] = school
            row["school_major_name"] = major
            if "|" in str(row.get("school_degree_type", "")):
                degree_parts = [part.strip() for part in str(row.get("school_degree_type", "")).split("|") if part.strip()]
                if degree_parts:
                    row["school_degree_type"] = degree_parts[0]
                    if len(degree_parts) > 1 and not major:
                        row["school_major_name"] = degree_parts[1]
            compact = re.sub(r"\s+", "", school).lower()
            if not school or len(school) < 2 or compact in seen or school in ("时间", "时 间", "时    间", "日期", "学校"):
                continue
            if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", school):
                continue
            if any(term in school for term in campus_terms):
                continue
            if compact in work_names or any(term in school.lower() for term in company_terms):
                continue
            # 没有教育机构特征且像职位/职责的条目，视为误识别。
            # EN: Entries without education-institution features that look like positions/duties are treated as misidentified.
            # JA: 教育機関の特徴がなく職位・職務のように見える項目は誤認識とみなす。
            if not any(term in school.lower() for term in school_terms):
                if any(term in (school + major) for term in ("经理", "工程师", "主管", "部长", "职位", "职务", "担当", "开发")):
                    continue
                # 外文学校有 University/College 等；其余短行很可能是表格噪声。
                # EN: Foreign schools have University/College etc.; other short lines are probably table noise.
                # JA: 外国の学校には University/College などがある。それ以外の短い行は表のノイズである可能性が高い。
                if len(school) > 18 or re.search(r"[，,。；;]", school):
                    continue
            seen.add(compact)
            kept.append(row)
        return sorted(kept, key=lambda x: (int(str(x.get("school_degree_rank", "1")) or "1") if str(x.get("school_degree_rank", "1")).isdigit() else 1,
                                           x.get("school_end_ym", "")), reverse=True)

    def _extract_name(self, text: str, filename: str, source_path: str = "", raw_html: str = "") -> str:
        exclude = {
            "姓 名", "姓名", "氏 名", "氏名", "智联招聘", "前程无忧", "51job", "猎聘简历", "猎聘",
            "工作经历", "工作经验", "工作经", "个人简历", "个人简", "个人", "求职意向", "教育经历", "教育背景", "基本信息", "更新时间", "更新日期",
            "目前职业", "职业状态", "求职简历", "中文", "日語简历", "英文简历", "推荐报告", "工作地点", "东芝电梯", "产品分析",
            "面试登记表", "看图王", "履歴書", "職務経歴書", "docx", "doc", "pdf", "xlsx", "xls", "最高学历", "最近工作",
            "无忧精英", "无忧", "精英", "好机会", "年经验", "无关联", "新厂建设"
        }

        # 1. 优先从文件名中提取真实候选人姓名
        # EN: 1. Prefer extracting the real candidate name from the file name
        # JA: 1. ファイル名から本当の候補者名を抽出することを優先する
        if filename:
            fn_clean = re.sub(r"^(?:51job|智联招聘|前程无忧|猎聘简历|猎聘|无忧精英|简历|【简历】|[_\s\d])+", "", filename, flags=re.IGNORECASE).strip()
            m_fn_name = re.search(r"([\u4e00-\u9fff]{2,4})", fn_clean)
            if m_fn_name:
                name_cand = m_fn_name.group(1).strip()
                # 删除尾部噪音字（日/文/中/英/语/简/历/负/责等）
                # EN: Remove trailing noise characters (日/文/中/英/语/简/历/负/责, etc.)
                # JA: 末尾のノイズ文字（日／文／中／英／语／简／历／负／责 など）を除去する
                name_cand = re.sub(r"(?:的|简|历|负责|日|文|中|英|语|工|作)$", "", name_cand)
                if name_cand and len(name_cand) >= 2 and name_cand not in exclude and not any(noise in name_cand for noise in ["更新", "时间", "日期", "简历", "招聘", "无忧"]):
                    return name_cand

        # 2. DOM 提取：当有 raw_html 时，从表格内的氏名/姓名行直接报名（不依赖冒号分隔）
        # EN: 2. DOM extraction: when raw_html exists, take the name directly from the 氏名/姓名 row in the table (without relying on a colon separator)
        # JA: 2. DOM 抽出：raw_html がある場合は、表内の氏名／姓名の行から直接取る（コロン区切りに依存しない）
        if HAS_BS4 and raw_html and ("<html" in raw_html.lower() or "<table" in raw_html.lower()):
            try:
                from bs4 import BeautifulSoup as _BS
                _soup = _BS(raw_html, "html.parser")
                for _tr in _soup.find_all("tr"):
                    _tds = _tr.find_all("td")
                    if len(_tds) >= 2:
                        _k = _tds[0].get_text(strip=True)
                        _v = _tds[1].get_text(strip=True)
                        if re.search(r"氏\s*名|姓\s*名", _k):
                            _v = re.sub(r"(?:的|简|历|负责)$", "", _v.strip())
                            if _v and len(_v) >= 2 and _v not in exclude:
                                return _v
            except Exception:
                pass

        # 3. 尝试提取脱敏或真实姓名
        # EN: 3. Try extracting a masked or real name
        # JA: 3. マスク済みまたは実際の氏名の抽出を試みる
        m_mask = re.search(r"(?:姓\s*名|氏\s*名)[:：\t\s]*([\u4e00-\u9fff][\u4e00-\u9fff\*]{1,3})", text)
        if m_mask:
            val = m_mask.group(1).strip()
            val = re.sub(r"(?:的|简|历|负责)$", "", val)
            if val not in exclude and not any(noise in val for noise in ["更新", "时间", "日期", "无忧"]):
                return val

        # 3. 尝试通过 candidate_name_hint_from_path 匹配
        # EN: 3. Try matching via candidate_name_hint_from_path
        # JA: 3. candidate_name_hint_from_path によるマッチを試みる
        if source_path:
            hint = candidate_name_hint_from_path(source_path)
            if hint and hint not in exclude and len(hint) >= 2 and not any(noise in hint for noise in ["更新", "时间", "无忧"]):
                return re.sub(r"(?:的|简|历|负责)$", "", hint)

        # 4. 从正文中提取（抓取紧贴在年龄/性别/手机号之上的 2-4 字独立中文姓名）
        # EN: 4. Extract from the body (grab a standalone 2-4 character Chinese name just above age/gender/phone number)
        # JA: 4. 本文から抽出する（年齢・性別・電話番号のすぐ上にある独立した 2〜4 文字の中国語の氏名を取る）
        m_body_name = re.search(r"\n\s*([\u4e00-\u9fff]{2,4})\s*\n\s*(?:男|女|\d{2}\s*岁|13\d{9}|15\d{9}|18\d{9}|17\d{9}|19\d{9}|ID[:\：\d])", text)
        if m_body_name:
            val = m_body_name.group(1).strip()
            val = re.sub(r"(?:的|简|历|负责)$", "", val)
            if val not in exclude and not any(noise in val for noise in ["更新", "时间", "日期", "职业", "状态", "无忧"]):
                return val

        # 4b. 猎聘专属格式：正文前几行 "孔女士 离职，正在找工作" / "张三 在职"
        # EN: 4b. Liepin-specific format: the first lines of the body read "<surname>女士 离职，正在找工作" (Ms X, left job, looking for work) / "<name> 在职" (employed)
        # JA: 4b. Liepin 専用の形式：本文の最初の数行が「<姓>女士 离职，正在找工作」（〇〇さん、退職済み・求職中）／「<氏名> 在职」（在職中）
        lines_all = [l.strip() for l in text.splitlines() if l.strip()]
        for l in lines_all[:8]:
            # 过滤含路径/时间的元数据行
            # EN: Filter metadata lines containing paths/times
            # JA: パスや日時を含むメタデータ行を除外する
            if any(noise in l for noise in ["源文件", "下载时间", "路径", "\\", "/"]):
                continue
            m_lp = re.match(r"^([\u4e00-\u9fff]{2,5}(?:女士|先生)?)\s+(?:离职|在职|求职|找工作|工作|应届)", l)
            if m_lp:
                cand = m_lp.group(1).strip()
                cand = re.sub(r"(?:的|简|历|负责)$", "", cand)
                if cand not in exclude and len(cand) >= 2:
                    return cand

        # 5. 从正文头部匹配姓名
        # EN: 5. Match the name from the head of the body
        # JA: 5. 本文の冒頭から氏名をマッチさせる
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for l in lines[:10]:
            if any(noise in l for noise in ["更新", "时间", "日期", "简历", "招聘", "51job", "ID:", "无忧", "源文件", "下载"]):
                continue
            m_l = re.match(r"^([\u4e00-\u9fff]{2,4})$", l)
            if m_l:
                cand = m_l.group(1)
                cand = re.sub(r"(?:的|简|历|负责)$", "", cand)
                if cand not in exclude:
                    return cand

        return ""



    def _extract_gender(self, text: str) -> str:
        m = re.search(r"(?:性\s*别|性\s*別)\s*[:：\t\n\s]*(男|女|男性|女性)", text)
        if m:
            val = m.group(1)
            return "女" if "女" in val else "男"
        if re.search(r"\b男\b|男性", text[:400]):
            return "男"
        if re.search(r"\b女\b|女性", text[:400]):
            return "女"
        return ""

    def _extract_birth(self, text: str) -> tuple[str, int | None, int | None]:
        m_age_full = re.search(r"(\d{2})\s*岁\s*[\(（]((?:19|20)\d{2})[年\.\/\-](\d{1,2})[月\.\/\-](\d{1,2})日?[\)）]", text)
        if m_age_full:
            age = int(m_age_full.group(1))
            b_year = int(m_age_full.group(2))
            b_month = f"{int(m_age_full.group(3)):02d}"
            b_day = f"{int(m_age_full.group(4)):02d}"
            return f"{b_year}年{b_month}月{b_day}日", b_year, age

        m = re.search(r"(?:出生日期|生年月日|出生年月|生日|生\s*日)\s*[:：\t\n\s]*((?:19|20)\d{2}[-./年/\ufffd／]\d{1,2}(?:[-./月/\ufffd／]\d{1,2})?日?)", text)
        if m:
            raw_b = m.group(1).strip()
            b_year_m = re.search(r"((?:19|20)\d{2})", raw_b)
            b_month_m = re.search(r"(?:19|20)\d{2}\D{1,3}(\d{1,2})", raw_b)
            b_day_m = re.search(r"(?:19|20)\d{2}\D{1,3}\d{1,2}\D{1,3}(\d{1,2})", raw_b)
            
            b_year = int(b_year_m.group(1)) if b_year_m else None
            age = 2026 - b_year if b_year else None
            
            b_month = f"{int(b_month_m.group(1)):02d}" if b_month_m else "01"
            b_day = f"{int(b_day_m.group(1)):02d}" if b_day_m else "01"
            
            formatted_birth = f"{b_year}年{b_month}月{b_day}日" if b_year else ""
            return formatted_birth, b_year, age
            
        m_age = re.search(r"(?:年\s*齢|年\s*龄|岁)\s*[:：\t\n\s]*(\d{2})|(?<!\d)(\d{2})\s*岁", text)
        if m_age:
            age_val = m_age.group(1) or m_age.group(2)
            age = int(age_val)
            b_year = 2026 - age
            return f"{b_year}年01月01日", b_year, age
            
        return "", None, None

    def _format_date(self, raw_str: str) -> str:
        if not raw_str or raw_str in ("至今", "现在", "目前", "Present", "今迄", "現在"):
            return raw_str or ""
        m_y = re.search(r"((?:19|20)\d{2})", raw_str)
        m_m = re.search(r"(?:19|20)\d{2}\D{1,3}(\d{1,2})", raw_str)
        m_d = re.search(r"(?:19|20)\d{2}\D{1,3}\d{1,2}\D{1,3}(\d{1,2})", raw_str)
        
        if m_y:
            y = m_y.group(1)
            m = f"{int(m_m.group(1)):02d}" if m_m else "01"
            d = f"{int(m_d.group(1)):02d}" if m_d else "01"
            return f"{y}年{m}月{d}日"
        return raw_str

    def _extract_marital_and_children(self, text: str) -> tuple[str, str]:
        marital = ""
        children = ""
        m = re.search(r"(?:婚姻状况|婚姻|婚姻状況|配偶者)\s*[:：\t\n\s]*([^\n]+)", text)
        if m:
            val = m.group(1).strip()
            if "已婚" in val or "有" in val: marital = "已婚"
            elif "未婚" in val or "独身" in val or "無" in val: marital = "未婚"
            if "育" in val or "子" in val: children = "已育"
            
        if not marital:
            if re.search(r"已婚|既婚", text[:600]): marital = "已婚"
            elif re.search(r"未婚|独身", text[:600]): marital = "未婚"
        return marital, children

    def _extract_phone(self, text: str) -> str:
        m = re.search(r"(?:手\s*机|电\s*话|TEL|电话号码|联系电话|联系方式|携帯|連絡方法)\s*[:：\t\n\s]*((?:\+\s*86[\s-]?)?1[3-9][0-9][\s-]?\d{4}[\s-]?\d{4})", text)
        if m:
            clean_p = re.sub(r"[^\d]", "", m.group(1))
            if len(clean_p) >= 11:
                return clean_p[-11:]
        m2 = re.search(r"(?:\+86[\s-]?)?(?<!\d)(1[3-9]\d{9})(?!\d)", text)
        if m2:
            return m2.group(1)
        return ""

    def _extract_email(self, text: str) -> str:
        m = re.search(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text)
        if m:
            return m.group(1)
        return ""

    def _extract_city_and_address(self, text: str) -> tuple[str, str]:
        city = ""
        address = ""
        m_addr = re.search(r"(?:现住地址|家庭住址|联系地址|住所|现住所)\s*[:：\t\n\s]*([^\n]+)", text)
        if m_addr:
            address = m_addr.group(1).strip()
            
        m_city = re.search(r"(?:现居住|居住地|现居住地|户口所在地|城市|现在所|地\s*域|所在地)\s*[:：\t\n\s]*([\u4e00-\u9fff]{2,10})", text)
        if m_city:
            c_val = m_city.group(1).strip()
            if not any(noise in c_val for noise in ["项目", "储备", "拥有", "隐私", "信息", "期望"]):
                c_clean = re.split(r"[-_\s]", c_val)[0].strip()
                if len(c_clean) >= 2:
                    city = c_clean if c_clean.endswith("市") else c_clean + "市"

        if not city and address:
            m_c = re.search(r"([\u4e00-\u9fff]{2,5}市)", address)
            if m_c: city = m_c.group(1)
            
        if not city:
            head_text = text[:600]
            m_exp = re.search(r"(?:求职意向|期望地点|地点)[:：]", head_text)
            if m_exp:
                head_text = head_text[:m_exp.start()]
            for c in ["北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "南京", "苏州", "天津", "武汉", "厦门", "大连", "青岛", "西安"]:
                if c in head_text:
                    city = c + "市"
                    break
        return city, address

    def _extract_pattern(self, text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
        return ""

    def _extract_pr(self, text: str) -> str:
        # 简历版块标题通常没有空行，不能只依赖空行作为结束条件。
        # EN: Résumé section headings usually have no blank line before them, so a blank line cannot be the only end condition.
        # JA: 履歴書の項目見出しの前には通常空行がないため、空行だけを終了条件にはできない。
        section_stops = (
            r"工作经验|工作经历|工作背景|职业概况|仕事経験|職歴|勤務履歴|勤務歴|"
            r"教育经历|教育背景|学历|学歴|项目经历|项目经验|研究经历|"
            r"培训经历|培训背景|语言能力|外语水平|技能标签|专业技能|计算机水平|"
            r"证书|资格证书|附加信息|附加消息|求职意向|职业意向|个人信息|基本信息|"
            r"希望職|求職希望|自己PR|個人PR|个人优势|兴趣爱好|趣味"
        )
        pr_val = ""
        m = re.search(
            rf"(?:自我评价|自己PR|个人自述|概要＆ポイント|自\s*评|自己アピール)"
            rf"\s*[:：\t\s]*([\s\S]{{10,800}}?)(?=\n\s*(?:{section_stops})\s*[:：]?\s*(?:\n|$)|声明：|\Z)",
            text,
            re.IGNORECASE,
        )
        if m:
            pr_val = m.group(1).strip()
        else:
            # 降级截取
            # EN: Fallback truncation
            # JA: 代替の切り出し
            m_fallback = re.search(r"(?:自我评价|自\s*评)\s*[:：\t\s]*([\s\S]+)", text, re.IGNORECASE)
            if m_fallback:
                pr_val = m_fallback.group(1).strip()

        # 某些模板把下一个标题直接接在上一行之后，统一截断一次。
        # EN: Some templates put the next heading directly after the previous line; truncate once uniformly.
        # JA: テンプレートによっては次の見出しが前の行の直後に続くため、一律に 1 回切り詰める。
        if pr_val:
            stop_match = re.search(rf"\n\s*(?:{section_stops})\s*[:：]?\s*(?:\n|$)", "\n" + pr_val, re.IGNORECASE)
            if stop_match:
                pr_val = pr_val[:max(0, stop_match.start() - 1)].strip()
                
        # 彻底剥离版权声明、操作时间及操作人（猎聘/智联尾部固定文本块）
        # EN: Completely strip copyright notices, operation times and operators (the fixed trailing text block of Liepin/Zhaopin)
        # JA: 著作権表示・操作日時・操作者（Liepin・Zhaopinの末尾にある定型テキストブロック）を完全に除去する
        pr_val = re.sub(r"声明：[\s\S]*$", "", pr_val).strip()
        pr_val = re.sub(r"操作时间[\s\S]*$", "", pr_val).strip()
        pr_val = re.sub(r"操作人[:：\s]*\d+[\s\S]*$", "", pr_val).strip()
        return pr_val[:600]

    def _detect_platform(self, text: str, filename: str) -> str:
        if "51job" in text.lower() or "前程无忧" in text or "51job" in filename.lower():
            return "前程无忧(51job)"
        if "zhilian" in text.lower() or "智联招聘" in text or "智联" in filename or "和ta聊聊" in text.lower():
            return "智联招聘"
        if "liepin" in text.lower() or "猎聘" in text or "猎聘" in filename:
            return "猎聘网"
        if "boss" in text.lower() or "直聘" in text:
            return "BOSS直聘"
        return ""

    def _extract_expected_info(self, text: str) -> list[dict[str, Any]]:
        exp_pos = ""
        exp_sal = ""
        exp_city = ""
        exp_ind = ""
        min_sal = ""
        max_sal = ""

        m = re.search(r"(?:\|?\s*(?:职业发展意向|求职意向|希望条件|期望工作|求職希望|希望職|职业意向))\s*[:\：\t\s]*([\s\S]{5,800}?)(?=\n\s*(?:\|?\s*(?:工作经验|工作经历|仕事経験|教育经历|学歴|保护隐私提示|目前职业概况|个人信息)|\Z))", text)
        sec = m.group(1) if m else text[:2500]


        # 工作信息字段黑名单——这些键出现时说明是工作经历字段，不是求职意向
        # EN: Blacklist of work-information fields: when these keys appear they are work-history fields, not job preferences
        # JA: 職歴情報フィールドのブラックリスト：これらのキーがあれば職歴のフィールドであり、希望条件ではない
        WORK_FIELD_KEYS = {"月薪", "月    薪", "日薪", "所在部门", "汇报对象", "下属人数", "工作地点", "薪酬情况",
                           "公司规模", "公司行业", "公司名称", "职责业绩", "职务职责", "项目职务", "所在公司"}

        for line in sec.splitlines():
            items = [item.strip() for item in re.split(r"\s{2,}|\t+", line) if item.strip()]
            for item in items:
                if ":" in item or "：" in item:
                    k, v = re.split(r"[:：]", item, 1)
                    k, v = k.strip(), v.strip()
                    # 跳过工作经历字段
                    # EN: Skip work-history fields
                    # JA: 職歴のフィールドをスキップする
                    if k in WORK_FIELD_KEYS: continue
                    if k in ("地点", "期望地点", "期望城市", "期望工作地点") and not exp_city:
                        if not any(bad in v for bad in ["薪", "月薪", "年薪", "部门", "汇报", "人数"]):
                            exp_city = v
                    elif k in ("职能/职位", "期望职位", "目标职能", "期望从事职业", "职能", "职位") and not exp_pos:
                        exp_pos = v
                    elif k in ("行业", "期望行业", "目标行业") and not exp_ind:
                        exp_ind = v
                    elif k in ("期望薪资", "期望薪水", "期望年薪", "薪资") and not exp_sal:
                        exp_sal = v

        # ─── 猎聘/智联 管道符格式解析 ───────────────────────────────────────────
        # 格式示例：
        #   项目经理/主管 | 上海 | 22-28k×14薪
        #   全部行业
        #   PMO | 上海 | 20-28k×14薪
        #   全部行业
        # EN: ─── Parse the Liepin/Zhaopin pipe-separated format ───
        #     Format example:
        #       项目经理/主管 | 上海 | 22-28k×14薪
        #       全部行业
        #       PMO | 上海 | 20-28k×14薪
        #       全部行业
        # JA: ─── Liepin／Zhaopin のパイプ区切り形式の解析 ───
        #     形式の例：
        #       项目经理/主管 | 上海 | 22-28k×14薪
        #       全部行业
        #       PMO | 上海 | 20-28k×14薪
        #       全部行业
        if not exp_pos or not exp_city:
            # 在求职意向 section 里找管道符格式行
            # EN: Look for pipe-format lines within the job-preference section
            # JA: 希望条件の section 内でパイプ区切り形式の行を探す
            pipe_lines = [l.strip() for l in sec.splitlines() if "|" in l and re.search(r"[\u4e00-\u9fff]", l)]
            for pl in pipe_lines:
                parts = [p.strip() for p in pl.split("|")]
                if len(parts) >= 2:
                    # parts[0] = 职位/职能，parts[1] = 城市，parts[2] = 薪资（可选）
                    # EN: parts[0] = position/function, parts[1] = city, parts[2] = salary (optional)
                    # JA: parts[0] = 職位・職能、parts[1] = 都市、parts[2] = 給与（任意）
                    pos_cand = parts[0].strip()
                    city_cand = parts[1].strip()
                    sal_cand = parts[2].strip() if len(parts) >= 3 else ""

                    # 职位：不能包含年份/数字开头/薪资关键词
                    # EN: Position: must not contain a year, start with a digit, or contain salary keywords
                    # JA: 職位：年を含まない、数字で始まらない、給与のキーワードを含まないこと
                    if not exp_pos and pos_cand and len(pos_cand) <= 20:
                        if not any(bad in pos_cand for bad in ["薪", "万", "k×", "K×", "全部"]):
                            exp_pos = pos_cand

                    # 城市：是真实城市名
                    # EN: City: is a real city name
                    # JA: 都市：実在する都市名であること
                    MAJOR_CITIES = {"北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "南京", "苏州",
                                    "天津", "武汉", "厦门", "大连", "青岛", "西安", "长沙", "郑州", "无锡"}
                    if not exp_city and city_cand and len(city_cand) <= 6:
                        if any(c in city_cand for c in MAJOR_CITIES) or re.fullmatch(r"[\u4e00-\u9fff]{2,6}", city_cand):
                            if not any(bad in city_cand for bad in ["薪", "行业", "经验"]):
                                exp_city = city_cand

                    # 薪资
                    # EN: Salary
                    # JA: 給与
                    if not exp_sal and sal_cand:
                        if re.search(r"\d+[-~]\d+[kK×]?", sal_cand):
                            exp_sal = sal_cand
                    if exp_pos and exp_city:
                        break

        # 行业：如果只有"全部行业"就不填
        # EN: Industry: leave empty if it is only "全部行业" (all industries)
        # JA: 業界：「全部行业」（全業界）だけなら記入しない
        if exp_ind == "全部行业" or exp_ind == "不限":
            exp_ind = ""

        if not exp_city:
            # 严格只从求职意向段内搜索期望地点
            # EN: Search for the desired location strictly within the job-preference section only
            # JA: 希望勤務地は希望条件の段落内だけで厳格に探す
            m_sec_city = re.search(r"(?:期望地点|期望城市|期望工作地点|希望勤務地)\s*[:：\t\s]*\n?\s*([^\n\t:：]+)", sec)
            if m_sec_city:
                c_cand = re.split(r"\s*(?:行业|职能|职位|到岗时间|工作类型|期望|个人标签)[:：]", m_sec_city.group(1))[0].strip()
                if not any(bad in c_cand for bad in ["薪", "月薪", "年薪", "部门", "汇报", "人数", "0人"]):
                    exp_city = c_cand

        if not exp_pos:
            m_pos = re.search(r"(?:期望职位|目标职能|希望職種|希望職|期望从事职业|求職希望|职能/职位|职能|职位)\s*[:：\t\s]*\n?\s*([^\n\t:：]+)", sec)
            if m_pos: exp_pos = re.split(r"\s*(?:行业|地点|到岗时间|工作类型|期望|薪资|年薪)[:：]", m_pos.group(1))[0].strip()

        if not exp_ind:
            m_ind = re.search(r"(?:期望行业|目标行业|行业)\s*[:\uff1a\t\s]*\n?\s*([^\n\t:\uff1a]+)", sec)
            if m_ind:
                ind_cand = re.split(r"\s*(?:地点|职能|职位|到岗时间|工作类型|期望|薪资|年薪)[:\uff1a]", m_ind.group(1))[0].strip()
                # 过滤含管道符的误匹配（管道符说明是 职位|城市|薪资 这种格式行）
                # EN: Filter false matches containing pipes (a pipe indicates a "position|city|salary" format line)
                # JA: パイプを含む誤マッチを除外する（パイプは「職位|都市|給与」形式の行であることを示す）
                if "|" not in ind_cand and ind_cand not in ("全部行业", "不限", "") and self._is_valid_industry(ind_cand):
                    exp_ind = ind_cand

        if not exp_sal:
            m_sal = re.search(r"(?:期望薪资|期望薪水|期望年薪|希望給料|薪资)\s*[:：\t\s]*\n?\s*([^\n\t:：]+)", sec)
            if m_sal: exp_sal = re.split(r"\s*(?:地点|行业|职能|职位|到岗时间|工作类型|期望)[:：]", m_sal.group(1))[0].strip()

        if exp_sal:
            m_range_w = re.search(r"(\d+(?:\.\d+)?)\s*万\s*[-～~—]\s*(\d+(?:\.\d+)?)\s*万", exp_sal)
            if m_range_w:
                try:
                    min_sal = str(int(float(m_range_w.group(1)) * 10000))
                    max_sal = str(int(float(m_range_w.group(2)) * 10000))
                except Exception:
                    pass
            else:
                m_range_m = re.search(r"(\d+)\s*[-～~—]\s*(\d+)\s*(?:元|K|k)?\s*(?:/|每)?\s*月", exp_sal)
                if m_range_m:
                    try:
                        v1 = int(m_range_m.group(1))
                        v2 = int(m_range_m.group(2))
                        if "K" in exp_sal.upper() or "k" in exp_sal:
                            v1 *= 1000
                            v2 *= 1000
                        min_sal = str(v1 * 12)
                        max_sal = str(v2 * 12)
                    except Exception:
                        pass

        return [{
            "expected_city": exp_city or "",
            "expected_position": exp_pos or "",
            "expected_salary": exp_sal or "",
            "expected_annual_salary_min": min_sal or "",
            "expected_annual_salary_max": max_sal or "",
            "expected_industry": exp_ind or "",
            "expected_employment_type": "全职",
            "expected_start_date": "即时"
        }]

    def _is_valid_industry(self, value: str) -> bool:
        """过滤把工作职责/业绩误填到期望行业的情况。

        EN: Filter cases where job duties/achievements were filled into the desired industry by mistake.

        JA: 職務や実績が希望業界に誤って入っているケースを除外する。
        """
        value = re.sub(r"\s+", " ", (value or "")).strip(" ：:，,；;。．")
        if not value or len(value) > 60 or "|" in value or "\n" in value:
            return False
        # 行业是名词短语；这些词通常标志着句子已经进入职责/项目描述。
        # EN: Industries are noun phrases; these words usually signal that the sentence has moved into duties/project descriptions.
        # JA: 業界は名詞句であり、これらの語は通常、文が職務・プロジェクトの説明に入ったことを示す。
        bad_terms = ("负责", "参与", "撰写", "维护", "升级", "控制", "编写", "设计", "开发",
                     "工作", "职责", "业绩", "文档", "固件", "代码", "项目", "客户", "供应商",
                     "部门", "汇报", "实现", "完成", "熟悉", "掌握", "优化")
        if any(term in value for term in bad_terms):
            return False
        if re.search(r"[。！？；;]", value):
            return False
        return True

    def _extract_work_experiences(self, text: str, lang: str, raw_html: str = "") -> list[dict[str, Any]]:
        works = []
        html_source = raw_html if raw_html else text
        
        # 1. 优先使用 DOM 节点抓取（针对猎聘/智联等 HTML 格式简历）
        # EN: 1. Prefer DOM node extraction (for HTML-format résumés such as Liepin/Zhaopin)
        # JA: 1. DOM ノードからの取得を優先する（Liepin／Zhaopin などの HTML 形式の履歴書向け）
        if HAS_BS4 and ("<html" in html_source.lower() or "<table" in html_source.lower() or "<tr" in html_source.lower()):
            try:
                soup = BeautifulSoup(html_source, "html.parser")
                work_tr = None
                for tr in soup.find_all("tr"):
                    if "工作经历" in tr.get_text():
                        work_tr = tr
                        break
                        
                if work_tr:
                    curr_tr = work_tr.find_next_sibling("tr")
                    curr_work = None
                    
                    while curr_tr:
                        txt_tr = curr_tr.get_text(strip=True)
                        if any(stop in txt_tr for stop in ["项目经历", "教育经历", "语言能力", "技能标签", "自我评价"]):
                            break
                            
                        tds = curr_tr.find_all("td")
                        if len(tds) >= 2:
                            left_txt = tds[0].get_text(strip=True)
                            right_txt = tds[1].get_text(strip=True)
                            
                            m_time = re.search(r"((?:19|20)\d{2}[\.\/年-]\d{1,2})\s*[-—–~∼～\-./~〜ー]{1,5}\s*((?:19|20)\d{2}[\.\/年-]\d{1,2}|至今|现在|Present)", right_txt)
                            if m_time and left_txt:
                                if curr_work and curr_work.get("company_name"):
                                    works.append(curr_work)
                                    
                                start_p = self._format_date(m_time.group(1))
                                end_p = m_time.group(2)
                                if end_p not in ("至今", "现在", "Present"):
                                    end_p = self._format_date(end_p)
                                    
                                curr_work = {
                                    "company_name": left_txt,
                                    "company_employees": "",
                                    "company_industry": "",
                                    "position": "",
                                    "position_type": "",
                                    "position_salary": "",
                                    "position_dept": "",
                                    "position_report_to": "",
                                    "position_subordinate": "0人",
                                    "employment_type": "全职",
                                    "annual_salary_min": "",
                                    "annual_salary_max": "",
                                    "status": "在职" if end_p in ("至今", "现在", "Present") else "离职",
                                    "position_start": start_p,
                                    "position_resigned": "" if end_p in ("至今", "现在", "Present") else end_p,
                                    "resigned_reason": "",
                                    "position_responsibilities": ""
                                }
                        elif len(tds) == 1 and curr_work and not curr_work.get("position"):
                            pos_txt = tds[0].get_text(strip=True)
                            if pos_txt and not any(k in pos_txt for k in ["所在部门", "汇报对象", "下属人数", "职责业绩"]):
                                curr_work["position"] = pos_txt
                        elif curr_work:
                            if "下属人数" in txt_tr:
                                m_sub = re.search(r"下属人数\s*[:：\s]*(\d+人|\d+)", txt_tr)
                                if m_sub: curr_work["position_subordinate"] = m_sub.group(1)
                            elif "职责业绩" in txt_tr:
                                resp_txt = re.sub(r"^职责业绩\s*[:：\s]*", "", txt_tr)
                                curr_work["position_responsibilities"] = resp_txt[:800]
                                
                        curr_tr = curr_tr.find_next_sibling("tr")
                        
                    if curr_work and curr_work.get("company_name"):
                        works.append(curr_work)
                        
                if works:
                    return works
                    
                # 1b. <p> 段落格式 DOM 提取（日语 Word 简历，如程坤平）
                # 格式: <p>2020.09-2022.03    深セン市訳雅馨翻訳有限会社</p>
                #        <p>高级日本语翻译通译</p>
                #        <p>报告相手: なし</p>
                # EN: 1b. DOM extraction for <p> paragraph format (Japanese Word résumés)
                #     Format: <p>2020.09-2022.03    深セン市訳雅馨翻訳有限会社</p>
                #            <p>高级日本语翻译通译</p>
                #            <p>报告相手: なし</p>
                # JA: 1b. <p> 段落形式の DOM 抽出（日本語の Word 履歴書）
                #     形式：<p>2020.09-2022.03    深セン市訳雅馨翻訳有限会社</p>
                #            <p>高级日本语翻译通译</p>
                #            <p>报告相手: なし</p>
                WORK_STOPS_JP = ["学歴関係", "学歴", "個人 PR", "個人PR", "趣味", "資格", "を持つ"]
                p_tags = [p for p in soup.find_all("p") if p.get_text(strip=True)]
                
                # 找到勤務履歴标题行
                # EN: Find the 勤務履歴 (work history) heading line
                # JA: 勤務履歴の見出し行を探す
                work_sec_start_idx = -1
                work_sec_end_idx = len(p_tags)
                for idx, p in enumerate(p_tags):
                    t = p.get_text(strip=True)
                    if any(kw in t for kw in ["勤務履歴", "履歴書", "仕事経験", "Work Experience", "工作经历"]):
                        if not any(stop in t for stop in ["年工作经验", "年经验"]):
                            work_sec_start_idx = idx + 1
                    elif work_sec_start_idx > -1 and any(stop in t for stop in WORK_STOPS_JP):
                        work_sec_end_idx = idx
                        break
                        
                if work_sec_start_idx > -1:
                    TIME_PAT = re.compile(
                        r"((?:19|20)\d{2}[.\./]\d{1,2})\s*[-—–~∼～]{0,3}\s*((?:19|20)\d{2}[.\./]\d{1,2}|\u73fe在|今迄|\u81f3今|Present)"
                    )
                    curr_work = None
                    for p in p_tags[work_sec_start_idx:work_sec_end_idx]:
                        t = p.get_text(strip=True)
                        m_t = TIME_PAT.search(t)
                        if m_t:
                            if curr_work and curr_work.get("company_name"):
                                works.append(curr_work)
                            start_p = self._format_date(m_t.group(1))
                            end_raw = m_t.group(2)
                            is_current = end_raw in ("現在", "今迄", "至今", "Present")
                            end_p = "" if is_current else self._format_date(end_raw)
                            # 公司名在同一行时间后面
                            # EN: The company name follows the dates on the same line
                            # JA: 会社名は同じ行の期間の後ろにある
                            comp_part = t[m_t.end():].strip()
                            comp_part = re.sub(r"^[\s\t　]+", "", comp_part)
                            curr_work = {
                                "company_name": comp_part,
                                "company_employees": "", "company_industry": "",
                                "position": "", "position_type": "", "position_salary": "",
                                "position_dept": "", "position_report_to": "", "position_subordinate": "0人",
                                "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "",
                                "status": "在职" if is_current else "离职",
                                "position_start": start_p, "position_resigned": end_p,
                                "resigned_reason": "", "position_responsibilities": ""
                            }
                        elif curr_work is not None:
                            # 属于当前公司的付属行
                            # EN: Subsidiary lines belonging to the current company
                            # JA: 現在の会社に属する付随行
                            t_strip = t
                            if not curr_work.get("position") and t_strip and len(t_strip) <= 20:
                                if not any(kw in t_strip for kw in ["报告相手", "業務内容", "業務", "·", "◇"]):
                                    curr_work["position"] = t_strip
                            elif "業務内容" in t_strip or "業務" in t_strip:
                                resp = re.sub(r"^[業務内容業務]+[\s：:]*", "", t_strip)
                                curr_work["position_responsibilities"] += resp + "\n"
                    if curr_work and curr_work.get("company_name"):
                        works.append(curr_work)
            except Exception:
                pass

        # 2. 降级模式：纯文本段落与正则解析（使用 clean_text，不含 HTML 标签）
        # EN: 2. Fallback mode: plain-text paragraphs and regex parsing (using clean_text, without HTML tags)
        # JA: 2. 代替モード：プレーンテキストの段落と正規表現による解析（HTML タグを含まない clean_text を使う）
        pattern = re.compile(r"((?:19|20)\d{2}[\.\/年-]\d{1,2})\s*[-—–~∼～\u2014\u2013\uff0d¡£`\-./\ufffd~〜ー\s]{1,5}\s*((?:19|20)\d{2}[\.\/年-]\d{1,2}|至今|现在|目前|Present|今迄|現在)", re.IGNORECASE)

        clean_text = re.sub(r"(?:搜索同事|更多)\s*", "", text)

        m_head = None
        for m in re.finditer(r"(?:工作经验|工作经历|職歴|仕事経験|Work Experience|履历)", clean_text, re.IGNORECASE):
            line_str = clean_text[max(0, m.start()-10):m.end()+10].splitlines()[0] if clean_text[max(0, m.start()-10):m.end()+10].splitlines() else ""
            if not any(stop in line_str for stop in ["年工作经验", "年经验", "工作年限", "最近工作", "简历-猎聘", ".doc", ".docx"]):
                m_head = m
                break
        if m_head:
            sec_start = m_head.end()
            m_next = re.search(r"\n\s*(?:教育程度|教育经历|教育背景|学歴|学\s*历|项目经历|项目经验|项目|【?项目经历】?|【?项目经验】?|外语水平|计算机水平|语言能力|语言|技能|Education|打工经历|奖惩情况|研究经历|自我评价|自己アピール|附加信息|\Z)", clean_text[sec_start:], re.IGNORECASE)
            sec_end = sec_start + m_next.start() if m_next else len(clean_text)
            sec = clean_text[sec_start:sec_end]

            matches = list(pattern.finditer(sec))
            for i, match in enumerate(matches):
                start_p = self._format_date(match.group(1))
                end_p = match.group(2)
                if end_p not in ("至今", "现在", "目前", "Present", "今迄", "現在"):
                    end_p = self._format_date(end_p)

                block_start = match.end()
                block_end = matches[i+1].start() if i+1 < len(matches) else len(sec)
                block_text = sec[block_start:block_end].strip()

                # 有些 Word 模板把“公司、职位”放在日期之前：
                # 公司\n职位\n2020.09—2021.06\n内容：……。不能从日期后的下一家公司反推当前公司。
                # EN: Some Word templates put "company, position" before the dates:
                #     company\nposition\n2020.09—2021.06\n内容：……. The current company must not be inferred from the next company after the dates.
                # JA: Word テンプレートによっては「会社、職位」が日付の前にある：
                #     会社\n職位\n2020.09—2021.06\n内容：……。日付の後ろにある次の会社から現在の会社を逆算してはならない。
                before_lines = [l.strip() for l in sec[:match.start()].splitlines() if l.strip()]
                preceding_company = ""
                preceding_position = ""
                for prev in reversed(before_lines[-6:]):
                    if (len(prev) <= 80 and
                            not any(noise in prev for noise in ["工作描述", "工作内容", "工作项目", "参与公司", "负责公司", "BIM工作", "项目负责", "培训和"])
                            and re.search(r"(?:有限公司|有限责任公司|公司|集团|企业|事务所|Corporation|Company)", prev, re.I)):
                        preceding_company = prev
                        break
                if before_lines:
                    candidate_prev = before_lines[-1]
                    if candidate_prev != preceding_company and not re.search(r"(?:工作经历|工作经验|项目经历|内容|职责)", candidate_prev):
                        preceding_position = candidate_prev

                # 下一段公司的标题位于下一日期之前，不能粘进本段工作内容。
                # EN: The heading of the next company sits before the next date and must not be glued onto this section's job content.
                # JA: 次の会社の見出しは次の日付の前にあり、この段落の業務内容にくっつけてはならない。
                first_block_line = next((x.strip() for x in block_text.splitlines() if x.strip()), "")
                inline_current_company = bool(
                    first_block_line
                    and not re.match(r"^(?:内容|工作描述|工作职责|职责业绩|职责|项目描述|项目简介|\d+[.)、])", first_block_line)
                    and re.search(r"(?:有限公司|有限责任公司|公司|集团|企业|事务所|Corporation|Company)", "\n".join(block_text.splitlines()[:5]), re.I)
                )
                next_company = re.search(
                    r"(?m)^\s*[^\n]{2,120}(?:有限公司|有限责任公司|公司|集团|企业|事务所|Corporation|Company)[^\n]*$",
                    block_text,
                    re.IGNORECASE,
                )
                if next_company and next_company.start() > 0 and preceding_company and not inline_current_company:
                    block_text = block_text[:next_company.start()].rstrip()

                lines = [l.strip() for l in block_text.splitlines() if l.strip()]
                company_name = ""
                position = ""
                dept = ""
                industry = ""
                emp_count = ""
                report_to = ""
                subordinate = ""
                salary = ""
                resp = ""

                if lines:
                    if preceding_company:
                        company_name = preceding_company
                    if preceding_position:
                        position = preceding_position
                    if inline_current_company:
                        inline_match = re.search(
                            r"(?m)^\s*[^\n]{2,120}(?:有限公司|有限责任公司|公司|集团|企业|事务所|Corporation|Company)[^\n]*$",
                            "\n".join(lines[:5]),
                            re.I,
                        )
                        if inline_match:
                            company_name = inline_match.group(0).strip()
                        if lines and not re.search(r"(?:内容|工作描述|工作职责|职责|项目描述)", lines[0]):
                            position = lines[0]
                    m_comp_tag = re.search(r"(?:所在公司|公司名称|单位名称)[:：\s]*([^\n]+)", block_text)
                    if m_comp_tag and not company_name:
                        c_sub = m_comp_tag.group(1).strip()
                        c_m_sub = re.search(r"([\u4e00-\u9fff\(\)（）A-Za-z0-9]+(?:公司|办事处|企业|机构|有限责任公司|研究院|院|厂|集团))", c_sub)
                        if c_m_sub:
                            company_name = c_m_sub.group(1).strip()
                        else:
                            company_name = c_sub

                    if not company_name:
                        for l_check in lines[:4]:
                            c_m = re.search(r"([\u4e00-\u9fff\(\)（）A-Za-z0-9]+(?:公司|办事处|企业|机构|有限责任公司|研究院|院|厂|集团))", l_check)
                            if c_m and not c_m.group(1).isdigit():
                                company_name = c_m.group(1).strip()
                                break

                    if not company_name:
                        first_line = re.sub(r"[\xa0\s]+", " ", lines[0])
                        parts = [p.strip() for p in first_line.split(" ") if p.strip()]
                        if len(parts) >= 1 and not parts[0].isdigit() and not any(kw in parts[0] for kw in ["技术", "工程师", "经理"]):
                            company_name = parts[0]

                    m_rep = re.search(r"(?:汇报对象|直属上司|汇报给)[:：\s]*([^\s\t\n|│]+)", block_text)
                    if m_rep:
                        v_rep = m_rep.group(1).strip()
                        if not any(tag in v_rep for tag in ["下属", "人数", "薪酬", "部门", "地区", "职责", "业绩", "：", ":"]):
                            report_to = v_rep

                    m_sub = re.search(r"(?:下属人数|管辖人数|团队人数)[:：\s]*(\d+|[^\s\t\n|│]+)", block_text)
                    if m_sub:
                        v_sub = m_sub.group(1).strip()
                        if not any(tag in v_sub for tag in ["薪酬", "部门", "地区", "职责", "业绩", "：", ":"]):
                            subordinate = v_sub

                    m_emp = re.search(r"公司规模[:：\s]*([^\s\t\n|│]+)", block_text)
                    if m_emp:
                        v_emp = m_emp.group(1).strip()
                        if not any(tag in v_emp for tag in ["行业", "公司", "：", ":"]):
                            emp_count = v_emp

                    m_ind = re.search(r"公司行业[:：\s]*([^\n|│]+)", block_text)
                    if m_ind:
                        v_ind = m_ind.group(1).strip()
                        m_next_slash = re.search(r"公司行业[:：\s]*[^\n|│]+\s*\n\s*(/[^\s\t\n|│]+)", block_text)
                        if m_next_slash:
                            v_ind += m_next_slash.group(1).strip()
                        if not any(tag in v_ind for tag in ["描述", "规模", "：", ":"]):
                            industry = v_ind

                    m_sal = re.search(r"(?:薪酬情况|职位薪资|薪资)[:：\s]*([^\s\t\n|│]+)", block_text)
                    if m_sal:
                        v_sal = m_sal.group(1).strip()
                        if not any(tag in v_sal for tag in ["职责", "业绩", "：", ":"]):
                            salary = v_sal

                    if not dept:
                        m_dept = re.search(r"(?m)^\s*(?:所在部门|部门)\s*[:：]\s*([^\s|│\n\t]+)", block_text)
                        if m_dept and m_dept.group(1).strip() not in ("汇报对象：", "下属人数："):
                            dept = m_dept.group(1).strip()

                    m_pos_tag = re.search(r"(?:所任职位|职务|职位|岗位)[:：\s]*([^\s\t\n|│]+)", block_text)
                    if m_pos_tag and not any(stop in m_pos_tag.group(1) for stop in ["类别", "汇报", "职责", "考核", "配合"]):
                        position = m_pos_tag.group(1).strip()

                    if position and any(bad in position for bad in ["(", "（", "，", ",", "。", "职责", "配合", "考核", "以此", "定期"]):
                        position = ""

                    if not position:
                        for l in lines:
                            l_sub = l.strip()
                            if any(stop in l_sub for stop in ["公司规模", "公司行业", "公司描述", "所在地区", "所在部门", "汇报对象", "下属人数", "薪酬情况", "职责业绩", "职责", "描述", "业绩", "考核", "配合"]):
                                continue
                            if len(l_sub) >= 2 and len(l_sub) <= 15 and not l_sub.isdigit() and l_sub != company_name:
                                if any(title_kw in l_sub for title_kw in ["部长", "经理", "主管", "工程师", "担当", "总监", "专员", "代表", "秘书", "顾问", "ka", "组长", "技术员", "科长", "处长"]):
                                    position = l_sub
                                    break

                    if not industry or not emp_count:
                        m_ind_line = re.search(r"([\u4e00-\u9fff/]+)\s*\|\s*(\d+-\d+人|少于\s*\d+\s*人|\d+人以上|\d+人)\s*\|\s*([\u4e00-\u9fff]+)", block_text)
                        if m_ind_line:
                            if not industry: industry = m_ind_line.group(1).strip()
                            if not emp_count: emp_count = m_ind_line.group(2).strip()

                    m_resp = re.search(r"(?:工作描述|工作职责和业绩|职责业绩|主要工作|工作职责|职责描述|内容)[:：]?\s*\n?([\s\S]{5,1500}?)(?=\n\s*(?:(?:19|20)\d{2}|汇报对象|所在地区|搜索同事|更多|学历|【?项目经历】?|项目经历|\Z))", block_text)
                    if m_resp:
                        resp = m_resp.group(1).strip()
                    else:
                        resp = "\n".join(lines[1:]) if len(lines) > 1 else ""
                        
                company_name = re.sub(r"^(?:公司|单位|名称|所属单位)[:：\s]*", "", company_name).strip()
                company_name = re.sub(r"[\(（]\s*\d+\s*年\s*\d*\s*个?月?\s*[\)）]", "", company_name).strip()
                if company_name.lower() == "gap":
                    company_name = "Gap year"
                if any(noise in company_name.lower() for noise in ["【工作内容】", "工作内容", "仕事内容", "工作描述", "主要职责", "大项目", "成功切换", "抑制剂", "合成与评估", "课题", "论文", "项目经历", "项目经验", "成本递减"]):
                    company_name = ""

                if position and any(bad in position for bad in ["(", "（", "，", ",", "。", "职责", "配合", "考核", "以此", "定期"]):
                    position = ""
                        
                works.append({
                    "company_name": company_name,
                    "company_employees": emp_count,
                    "company_industry": industry,
                    "position": position or "担当",
                    "position_type": "",
                    "position_salary": salary,
                    "position_dept": dept,
                    "position_report_to": report_to,
                    "position_subordinate": subordinate,
                    "employment_type": "全职",
                    "annual_salary_min": "",
                    "annual_salary_max": "",
                    "status": "在职" if end_p in ("至今", "现在", "目前", "Present", "今迄", "現在") else "离职",
                    "position_start": start_p,
                    "position_resigned": "" if end_p in ("至今", "现在", "目前", "Present", "今迄", "現在") else end_p,
                    "resigned_reason": "",
                    "position_responsibilities": resp[:800]
                })
        return sorted([w for w in works if w["company_name"] and not w["company_name"].isdigit()], key=lambda x: x.get("position_start", ""), reverse=True)

    def _extract_education_list(self, text: str, lang: str, raw_html: str = "") -> list[dict[str, Any]]:
        edus = []
        html_source = raw_html if raw_html else text
        
        # 1. 优先使用 DOM 节点抓取（针对猎聘/智联等 HTML 格式简历）
        # EN: 1. Prefer DOM node extraction (for HTML-format résumés such as Liepin/Zhaopin)
        # JA: 1. DOM ノードからの取得を優先する（Liepin／Zhaopin などの HTML 形式の履歴書向け）
        if HAS_BS4 and ("<html" in html_source.lower() or "<table" in html_source.lower() or "<tr" in html_source.lower()):
            try:
                soup = BeautifulSoup(html_source, "html.parser")
                edu_tr = None
                for tr in soup.find_all("tr"):
                    if "教育经历" in tr.get_text():
                        edu_tr = tr
                        break
                        
                if edu_tr:
                    curr_tr = edu_tr.find_next_sibling("tr")
                    while curr_tr:
                        txt_tr = curr_tr.get_text(strip=True)
                        if any(stop in txt_tr for stop in ["语言能力", "技能标签", "自我评价", "项目经历", "工作经历"]):
                            break
                            
                        tds = curr_tr.find_all("td")
                        if len(tds) >= 2:
                            left_txt = tds[0].get_text(strip=True)
                            right_txt = tds[1].get_text(strip=True)
                            all_cells = [td.get_text(" ", strip=True) for td in tds]
                            # 模板常见三列：学校 | 专业/学历 | 起止时间；时间不一定在第二列。
                            # EN: Templates often have three columns: school | major/degree | start-end; the dates are not always in the second column.
                            # JA: テンプレートは「学校 | 専攻／学歴 | 期間」の 3 列が多いが、期間が 2 列目にあるとは限らない。
                            time_text = " ".join(all_cells)
                            m_time = re.search(r"((?:19|20)\d{2}[\.\/年-]\d{1,2})\s*[-—–~∼～\-./~〜ー]{1,5}\s*((?:19|20)\d{2}[\.\/年-]\d{1,2})", time_text)
                            if m_time and left_txt:
                                start_ym = self._format_date(m_time.group(1))
                                end_ym = self._format_date(m_time.group(2))
                                
                                # 三列模板直接取前两列，避免把“专业/学历”当成学校。
                                # EN: For three-column templates take the first two columns directly, so "major/degree" is not taken as the school.
                                # JA: 3 列のテンプレートでは先頭の 2 列をそのまま取り、「専攻／学歴」を学校と誤認しないようにする。
                                if len(tds) >= 3 and re.search(r"(?:19|20)\d{2}", all_cells[-1]):
                                    school = left_txt
                                    rem = right_txt
                                    degree = ""
                                    for dkw in ["硕士", "本科", "大专", "博士", "学士", "研究生"]:
                                        if dkw in rem:
                                            degree = dkw
                                            break
                                    major = re.sub(r"[\s·]*(?:硕士|本科|大专|博士|学士|研究生|统招|全日制)+[\s·]*", " ", rem).strip()
                                    deg_rank = "4"
                                    for rank_val, keywords in EDUCATION_RANKS_ORDERED:
                                        if any(kw in (degree or rem) for kw in keywords):
                                            deg_rank = rank_val
                                            break
                                    edus.append({
                                        "school_name": school,
                                        "school_major_name": major,
                                        "school_degree_type": degree or ("硕士" if deg_rank == "5" else "本科"),
                                        "school_degree_rank": deg_rank,
                                        "school_education_type": EDUCATION_TYPE_MAP.get(deg_rank, "全日制大学"),
                                        "school_start_ym": self._format_date(m_time.group(1)),
                                        "school_end_ym": self._format_date(m_time.group(2)),
                                    })
                                    curr_tr = curr_tr.find_next_sibling("tr")
                                    continue

                                # 猎聘 HTML：学校名与专业在同一 TD，用双空格分隔
                                # 例如: "中国计量大学  检测技术与自动化装置·硕士·统招"
                                # EN: Liepin HTML: the school name and major are in the same TD, separated by a double space
                                #     e.g.: "中国计量大学  检测技术与自动化装置·硕士·统招"
                                # JA: Liepin の HTML：学校名と専攻が同じ TD にあり、2 つの空白で区切られている
                                #     例："中国计量大学  检测技术与自动化装置·硕士·统招"
                                parts_by_space = [p.strip() for p in re.split(r"\s{2,}", left_txt) if p.strip()]
                                clean_t = parts_by_space[0] if parts_by_space else left_txt.strip()
                                rem_part = parts_by_space[1] if len(parts_by_space) > 1 else ""
                                school, major, degree = "", "", ""
                                
                                m_sch = re.search(r"^(.*?[\u4e00-\u9fff]+(?:大学|学院|学校|高中|专科学校|职业技术学院|研究院))(.*)$", clean_t)
                                if m_sch:
                                    school = m_sch.group(1).strip()
                                    rem = (m_sch.group(2) + " " + rem_part).strip()
                                else:
                                    school = clean_t
                                    rem = rem_part
                                    
                                # 从 rem 中拆出学位和专业
                                # EN: Split the degree and major out of rem
                                # JA: rem から学位と専攻を切り出す
                                for dkw in ["硕士", "本科", "大专", "博士", "学士"]:
                                    if dkw in rem:
                                        degree = dkw
                                        break
                                rem = re.sub(r"[\s·]*(?:硕士|本科|大专|博士|学士|统招|全日制)+[\s·]*", " ", rem).strip()
                                major = rem.strip()
                                
                                deg_rank = "4"
                                for rank_val, keywords in EDUCATION_RANKS_ORDERED:
                                    if any(kw in (degree or left_txt) for kw in keywords):
                                        deg_rank = rank_val
                                        break
                                
                                edus.append({
                                    "school_name": school,
                                    "school_major_name": major,
                                    "school_degree_type": degree or ("硕士" if deg_rank=="5" else "本科"),
                                    "school_degree_rank": deg_rank,
                                    "school_education_type": EDUCATION_TYPE_MAP.get(deg_rank, "全日制大学"),
                                    "school_start_ym": start_ym,
                                    "school_end_ym": end_ym
                                })
                        curr_tr = curr_tr.find_next_sibling("tr")
                        
                if edus:
                    return sorted(edus, key=lambda x: (int(x.get("school_degree_rank", "1")), x.get("school_end_ym", "")), reverse=True)

                # 1b. <p> 段落格式教育经历（日语 Word 简历）
                # 格式: <p>2022.03 - 2023.04    本科   上海外国語大学  　日本語</p>
                # EN: 1b. <p> paragraph-format education history (Japanese Word résumés)
                #     Format: <p>2022.03 - 2023.04    本科   上海外国語大学  　日本語</p>
                # JA: 1b. <p> 段落形式の学歴（日本語の Word 履歴書）
                #     形式：<p>2022.03 - 2023.04    本科   上海外国語大学  　日本語</p>
                EDU_STOPS = ["勤務履歴", "勤務歴", "仕事経験", "個人PR", "個人 PR", "趣味", "자기소개"]
                p_tags_all = [p for p in soup.find_all("p") if p.get_text(strip=True)]
                
                edu_sec_start_idx = -1
                edu_sec_end_idx = len(p_tags_all)
                for idx, p in enumerate(p_tags_all):
                    t = p.get_text(strip=True)
                    if any(kw in t for kw in ["学歴関係", "学歴", "学历", "Education", "教育背景"]):
                        if not any(stop in t for stop in ["最高学历", "学历要求"]):
                            edu_sec_start_idx = idx + 1
                    elif edu_sec_start_idx > -1 and any(stop in t for stop in EDU_STOPS):
                        edu_sec_end_idx = idx
                        break

                if edu_sec_start_idx > -1:
                    EDU_TIME_PAT = re.compile(
                        r"((?:19|20)\d{2}[.\-/年]\d{1,2})\s*[-—–~∼～　\s]{0,5}\s*((?:19|20)\d{2}[.\-/年]\d{1,2})"
                    )
                    DEGREE_MAP_JP = {
                        "博士": ("博士", "6"), "修士": ("硕士", "5"), "硕士": ("硕士", "5"),
                        "本科": ("本科", "4"), "学士": ("本科", "4"), "大学": ("本科", "4"),
                        "短期大学": ("大专", "3"), "大专": ("大专", "3"), "専門": ("大专", "3"),
                        "高中": ("高中", "2"), "高校": ("高中", "2"),
                    }
                    for p in p_tags_all[edu_sec_start_idx:edu_sec_end_idx]:
                        t = p.get_text(strip=True)
                        m_t = EDU_TIME_PAT.search(t)
                        if not m_t:
                            continue
                        start_ym = self._format_date(m_t.group(1))
                        end_ym = self._format_date(m_t.group(2))
                        
                        rest = t[m_t.end():].strip()
                        # rest 格式: "   本科   上海外国語大学  　日本語"
                        # EN: rest format: "   本科   上海外国語大学  　日本語"
                        # JA: rest の形式："   本科   上海外国語大学  　日本語"
                        parts = [x.strip() for x in re.split(r"[\s\t　]{2,}", rest) if x.strip()]
                        
                        degree_type, deg_rank = "本科", "4"
                        school, major = "", ""
                        
                        for pt in parts:
                            matched_deg = False
                            # 含省/市/区/国 等地名特征 → 一定是学校名，不是学位词
                            # EN: Contains place-name features such as province/city/district/country → definitely a school name, not a degree word
                            # JA: 省／市／区／国などの地名の特徴を含む → 必ず学校名であり、学位の語ではない
                            is_school_name = any(loc in pt for loc in ["省", "市", "区", "县", "自治", "国", "大学院"])
                            if not is_school_name:
                                for kw, (dname, drank) in DEGREE_MAP_JP.items():
                                    # kw 必须完全等于 pt，或者 pt 就是纯学位词（≤4字）
                                    # EN: kw must equal pt exactly, or pt must be a pure degree word (≤4 characters)
                                    # JA: kw が pt と完全に一致するか、pt が純粋な学位の語（4 文字以内）であること
                                    if pt == kw or (kw in pt and len(pt) <= 4):
                                        degree_type, deg_rank = dname, drank
                                        matched_deg = True
                                        break
                            if not matched_deg:
                                if not school:
                                    school = pt
                                elif not major:
                                    major = pt

                        
                        if school:
                            edus.append({
                                "school_name": school,
                                "school_major_name": major,
                                "school_degree_type": degree_type,
                                "school_degree_rank": deg_rank,
                                "school_education_type": EDUCATION_TYPE_MAP.get(deg_rank, "全日制大学"),
                                "school_start_ym": start_ym,
                                "school_end_ym": end_ym
                            })
                    if edus:
                        return sorted(edus, key=lambda x: (int(x.get("school_degree_rank", "1")), x.get("school_end_ym", "")), reverse=True)
            except Exception:
                pass
        
        # 表单型中文简历：日期、学校、学历、专业分行排列，且学校名不一定带“大学/学院”。
        # 例如：2009/9-2012/6\n黑龙江农业工程\n大专\n|\n制造工程。
        # EN: Form-style Chinese résumés: date, school, degree and major are on separate lines, and the school name does not necessarily include "大学/学院".
        #     e.g.: 2009/9-2012/6\n黑龙江农业工程\n大专\n|\n制造工程.
        # JA: フォーム形式の中国語履歴書：日付・学校・学歴・専攻が別々の行に並び、学校名に「大学／学院」が付くとは限らない。
        #     例：2009/9-2012/6\n黑龙江农业工程\n大专\n|\n制造工程。
        m_form_edu = re.search(
            r"教育经历\s*([\s\S]{0,1800}?)(?=技能特长|工作经验|工作经历|项目经历|语言能力|$)",
            text,
            re.IGNORECASE,
        )
        if m_form_edu:
            form_sec = m_form_edu.group(1)
            form_lines = [line.strip(" \t\r\n|") for line in form_sec.splitlines() if line.strip(" \t\r\n|")]
            date_re = re.compile(r"((?:19|20)\d{2}[./年-]\d{1,2})\s*[-—–~～至到－]+\s*((?:19|20)\d{2}[./年-]\d{1,2})")
            idx = 0
            while idx < len(form_lines):
                dm = date_re.search(form_lines[idx])
                if not dm and idx + 1 < len(form_lines):
                    dm = re.search(rf"((?:19|20)\d{{2}}[./年-]\d{{1,2}})\s*[-—–~～至到－]*$", form_lines[idx])
                    if dm and re.fullmatch(r"(?:19|20)\d{2}[./年-]\d{1,2}", form_lines[idx + 1]):
                        end_raw = form_lines[idx + 1]
                        dm = re.match(rf"({dm.group(1)})", form_lines[idx])
                        start_raw = dm.group(1) if dm else ""
                        end_raw = end_raw
                        date_start_idx = idx
                        idx += 2
                    else:
                        idx += 1
                        continue
                elif dm:
                    start_raw, end_raw, date_start_idx = dm.group(1), dm.group(2), idx
                    idx += 1
                else:
                    idx += 1
                    continue
                if not dm:
                    continue
                # 下一行学校、再下一行学历、随后是专业；跳过“专业描述”标签及其内容。
                # EN: The next line is the school, the one after that the degree, then the major; skip the "专业描述" (major description) label and its content.
                # JA: 次の行が学校、その次が学歴、続いて専攻。「专业描述」（専攻の説明）のラベルとその内容はスキップする。
                rest = form_lines[idx:idx + 8]
                if not rest:
                    continue
                school = rest[0]
                degree = next((x for x in rest[1:4] if any(k in x for k in ["博士", "硕士", "研究生", "本科", "学士", "大专", "专科", "高中"])), "")
                degree_idx = rest.index(degree) if degree in rest else 1
                major = next((x for x in rest[degree_idx + 1:] if x and not x.startswith("专业描述")), "")
                if school and not any(stop in school for stop in ["学校", "学历", "专业", "时间"]):
                    rank = "4"
                    for rank_val, keywords in EDUCATION_RANKS_ORDERED:
                        if any(k in (degree or school) for k in keywords):
                            rank = rank_val
                            break
                    edus.append({
                        "school_name": school,
                        "school_major_name": major,
                        "school_degree_type": degree or ("本科" if rank == "4" else ""),
                        "school_degree_rank": rank,
                        "school_education_type": EDUCATION_TYPE_MAP.get(rank, ""),
                        "school_start_ym": self._format_date(start_raw),
                        "school_end_ym": self._format_date(end_raw),
                    })
                idx += max(1, len(rest[:4]))
            if edus:
                return sorted(edus, key=lambda x: x.get("school_end_ym", ""), reverse=True)

        m_jp_edu = re.search(r"(?:卒業学校|卒業校)\s*[:：\s]*([^\n]+)", text)
        if m_jp_edu:
            line_str = m_jp_edu.group(1).strip()
            parts = [p.strip() for p in re.split(r"\s+", re.sub(r"（[^）]*）|\([^)]*\)", "", line_str)) if p.strip()]
            school = parts[0] if len(parts) >= 1 else ""
            major = parts[1] if len(parts) >= 2 else ""

            if re.search(r"修士|大学院", line_str):
                degree_type, deg_rank = "硕士", "5"
            elif re.search(r"博士", line_str):
                degree_type, deg_rank = "博士", "6"
            else:
                degree_type, deg_rank = "学士", "4"

            m_year = re.search(r"((?:19|20)\d{2})年(\d{1,2})月", line_str)
            if m_year:
                end_ym = f"{m_year.group(1)}年{int(m_year.group(2)):02d}月01日"
                study_years = 4 if deg_rank == "4" else 2
                start_ym = f"{int(m_year.group(1)) - study_years}年09月01日"
            else:
                end_ym = ""
                start_ym = ""

            edus.append({
                "school_name": school,
                "school_major_name": major,
                "school_degree_type": degree_type,
                "school_degree_rank": deg_rank,
                "school_education_type": EDUCATION_TYPE_MAP.get(deg_rank, "全日制大学"),
                "school_start_ym": start_ym,
                "school_end_ym": end_ym
            })

            m_exchange = re.search(
                r"交換留学\s*[:：\s]*((?:19|20)\d{2}[./]\d{1,2})\s*[-～〜]+\s*((?:19|20)\d{2}[./]\d{1,2})\s*([^\n]+)",
                text
            )
            if m_exchange:
                ex_start = self._format_date(m_exchange.group(1))
                ex_end = self._format_date(m_exchange.group(2))
                ex_school = re.sub(r"（[^）]*）|\([^)]*\)", "", m_exchange.group(3)).strip().split()[0]
                edus.append({
                    "school_name": ex_school,
                    "school_major_name": "交換留学",
                    "school_degree_type": "交換生",
                    "school_degree_rank": "4",
                    "school_education_type": "全日制大学",
                    "school_start_ym": ex_start,
                    "school_end_ym": ex_end
                })
            return sorted(edus, key=lambda x: (int(x.get("school_degree_rank", "1")), x.get("school_end_ym", "")), reverse=True)

        pattern = re.compile(r"((?:19|20)\d{2}[\.\/\-年]\d{1,2})\s*[-—–~∼～\u2014\u2013\uff0d¡£`\-./\ufffd~〜ー\s]{1,5}\s*((?:19|20)\d{2}[\.\/\-年]\d{1,2}|至今|现在|目前|Present)", re.IGNORECASE)
        m_head = None
        for m in re.finditer(r"(?:教育经历|教育背景|学歴|Education)", text, re.IGNORECASE):
            line_str = text[max(0, m.start()-10):m.end()+10].splitlines()[0] if text[max(0, m.start()-10):m.end()+10].splitlines() else ""
            if not any(stop in line_str for stop in ["最高学历", "学历/学位", "教育程度", "学历："]):
                m_head = m
                break
        if not m_head:
            m_head = re.search(r"(?:教育经历|教育背景|学歴|学\s*历|Education)", text, re.IGNORECASE)
        if m_head:
            sec_start = m_head.end()
            m_next = re.search(r"\n\s*(?:工作经验|工作经历|職歴|仕事经验|履历|经\s*历|【?工作地点】?|项目经历|项目经验|【?项目经历】?|【?项目经验】?|外语水平|计算机水平|语言|技能|Education|打工经历|奖惩情况|研究经历|自我评价|自己アピール|附加信息|\Z)", text[sec_start:], re.IGNORECASE)
            sec_end = sec_start + m_next.start() if m_next else len(text)
            sec = text[sec_start:sec_end]
            
            matches = list(pattern.finditer(sec))
            for i, match in enumerate(matches):
                start_p = self._format_date(match.group(1))
                end_p = match.group(2)
                if end_p not in ("至今", "现在", "目前", "Present"):
                    end_p = self._format_date(end_p)

                prev_text = sec[:match.start()].strip()
                prev_line_prefix = prev_text.splitlines()[-1].strip() if prev_text.splitlines() else ""
                
                block_start = match.end()
                block_end = matches[i+1].start() if i+1 < len(matches) else len(sec)
                block_text = sec[block_start:block_end].strip()

                school = ""
                major = ""
                degree = ""

                if prev_line_prefix:
                    p_clean = prev_line_prefix.strip()
                    p_clean = re.sub(r"^[*\-•\d\.\s]+", "", p_clean).strip()
                    if len(p_clean) <= 30 and not any(kw in p_clean for kw in ["教育经历", "教育背景", "学历", "教育程度"]):
                        if not any(noise in p_clean for noise in ["访问", "会议", "交流", "项目", "公司", "工程师", "经理", "主管", "专员", "原因", "年份", "成绩", "评价", "职责", "描述", "经历"]):
                            school = p_clean
                        elif any(good in p_clean for good in ["大学", "学院", "学校", "高中", "中学", "理工"]):
                            school = p_clean

                after_text = " ".join([l.strip() for l in block_text.splitlines()[:2] if l.strip()])
                after_clean = re.sub(r"[\xa0\s|│]+", " ", after_text).strip()
                after_parts = [p.strip() for p in after_clean.split(" ") if p.strip()]

                for p in after_parts:
                    p_clean = re.sub(r"^(?:专业|專門|学历|学歴|学位)[:：\s]*", "", p).strip()
                    if not p_clean: continue

                    if not school and any(skw in p_clean for skw in ["大学", "学院", "学校", "高中", "中学"]):
                        school = p_clean
                    elif any(dkw in p_clean for dkw in ["本科", "学士", "硕士", "大专", "高中", "中学", "博士", "研究生"]):
                        if not degree:
                            degree = p_clean
                    elif not major and p_clean != school and p_clean != degree:
                        major = p_clean

                if not school and prev_text:
                    lines_before = [l.strip() for l in prev_text.splitlines() if l.strip()]
                    if lines_before:
                        last_l = lines_before[-1]
                        if not any(kw in last_l for kw in ["教育经历", "教育背景", "学历"]):
                            if not any(noise in last_l for noise in ["项目", "公司", "原因", "年份"]):
                                school = last_l

                school = re.sub(r"^(?:学校|名称|毕业院校)[:：\s]*", "", school).strip()
                major = re.sub(r"^(?:专业|专线|主修)[:：\s]*", "", major).strip()
                degree = re.sub(r"^(?:学历|学位)[:：\s]*", "", degree).strip()
                
                deg_rank = "4"
                for rank_val, keywords in EDUCATION_RANKS_ORDERED:
                    found = False
                    for kw in keywords:
                        if kw in degree or kw in block_text:
                            deg_rank = rank_val
                            if not degree: degree = kw
                            found = True
                            break
                    if found:
                        break
                        
                edu_type = EDUCATION_TYPE_MAP.get(deg_rank, "全日制大学")
                        
                edus.append({
                    "school_name": school,
                    "school_major_name": major,
                    "school_degree_type": degree or ("学士" if deg_rank=="4" else "本科"),
                    "school_degree_rank": deg_rank,
                    "school_education_type": edu_type,
                    "school_start_ym": start_p,
                    "school_end_ym": end_p
                })
        return sorted(edus, key=lambda x: (int(x.get("school_degree_rank", "1")), x.get("school_end_ym", "")), reverse=True)

    def _build_current_info(self, work_experiences: list[dict[str, Any]]) -> dict[str, Any]:
        if work_experiences:
            w = work_experiences[0]
            return {
                "company_name": w.get("company_name", ""),
                "company_employees": w.get("company_employees", ""),
                "company_industry": w.get("company_industry", ""),
                "position": w.get("position", ""),
                "position_type": w.get("position_type", ""),
                "position_salary": w.get("position_salary", ""),
                "position_dept": w.get("position_dept", ""),
                "position_report_to": w.get("position_report_to", ""),
                "position_subordinate": w.get("position_subordinate", ""),
                "employment_type": w.get("employment_type", "全职"),
                "annual_salary_min": w.get("annual_salary_min", ""),
                "annual_salary_max": w.get("annual_salary_max", ""),
                "status": w.get("status", "在职"),
                "position_start": w.get("position_start", ""),
                "position_resigned": w.get("position_resigned", "")
            }
        return self._build_empty_current_info()

    def _build_empty_current_info(self) -> dict[str, Any]:
        return {
            "company_name": "", "company_employees": "", "company_industry": "",
            "position": "", "position_type": "", "position_salary": "",
            "position_dept": "", "position_report_to": "", "position_subordinate": "",
            "employment_type": "全职", "annual_salary_min": "", "annual_salary_max": "",
            "status": "", "position_start": "", "position_resigned": ""
        }

    def _build_highest_education_info(self, education_list: list[dict[str, Any]]) -> dict[str, Any]:
        if education_list:
            sorted_edus = sorted(education_list, key=lambda x: (int(x.get("school_degree_rank", "1")), x.get("school_end_ym", "")), reverse=True)
            top = sorted_edus[0]
            return {
                "school_name": top.get("school_name", ""),
                "school_major_name": top.get("school_major_name", ""),
                "school_degree_type": top.get("school_degree_type", ""),
                "school_degree_rank": top.get("school_degree_rank", "4"),
                "school_education_type": top.get("school_education_type", "全日制大学"),
                "school_start_ym": top.get("school_start_ym", ""),
                "school_end_ym": top.get("school_end_ym", "")
            }
        return self._build_empty_education_info()

    def _build_empty_education_info(self) -> dict[str, Any]:
        return {
            "school_name": "", "school_major_name": "", "school_degree_type": "",
            "school_degree_rank": "", "school_education_type": "",
            "school_start_ym": "", "school_end_ym": ""
        }

    def _extract_certificates(self, text: str) -> list[dict[str, Any]]:
        certs = []
        seen = set()

        # 必须显示定位到证书版块，避免全文搜索将简历下载时间/工作年限误识别为证书
        # EN: Must explicitly locate the certificate section, so a full-text search does not mistake the résumé download time / years of work for certificates
        # JA: 資格欄を明示的に特定する必要がある。全文検索で履歴書のダウンロード日時や勤続年数を資格と誤認しないため
        m = re.search(r"(?:\|?\s*证书|资格证书|Certifications|资质认证|获得证书)\s*[:：\t\n\s]*([\s\S]{3,600}?)(?=\n\s*(?:\|?\s*语言能力|\|?\s*技能|\|?\s*自我评价|\|?\s*项目经历|\|?\s*工作经历|\Z))", text, re.IGNORECASE)
        if m:
            sec_txt = m.group(1).strip()
            lines = [l.strip() for l in sec_txt.splitlines() if l.strip()]
            for l in lines:
                l_clean = re.sub(r"^[*\-•\d\.\s▲\u25b2]+", "", l).strip()
                l_clean = re.sub(r"<[^>]+>", "", l_clean).strip()
                if not l_clean: continue

                # 排除过滤
                # EN: Exclusion filter
                # JA: 除外フィルター
                if any(bad in l_clean for bad in ["15:", "16:", "(8年)", "(1年", "(3个", "年11", "知识资产", "声明：", "</p>", "</td>", "操作时间"]):
                    continue
                # “技能特长（包括IT技能、语言能力、证书、成绩、培训经历）”是说明文字，
                # 不是证书名称；不能把其尾部“、成绩、培训经历）”入库。
                # EN: "技能特长（包括IT技能、语言能力、证书、成绩、培训经历）" is explanatory text,
                #     not a certificate name; its tail "、成绩、培训经历）" must not be stored.
                # JA: 「技能特长（包括IT技能、语言能力、证书、成绩、培训经历）」は説明文であり資格名ではない。
                #     末尾の「、成绩、培训经历）」を登録してはならない。
                if ("成绩" in l_clean and "培训经历" in l_clean) or "包括IT技能" in l_clean:
                    continue

                m_item = re.search(r"((?:19|20)\d{2}[\./\-年-]{1,5}\d{1,2}月?)\s*[:：\s]*([^\n]+)", l_clean)
                if m_item:
                    c_time = self._format_date(m_item.group(1).strip())
                    c_name = m_item.group(2).strip()
                    c_name = re.sub(r"^.*(?:学校|学院|中心|公司)\s*", "", c_name).strip()
                    if c_name and c_name not in seen and len(c_name) <= 25 and not any(stop in c_name for stop in ["培训", "机构", "地点"]):
                        seen.add(c_name)
                        certs.append({
                            "certificate_name": c_name,
                            "certificate_tpye": "证书",
                            "certificate_time": c_time
                        })
                else:
                    if len(l_clean) <= 25 and len(l_clean) >= 2 and l_clean not in seen:
                        seen.add(l_clean)
                        certs.append({
                            "certificate_name": l_clean,
                            "certificate_tpye": "证书",
                            "certificate_time": ""
                        })

        # 常规名企/国家权威证书保底匹配
        # EN: Fallback matching of common certificates from well-known companies / national authorities
        # JA: 有名企業・国家機関の一般的な資格に対する最終手段のマッチング
        for cert_kw in ["PMP", "信息系统项目管理师", "二级建造师", "一级建造师", "CMMI5"]:
            if cert_kw in text and cert_kw not in seen:
                seen.add(cert_kw)
                certs.append({
                    "certificate_name": cert_kw,
                    "certificate_tpye": "证书",
                    "certificate_time": ""
                })

        return certs

    def _normalize_certificates(self, certs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        seen = set()
        generic = {"certificates", "certificate", "证书", "荣誉证书", "资格证书"}
        for item in certs or []:
            row = dict(item)
            name = re.sub(r"^[\s\(（\)）】】、,，;；.。]+", "", str(row.get("certificate_name", ""))).strip()
            name = re.sub(r"[；;，,。]+$", "", name).strip()
            if not name or name.casefold() in generic or ("成绩" in name and "培训经历" in name):
                continue
            # 从“英语CET-6级，良好的听说写能力”中只保留证书主体。
            # EN: From "英语CET-6级，良好的听说写能力" (English CET-6, good listening/speaking/writing) keep only the certificate itself.
            # JA: 「英语CET-6级，良好的听说写能力」（英語 CET-6、聞く・話す・書く力が良好）から資格本体だけを残す。
            if re.search(r"英语\s*CET\s*[-]?\s*6", name, re.I):
                name = "英语CET-6"
            elif re.search(r"英语\s*CET\s*[-]?\s*4", name, re.I):
                name = "英语CET-4"
            elif "计算机二级" in name:
                name = "计算机二级"
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            row["certificate_name"] = name
            result.append(row)
        return result

    def _extract_languages(self, text: str) -> list[dict[str, Any]]:
        langs = []
        seen = set()

        m_sec = re.search(r"(?:\|?\s*语言能力|外语水平|语言水平|語学|語学能力)\s*[:：\t\n\s]*([\s\S]{3,200}?)(?=\n\s*(?:\|?\s*技能|\|?\s*自我评价|\|?\s*项目经历|\|?\s*教育经历|\Z))", text, re.IGNORECASE)
        if m_sec:
            sec_txt = m_sec.group(1).strip()
            lines = [l.strip() for l in sec_txt.splitlines() if l.strip()]
            for l in lines:
                parts = re.split(r"[,，、;\s]+", l)
                for p in parts:
                    p_clean = p.strip()
                    if not p_clean: continue
                    if any(lkw in p_clean for lkw in ["英语", "普通话", "日语", "韩语", "德语", "法语", "西班牙语", "粤语"]):
                        if p_clean not in seen:
                            seen.add(p_clean)
                            langs.append({
                                "language_name": p_clean,
                                "language_level": "熟练",
                                "language_certificate": "有",
                                "language_certificate_time": ""
                            })

        if not langs:
            m_eng = re.search(r"英\s*语\s*[:：\t\s\n]*([^\n]+)", text)
            if m_eng:
                l_val = m_eng.group(1).strip()
                if l_val:
                    langs.append({"language_name": "英语", "language_level": l_val[:20], "language_certificate": "有", "language_certificate_time": ""})

            m_n1 = re.search(r"(?:日语一級|日本語1級|JLPT N1|\bN1\b|日语国际一级|日本語能力試験N1)[^\n]*(\d{2,3}/\d{2,3}点?)?", text)
            m_n2 = re.search(r"(?:日语二级|日本語2級|JLPT N2|\bN2\b)[^\n]*(\d{2,3}/\d{2,3}点?)?", text)
            if m_n1:
                score = m_n1.group(1) or ""
                level = f"N1精通（{score}）" if score else "N1精通"
                langs.append({"language_name": "日语", "language_level": level, "language_certificate": "有", "language_certificate_time": ""})
            elif m_n2:
                score = m_n2.group(1) or ""
                level = f"N2（{score}）" if score else "N2"
                langs.append({"language_name": "日语", "language_level": level, "language_certificate": "有", "language_certificate_time": ""})

        if not langs:
            if re.search(r"英语六级|CET6|CET-6|大学英语六级", text):
                langs.append({"language_name": "英语", "language_level": "CET-6", "language_certificate": "有", "language_certificate_time": ""})
            elif re.search(r"英语四级|CET4|CET-4|大学英语四级", text):
                langs.append({"language_name": "英语", "language_level": "CET-4", "language_certificate": "有", "language_certificate_time": ""})

        return langs

    def _extract_skills(self, text: str) -> list[dict[str, Any]]:
        skills = []
        seen_names = set()

        m_tag = re.search(r"(?:\|?\s*技能标签|技能专长|IT技能|Skills|计算机水平|专业技能)\s*[:：\t\n\s]*([\s\S]{3,500}?)(?=\n\s*(?:\|?\s*自我评价|\|?\s*工作经历|\|?\s*教育经历|\|?\s*项目经历|\Z))", text, re.IGNORECASE)
        if m_tag:
            sec_txt = m_tag.group(1).strip()
            lines = [l.strip() for l in sec_txt.splitlines() if l.strip()]
            for l in lines:
                if any(stop in l for stop in ["自我评价", "工作经历", "教育经历"]): continue
                parts = re.split(r"[,，、;；\s]+", l)
                for p in parts:
                    p_name = p.strip()
                    if p_name and len(p_name) <= 20 and len(p_name) >= 2 and p_name not in seen_names:
                        if not any(noise in p_name for noise in ["工作", "评价", "描述", "经历", "招聘"]):
                            seen_names.add(p_name)
                            skills.append({
                                "skills_name": p_name,
                                "skills_level": "熟练",
                                "skills_certificate": "有"
                            })

        if re.search(r"日语一級|日本語1級|JLPT N1|\bN1\b|日语国际一级", text) and "日语国际一级" not in seen_names:
            skills.append({"skills_name": "日语国际一级", "skills_level": "熟练", "skills_certificate": "有"})
            seen_names.add("日语国际一级")

        if re.search(r"英语六级|CET6|CET-6|大学英语六级", text) and "英语六级" not in seen_names:
            skills.append({"skills_name": "英语六级", "skills_level": "熟练", "skills_certificate": "有"})
            seen_names.add("英语六级")

        return [s for s in skills if str(s.get("skills_name", "")).casefold() not in {"professional", "skills", "professional skills"}][:15]

    def _normalize_language_and_skills(self, languages: list[dict[str, Any]], skills: list[dict[str, Any]], text: str):
        """统一语言名称，并把 CET/JLPT 等语言证书从技能列表合并到语言列表。

        EN: Unify language names, and merge language certificates such as CET/JLPT from the skills list into the language list.

        JA: 言語名を統一し、CET／JLPT などの語学資格をスキル一覧から語学一覧に統合する。
        """
        lang_map = {
            "英语": "英语", "英文": "英语", "english": "英语",
            "日语": "日语", "日文": "日语", "日本語": "日语", "japanese": "日语",
            "德语": "德语", "德文": "德语", "german": "德语",
            "法语": "法语", "韩语": "韩语", "韩文": "韩语", "普通话": "普通话", "国语": "普通话",
            "粤语": "粤语", "西班牙语": "西班牙语",
        }
        normalized = []
        by_name = {}
        for item in languages or []:
            row = dict(item)
            raw_name = re.sub(r"\s+", "", str(row.get("language_name", ""))).strip()
            cert_level = ""
            m_cert = re.search(r"(?:CET\s*[-]?\s*(4|6)|英语四级|英语六级|JLPT\s*N\s*([1-5])|日语[一二三四五]级|日本語[1-5]級)", raw_name, re.IGNORECASE)
            if m_cert:
                if m_cert.group(1):
                    cert_level = f"CET-{m_cert.group(1)}"
                elif m_cert.group(2):
                    cert_level = f"N{m_cert.group(2)}"
                elif "六" in raw_name or "6" in raw_name:
                    cert_level = "CET-6"
                elif "四" in raw_name or "4" in raw_name:
                    cert_level = "CET-4"
            raw_name = re.sub(r"[（(].*?[）)]", "", raw_name).strip()
            raw_name = re.sub(r"(?:CET\s*[-]?\s*[46]|英语[四六]级|JLPT\s*N\s*[1-5]|日语[一二三四五]级|日本語[1-5]級)", "", raw_name, flags=re.IGNORECASE).strip()
            name = next((v for k, v in lang_map.items() if k.lower() in raw_name.lower()), raw_name)
            if not name:
                continue
            row["language_name"] = name
            if row.get("language_level"):
                row["language_level"] = re.sub(r"[\s√✓✔☑（）()]+", " ", str(row["language_level"])).strip(" /|")
            if cert_level and not row.get("language_level"):
                row["language_level"] = cert_level
            elif cert_level and row.get("language_level") in ("熟练", "", None):
                row["language_level"] = cert_level
            row["language_certificate"] = "有" if (row.get("language_certificate") or cert_level) else ""
            if name not in by_name:
                by_name[name] = row
                normalized.append(row)
            else:
                old = by_name[name]
                if cert_level and cert_level not in str(old.get("language_level", "")):
                    old["language_level"] = (str(old.get("language_level", "")) + "/" + cert_level).strip("/")

        # 兜底：正文提到语言证书但版块解析没有生成语言。
        # EN: Fallback: the body mentions a language certificate but section parsing produced no language.
        # JA: 最終手段：本文で語学資格に言及しているのに、セクション解析で言語が生成されなかった場合。
        if not normalized:
            for label, level in (("英语", "CET-6"), ("日语", "N1")):
                if (label == "英语" and re.search(r"英语六级|CET\s*[-]?\s*6|大学英语六级", text, re.IGNORECASE)) or (label == "日语" and re.search(r"日语一級|日本語1級|JLPT\s*N1", text, re.IGNORECASE)):
                    normalized.append({"language_name": label, "language_level": level, "language_certificate": "有", "language_certificate_time": ""})

        out_skills = []
        seen_skills = set()
        language_exam = re.compile(r"^(?:英语六级|英语四级|大学英语[四六]级|CET\s*[-]?\s*[46]|日语国际一?级|JLPT\s*N\s*[1-5])$", re.IGNORECASE)
        for item in skills or []:
            row = dict(item)
            name = re.sub(r"\s+", "", str(row.get("skills_name", ""))).strip()
            if not name or name in seen_skills or language_exam.fullmatch(name):
                continue
            seen_skills.add(name)
            row["skills_name"] = name
            out_skills.append(row)
        return normalized, out_skills[:15]
