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
    ("2", ["高中", "中专", "职高", "中学"]),
    ("1", ["初中", "小学"])
]

EDUCATION_TYPE_MAP = {
    "7": "全日制研究生",
    "6": "全日制研究生",
    "5": "全日制研究生",
    "4": "全日制大学",
    "3": "全日制大专",
    "2": "全日制高中",
    "1": "全日制初中及以下"
}

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

class CodexGeminiHtmlSchemaParser:
    """Codex 独立副本：基于 Word 导出 HTML DOM 的结构化解析器。

    该文件是 Gemini 版本的隔离副本，正式跑批只引用本类，不修改原始
    ``gemini_html_schema_parser.py``，便于两套规则并行对比。

    EN: Codex standalone copy: structured parser based on the HTML DOM exported from Word.

    This file is an isolated copy of the Gemini version; formal batch runs reference only this class and do not modify the original
    ``gemini_html_schema_parser.py``, so the two rule sets can be compared side by side.

    JA: Codex の独立コピー：Word からエクスポートした HTML DOM に基づく構造化パーサー。

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
                    "platform_resume_id": f_res["base_info"].get("platform_resume_id", ""),
                    "phone": f_res["base_info"]["phone"],
                    "email": f_res["base_info"]["email"],
                    "city": "", "nationality": "", "pr": ""
                },
                "expected_info": [],
                "work_experiences": [],
                "education_list": [],
                "certificate_list": [],
                "language_list": [],
                "skills_list": [],
                "training_list": [],
                "project_list": [],
                "communication_list": []
            }
            resumes.append(zh_placeholder)
            resumes.append(f_res)
            
            empty_base = {
                "full_name": "", "gender": "", "age": "", "birth_date": "",
                "birth_year": "", "marital_status": "", "children_status": "",
                "political_status": "", "height_cm": "", "weight_kg": "",
                "household_registration": "", "address": "", "postal_code": "",
                "platform_from": f_res["base_info"]["platform_from"],
                "platform_resume_id": f_res["base_info"].get("platform_resume_id", ""),
                "phone": f_res["base_info"]["phone"],
                "email": f_res["base_info"]["email"],
                "city": "", "nationality": "", "pr": ""
            }
            return {
                "base_info": empty_base,
                "expected_info": [],
                "current_info": self._build_empty_current_info(),
                "education_info": self._build_empty_education_info(),
                "certificate_list": [],
                "language_list": [],
                "skills_list": [],
                "training_list": [],
                "project_list": [],
                "communication_list": [],
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
            # 如果是双语简历，确保英文块的工作经历与中文块保持一致
            # EN: For bilingual résumés, make sure the English block's work history matches the Chinese block
            # JA: バイリンガルの履歴書では、英語ブロックの職歴を中国語ブロックと一致させる
            zh_block = next((b for lt, b in parsed_blocks if lt == "zh"), None)
            en_block = next((b for lt, b in parsed_blocks if lt == "en"), None)
            if zh_block and en_block:
                en_block["work_experiences"] = zh_block.get("work_experiences", []).copy()

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
                "certificate_list": zh_block.get("certificate_list", zh_block.get("certificate_info", [])),
                "language_list": zh_block.get("language_list", zh_block.get("language_info", [])),
                "skills_list": zh_block.get("skills_list", zh_block.get("skills_info", [])),
                "training_list": zh_block.get("training_list", zh_block.get("training_experiences", [])),
                "project_list": zh_block.get("project_list", []),
                "communication_list": zh_block.get("communication_list", []),
                "resumes": resumes
            }

    def _split_language_blocks(self, text: str) -> list[tuple[str, str]]:
        """智能拆分中文与日文/英文双语板块

        EN: Smartly split Chinese and Japanese/English bilingual blocks

        JA: 中国語と日本語・英語の言語ブロックを賢く分割する
        """
        m_jp = re.search(r"\n\s*(?:日语简历|日語简历|日語|日本語|履歴書|職務経歴書)", text)
        m_en = re.search(r"\n\s*(?:英文简历|English Resume|Curriculum Vitae|Resume\s*\(English\)|Resume\b|\bWork Experience\b)", text, re.IGNORECASE)
        
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

    @staticmethod
    def _filename_identity(filename: str) -> tuple[str, str, str]:
        """Extract the identity fields encoded by exported platform filenames."""
        stem = Path(str(filename or "")).stem.strip()
        if not stem:
            return "", "", ""

        stem_clean = re.sub(r"__[a-f0-9]{8,12}$", "", stem, flags=re.I)

        # 1. 51job / 智联 / 猎聘标准导出模式：
        # 51job_徐杰_81481025
        # 51job_严振海_305316250_渠道饮料食品_日语销售
        # 51job_Vincent_归效_322289066
        # EN: 1. Standard 51job / Zhaopin / Liepin export pattern (file names like 51job_<name>_<id>, 51job_<name>_<id>_<job>, 51job_<English name>_<name>_<id>):
        # JA: 1. 51job / Zhaopin / Liepin の標準エクスポート形式（ファイル名は 51job_<氏名>_<ID>、51job_<氏名>_<ID>_<職種>、51job_<英語名>_<氏名>_<ID> など）：
        m1 = re.match(
            r"^(?:51job|前程无忧|智联|智联招聘|猎聘|猎聘网)[_\-\s]+"
            r"(?P<name>[^\s_]+?)[_\-\s]+"
            r"(?P<resume_id>\d{5,15})(?:[_\-].*)?$",
            stem_clean,
            re.I
        )
        if m1:
            raw_name = m1.group("name")
            resume_id = m1.group("resume_id")
            m_cn = re.search(r"[\u4e00-\u9fff]{2,4}", raw_name)
            clean_name = m_cn.group(0) if m_cn else raw_name
            return clean_name, resume_id, "前程无忧(51job)"

        # 2. 带括号 ID 模式：无忧精英网_陆蕾(1603330527)
        # EN: 2. Pattern with an ID in brackets: <site name>_<name>(<id>)
        # JA: 2. 括弧付き ID の形式：<サイト名>_<氏名>(<ID>)
        m2 = re.match(
            r"^(?:无忧精英网|无忧|前程无忧|51job)[_\-\s]*"
            r"(?P<name>[\u4e00-\u9fffA-Za-z]+)\((?P<resume_id>[A-Za-z0-9_-]{3,80})\)$",
            stem_clean,
            re.I
        )
        if m2:
            return m2.group("name"), m2.group("resume_id"), "前程无忧(51job)"

        # 3. 猎聘网格式
        # EN: 3. Liepin format
        # JA: 3. Liepin の形式
        m3 = re.match(r"^(?P<name>[\u4e00-\u9fff]{2,4})(?P<resume_id>[A-Za-z0-9]{6,80}-)(?P<rest>.+)$", stem_clean)
        if m3:
            return m3.group("name"), m3.group("resume_id").rstrip("-"), "猎聘网"

        # 4. 保底提取 ID 与 姓名
        # EN: 4. Fallback extraction of ID and name
        # JA: 4. ID と氏名の最終手段による抽出
        m_id = re.search(r"[_\-\(](\d{6,12})[\_\-\)]?", stem_clean)
        resume_id = m_id.group(1) if m_id else ""

        parts = stem_clean.split("_")
        name = ""
        for p in parts:
            if p.lower() in ("51job", "前程无忧", "智联", "猎聘") or p.isdigit():
                continue
            m_c = re.search(r"[\u4e00-\u9fff]{2,4}", p)
            if m_c:
                name = m_c.group(0)
                break
            elif len(p) <= 15:
                name = p
                break

        return name, resume_id, "前程无忧(51job)"

    def _parse_single_block(self, text: str, lang: str, filename: str, source_path: str, raw_html: str = "") -> dict[str, Any]:
        filename_name, filename_resume_id, filename_platform = self._filename_identity(filename)
        
        # 提取姓名：优先 DOM / 正文高精提取 (len >= 2) -> 备选文件名提取
        # EN: Extract the name: prefer high-precision DOM / body extraction (len >= 2) -> fall back to the file name
        # JA: 氏名の抽出：DOM・本文からの高精度抽出（len >= 2）を優先 -> 代替はファイル名から
        full_name = self._extract_name(text, filename, source_path, raw_html=raw_html)
        if not full_name or len(full_name) < 2 or full_name in {"目前", "其他", "未知候选人", "未知", "简历", "51job", "智联招聘", "前程无忧"}:
            if filename_name and len(filename_name) >= 2:
                full_name = filename_name
            elif filename_name and len(filename_name) == 1:
                # 针对类似于 徐_81481025.doc 单字姓氏，尝试从正文中匹配 姓 + 名
                # EN: For single-character surnames like <surname>_<id>.doc, try matching surname + given name in the body
                # JA: <姓>_<ID>.doc のような 1 文字の姓の場合、本文から姓 + 名のマッチを試みる
                m_sub = re.search(rf"{filename_name}([\u4e00-\u9fff]{{1,3}})", text or raw_html)
                if m_sub and len(m_sub.group(0)) >= 2:
                    full_name = m_sub.group(0)

        # 提取平台 ID：优先正文 (ID:\d+) -> 备选文件名中的 ID
        # EN: Extract the platform ID: prefer the body (ID:\d+) -> fall back to the ID in the file name
        # JA: プラットフォーム ID の抽出：本文（ID:\d+）を優先 -> 代替はファイル名中の ID
        m_txt_id = re.search(r"\(?\s*ID\s*[:：\s]*(\d{5,15})\s*\)?", raw_html or text, re.I)
        platform_resume_id = m_txt_id.group(1) if m_txt_id else filename_resume_id

        gender = self._extract_gender(text)
        birth_date, birth_year, age = self._extract_birth(text)
        marital, children = self._extract_marital_and_children(text)
        phone = self._extract_phone(text)
        email = self._extract_email(text)
        city, address = self._extract_city_and_address(text)
        pr = self._extract_pr(text)
        platform_from = filename_platform or self._detect_platform(text, filename)
        
        height_cm = self._extract_pattern(text, r"(?:身\s*高|身長)\s*[:：\t\s\n]*(\d{2,3})(?:cm)?")
        weight_kg = self._extract_pattern(text, r"(?:体\s*重|体重)\s*[:：\t\s\n]*(\d{2,3})(?:kg)?")
        h_reg = self._extract_pattern(text, r"(?:户口所在地|户籍|籍贯|戸籍|出身地)\s*[:：\t\s\n]*([^\n\t]+)")
        
        expected_info = self._extract_expected_info(text)
        work_experiences = self._filter_work_experiences(
            self._extract_work_experiences(text, lang, raw_html=raw_html)
        )
        education_list = self._extract_education_list(text, lang, raw_html=raw_html)
        education_list = self._filter_education_entries(education_list, work_experiences)
        certificate_info = self._normalize_certificates(self._extract_certificates(text))
        language_info = self._extract_languages(text)
        skills_info = self._extract_skills(text)
        language_info, skills_info = self._normalize_language_and_skills(language_info, skills_info, text)
        certificate_info, language_info = self._separate_language_certificates(certificate_info, language_info)
        
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
            "platform_resume_id": platform_resume_id,
            "phone": phone or "",
            "email": email or "",
            "city": city,
            "nationality": "",
            "pr": pr
        }
        
        training_experiences = self._extract_training_experiences(text)

        return {
            "resume_languge": lang,
            "base_info": base_info,
            "expected_info": expected_info,
            "work_experiences": work_experiences,
            "education_list": education_list,
            "certificate_list": certificate_info,
            "language_list": language_info,
            "skills_list": skills_info,
            "training_list": training_experiences,
            "project_list": [],  # TODO: 添加 _extract_project_list 方法
            # EN: TODO: add an _extract_project_list method
            # JA: TODO: _extract_project_list メソッドを追加する
            "communication_list": []
        }

    def _separate_language_certificates(self, certificate_info: list[dict[str, Any]], language_info: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """将误混入专业证书列表中的语言类证书（如日语一级、J.TEST、CET-4、CET-6、英语四六级等）精准剥离，归入语言能力列表。

        EN: Precisely strip language certificates mixed into the professional certificate list (e.g. Japanese level 1, J.TEST, CET-4, CET-6, English CET-4/6) and move them into the language list.

        JA: 専門資格の一覧に紛れ込んだ語学資格（日本語 1 級、J.TEST、CET-4、CET-6、英語 4・6 級など）を正確に取り除き、語学力の一覧に移す。
        """
        lang_certs = []
        pro_certs = []
        
        lang_pattern = re.compile(r"日语|日文|日本語|JLPT|J\.TEST|英语|英文|CET[- ]?[46]|四级|六级|TOEIC|TOEFL|IELTS|托福|雅思|大学英语|专四|专八", re.IGNORECASE)
        
        for cert in (certificate_info or []):
            cname = str(cert.get("certificate_name") or "").strip()
            cname_clean = re.sub(r"^[/\\:\d\s._-]+", "", cname).strip()
            if not cname_clean:
                continue
                
            if lang_pattern.search(cname_clean):
                lang_name = "英语"
                if re.search(r"日", cname_clean):
                    lang_name = "日语"
                elif re.search(r"德", cname_clean):
                    lang_name = "德语"
                elif re.search(r"法", cname_clean):
                    lang_name = "法语"
                elif re.search(r"韩", cname_clean):
                    lang_name = "韩语"
                
                lang_certs.append({
                    "language_name": lang_name,
                    "language_level": cert.get("certificate_level") or cert.get("certificate_name") or cname_clean,
                    "language_certificate": cname_clean,
                    "language_certificate_time": cert.get("certificate_time") or ""
                })
            else:
                cert["certificate_name"] = cname_clean
                pro_certs.append(cert)
                
        existing_certs = {str(l.get("language_certificate") or "") for l in (language_info or [])}
        for lc in lang_certs:
            c_val = lc["language_certificate"]
            if c_val and c_val not in existing_certs:
                existing_certs.add(c_val)
                matched = False
                for l in (language_info or []):
                    if l.get("language_name") == lc["language_name"]:
                        if not l.get("language_certificate"):
                            l["language_certificate"] = c_val
                        if not l.get("language_certificate_time"):
                            l["language_certificate_time"] = lc["language_certificate_time"]
                        matched = True
                        break
                if not matched:
                    if language_info is None:
                        language_info = []
                    language_info.append(lc)
                    
        return pro_certs, language_info

    def _filter_work_experiences(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """剔除被日期正则误切出的培训/证书清单，避免伪造工作经历。

        EN: Remove training/certificate lists wrongly cut out by the date regex, to avoid fabricating work history.

        JA: 日付の正規表現で誤って切り出された研修・資格の一覧を除去し、架空の職歴を作らないようにする。
        """
        kept = []
        for row in entries or []:
            company = str(row.get("company_name") or "").strip()
            company = re.sub(r"^(?:名称|公司|单位|企业)\s*[:：]\s*", "", company).strip()
            company = re.sub(r"^\s*(?:至今|至今\s*[:：]|至\s*現在|目前|现在)\s*[:：]?\s*", "", company).strip()
            company = re.sub(r"\s*\[[^\]]*(?:年|个月|month|year)[^\]]*\]\s*$", "", company, flags=re.I).strip()
            row["company_name"] = company
            
            position = str(row.get("position") or "").strip()
            m_scale = re.search(r"[（(]?\s*(\d+(?:-\d+)?\s*人(?:以上|以下)?)[）)]?", position)
            if m_scale:
                if not row.get("company_employees"):
                    row["company_employees"] = m_scale.group(1)
                position = re.sub(r"[（(]?\s*\d+(?:-\d+)?\s*人(?:以上|以下)?[）)]?", "", position).strip()
            row["position"] = position

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
            # 仅有“25岁”时不能反推出出生年份/日期；生日是否已过、资料
            # 的基准日期都未知，强行填充会制造一条不存在的个人信息。
            # EN: With only "25岁" (25 years old) the birth year/date cannot be inferred; whether the birthday has passed and the reference date
            #     of the data are both unknown, and forcing a value would create personal information that does not exist.
            # JA: 「25岁」（25 歳）だけでは生年や生年月日を逆算できない。誕生日を過ぎたかどうかも、資料の基準日もわからず、
            #     無理に埋めると存在しない個人情報を作り出してしまう。
            return "", None, age
            
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

        # 2a. 51job/无忧精英常见顺序：日期 → 职位/部门 → 公司 →
        # 公司元数据 → 工作描述。通用正则容易把“作为开发进入公司”或
        # “主要使用 Solidworks……”当成公司名，因此先按工作区块的
        # 行结构解析；成功时直接返回，避免后面的宽松回退规则污染字段。
        # EN: 2a. Common 51job / Wuyou Elite order: date → position/department → company →
        #     company metadata → job description. Generic regexes easily take "joined the company as a developer" or
        #     "mainly used Solidworks ..." as the company name, so first parse by the line structure of the
        #     work block; on success return immediately so the looser fallback rules below cannot pollute the fields.
        # JA: 2a. 51job／無憂精英によくある順序：日付 → 職位／部署 → 会社 →
        #     会社のメタデータ → 職務説明。汎用の正規表現は「開発者として入社」や
        #     「主に Solidworks を使用……」を会社名と誤認しやすいため、まず職歴ブロックの
        #     行構造で解析する。成功したらすぐに返し、後の緩い代替ルールがフィールドを汚染しないようにする。
        structured_work = self._extract_labeled_work_blocks(clean_text, pattern)
        if structured_work:
            return structured_work

        m_head = None
        for m in re.finditer(r"(?:工作经验|工作经历|職歴|仕事経験|Work Experience|履历)", clean_text, re.IGNORECASE):
            line_str = clean_text[max(0, m.start()-10):m.end()+10].splitlines()[0] if clean_text[max(0, m.start()-10):m.end()+10].splitlines() else ""
            if not any(stop in line_str for stop in ["年工作经验", "年经验", "工作年限", "最近工作", "简历-猎聘", ".doc", ".docx"]):
                m_head = m
                break
        if m_head:
            sec_start = m_head.end()
            m_next = re.search(r"\n\s*(?:教育程度|教育经历|教育背景|学歴|学\s*历|项目经历|项目经验|项目|【?项目经历】?|【?项目经验】?|Project Experience|Projects|外语水平|计算机水平|语言能力|语言|技能|Education|打工经历|奖惩情况|研究经历|自我评价|自己アピール|附加信息|\Z)", clean_text[sec_start:], re.IGNORECASE)
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

    def _extract_labeled_work_blocks(self, text: str, pattern: re.Pattern[str]) -> list[dict[str, Any]]:
        """Parse line-oriented 51job/无忧工作经历 blocks before generic fallback."""
        headings = list(re.finditer(r"(?m)^\s*(?:工作经验|工作经历)\s*$", text, re.I))
        if not headings:
            return []
        head = headings[-1]
        start = head.end()
        stop = re.search(
            r"(?m)^\s*(?:项目经历|项目经验|教育经历|教育背景|教育程度|技能特长|技能标签|语言能力|外语水平|自我评价|个人评价|证书)\s*$",
            text[start:],
            re.I,
        )
        section = text[start:start + stop.start()] if stop else text[start:]
        matches = list(pattern.finditer(section))
        if not matches:
            return []

        company_suffix = re.compile(
            r"(?:有限公司|有限责任公司|股份有限公司|集团(?:公司)?|研究所|研究中心|研究院|中心|公司|株式会社|会社|Corporation|Company|事务所|企业|工厂|厂)$",
            re.I,
        )
        title_words = ("工程师", "技术员", "经理", "主管", "专员", "顾问", "测试", "设计", "开发", "销售", "助理", "代表", "主任", "担当", "部长", "组长", "技师", "实习生", "学生实践")
        bad_company = ("作为", "进入公司", "主要使用", "负责", "参与", "项目", "工作描述", "工作内容", "职位：", "职能")
        result: list[dict[str, Any]] = []
        for idx, match in enumerate(matches):
            block_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
            block = section[match.end():block_end]
            lines = [re.sub(r"\s+", " ", line).strip(" |│\t") for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            # 公司名优先取日期后的前若干行中“机构后缀”行，去掉任职时长。
            # EN: For the company name, prefer an "institution suffix" line among the first few lines after the date, and remove the tenure.
            # JA: 会社名は日付の後の数行のうち「機関の接尾辞」を持つ行を優先し、在職期間を取り除く。
            company = ""
            company_idx = -1
            for li, line in enumerate(lines[:10]):
                candidate = re.sub(r"\s*[\[【(（][^\]】)）]*(?:年|个月|月|合作|兼职)[^\]】)）]*[\]】)）]\s*$", "", line).strip()
                candidate = re.sub(r"^(?:公司|公司名称|所属公司|单位)\s*[:：]\s*", "", candidate).strip()
                if company_suffix.search(candidate) and not any(term in candidate for term in bad_company):
                    company, company_idx = candidate, li
                    break
            if not company:
                continue

            # 日期后的短行通常是职位/部门；带分隔符时按标题词定位。
            # EN: Short lines after the date are usually position/department; when separators are present, locate by heading words.
            # JA: 日付の後の短い行は通常、職位・部署である。区切り文字がある場合は見出し語で位置を特定する。
            position, dept = "", ""
            pre_company = lines[:company_idx]
            for line in pre_company:
                tokens = [x.strip() for x in re.split(r"[|｜]", line) if x.strip()]
                if tokens:
                    for token in tokens:
                        if not position and any(k in token for k in title_words) and len(token) <= 40:
                            position = token
                    if len(tokens) >= 2 and position and not dept:
                        dept = next((x for x in tokens if x != position and len(x) <= 40), "")
            if not position:
                for line in lines[company_idx + 1:company_idx + 12]:
                    if re.search(r"公司行业|公司规模|工作描述", line):
                        continue
                    # 51job 常见“部门 职位”同一行；按空白/管道拆分，
                    # 不要把“信通部 软件测试工程师”整段写进职位。
                    # EN: 51job often has "department position" on the same line; split on whitespace/pipes
                    #     and do not write the whole "信通部 软件测试工程师" into the position.
                    # JA: 51job では「部署 職位」が同じ行にあることが多い。空白やパイプで分割し、
                    #     「信通部 软件测试工程师」をまるごと職位に書き込まない。
                    tokens = [x.strip() for x in re.split(r"\s+|[|｜]", line) if x.strip()]
                    for token in tokens:
                        if any(k in token for k in title_words) and len(token) <= 40:
                            position = token
                            break
                    if position:
                        break
            if not dept:
                # 有些 51job 模板把“部门 职位”放在公司后的较后行，
                # 不要只看固定三行，扫描到职责标签前。
                # EN: Some 51job templates put "department position" on a later line after the company;
                #     do not look only at a fixed three lines, scan up to the duties label.
                # JA: 51job のテンプレートによっては「部署 職位」が会社より後ろの行にある。
                #     固定の 3 行だけを見ずに、職務のラベルまでスキャンする。
                for line in pre_company + lines[company_idx + 1:]:
                    if re.search(r"工作描述|工作职责|职责业绩|主要工作|工作内容", line):
                        break
                    tokens = [x.strip() for x in re.split(r"\s+|[|｜]", line) if x.strip()]
                    for token in tokens:
                        if re.fullmatch(r"[^|｜：:]{2,30}(?:部|处|科|中心|组)", token):
                            dept = token
                            break
                    if dept:
                        break

            meta = "\n".join(lines)
            industry, employees = "", ""
            m_meta = re.search(r"(?P<industry>[^|｜\n]{2,50})\s*[|｜]\s*(?P<employees>少于\s*\d+\s*人|\d+\s*[-—至]\s*\d+\s*人|\d+\s*人以上|\d+\s*人)", meta)
            if m_meta:
                industry, employees = m_meta.group("industry").strip(), re.sub(r"\s+", "", m_meta.group("employees"))
            m_ind = re.search(r"(?:公司行业|行业)\s*[:：]\s*([^|｜\n]+)", meta)
            if m_ind and not industry:
                industry = m_ind.group(1).strip()
            if not industry:
                # 51job 常见“行业|公司性质/规模”无标签写法。
                # EN: 51job often writes "industry|company type/size" without labels.
                # JA: 51job では「業界|会社の性質／規模」がラベルなしで書かれることが多い。
                for line in lines[company_idx + 1:company_idx + 6]:
                    if "|" in line or "｜" in line:
                        left = re.split(r"[|｜]", line, maxsplit=1)[0].strip()
                        if left and len(left) <= 60 and not re.search(r"工作描述|公司规模|公司性质", left):
                            industry = left
                            break
            salary = ""
            m_sal = re.search(r"(?:薪酬情况|职位薪资|薪资)\s*[:：]\s*([^|｜\n]+)", meta)
            if m_sal:
                salary = m_sal.group(1).strip()
            report_to = ""
            m_report = re.search(r"(?:汇报对象|汇报给|直属上司)\s*[:：]\s*([^|｜\n]+)", meta)
            if m_report:
                report_to = m_report.group(1).strip()
            subordinate = ""
            m_sub = re.search(r"(?:下属人数|管辖人数|团队人数)\s*[:：]\s*(\d+\s*人?)", meta)
            if m_sub:
                subordinate = re.sub(r"\s+", "", m_sub.group(1))

            resp = ""
            m_resp = re.search(r"(?:工作描述|工作职责和业绩|职责业绩|主要工作|工作职责|职责描述|内容)\s*[:：]?\s*([\s\S]*)", block, re.I)
            if m_resp:
                resp = m_resp.group(1).strip()
            else:
                # 没有标签时保留公司之后的非元数据文字，避免丢失职责。
                # EN: Without labels, keep the non-metadata text after the company so duties are not lost.
                # JA: ラベルがない場合は会社の後のメタデータ以外のテキストを残し、職務が失われないようにする。
                resp_lines = lines[company_idx + 1:]
                resp = "\n".join(x for x in resp_lines if x and not re.search(r"公司行业|公司规模|公司性质|汇报对象|下属人数|薪酬情况", x))

            start_p = self._format_date(match.group(1))
            end_raw = match.group(2)
            current = end_raw in ("至今", "现在", "目前", "Present", "今迄", "現在")
            end_p = "" if current else self._format_date(end_raw)
            result.append({
                "company_name": company,
                "company_employees": employees,
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
                "status": "在职" if current else "离职",
                "position_start": start_p,
                "position_resigned": end_p,
                "resigned_reason": "",
                "position_responsibilities": resp[:1500],
            })
        return sorted(result, key=lambda x: x.get("position_start", ""), reverse=True)

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
        # 只把独立的“证书/资格证书”标题当作证书区块。不能从正文中的
        # “证书：……”或工作职责里任意出现的“证书”开始截取，否则会把
        # 投标、项目计价、合同签订等工作内容误收为证书。
        # EN: Must explicitly locate the certificate section, so a full-text search does not mistake the résumé download time / years of work for certificates.
        #     Only a standalone "证书/资格证书" (certificates/qualifications) heading counts as the certificate block. Extraction must not start from
        #     "证书：……" in the body or any occurrence of "证书" in job duties, otherwise work content such as
        #     bidding, project pricing and contract signing would be stored as certificates.
        # JA: 資格欄を明示的に特定する必要がある。全文検索で履歴書のダウンロード日時や勤続年数を資格と誤認しないため。
        #     独立した「证书／资格证书」（資格）の見出しだけを資格ブロックとして扱う。本文中の
        #     「证书：……」や職務内容に出てくる任意の「证书」から切り出してはならない。さもないと
        #     入札・プロジェクト見積もり・契約締結などの業務内容が資格として取り込まれてしまう。
        m = re.search(r"(?m)^\s*(?:\|?\s*(?:证书|资格证书|Certifications|资质认证|获得证书))\s*[:：\t\n\s]*([\s\S]{3,600}?)(?=\n\s*(?:\|?\s*语言能力|\|?\s*技能|\|?\s*自我评价|\|?\s*项目经历|\|?\s*工作经历|\|?\s*工作经验|\Z))", text, re.IGNORECASE)
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
                        # 区块内的普通职责句不是证书。只有名称本身带有
                        # 明确的证书/资格/考试标识时才允许进入证书表。
                        # EN: Ordinary duty sentences inside the block are not certificates. Only when the name itself carries
                        #     a clear certificate/qualification/exam marker may it enter the certificate table.
                        # JA: ブロック内の普通の職務の文は資格ではない。名称自体に明確な資格・検定・試験の目印がある場合だけ、
                        #     資格の表に入れてよい。
                        certificate_marker = re.search(
                            r"证书|资格|驾驶证|CET\s*[-－]?\s*[四六六]|N[一二三四五六1-6]|PMP|建造师|工程师|会计师|律师|职称|等级|认证|执业",
                            l_clean,
                            re.I,
                        )
                        action_phrase = re.search(
                            r"投标|项目|完成|负责|制定|承接|合同|签订|计价|报价|客户|市场|销售|回款|工作内容|工作职责|业绩|公司|部门|岗位|开发|管理|维护|设计|编制|安装|调试|组织|参与|协助",
                            l_clean,
                        )
                        if action_phrase and not certificate_marker:
                            continue
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
            # 语言名称属于 language_info，不是证书；只有带有明确等级/考试/证书标识时才保留。
            # EN: Language names belong to language_info, not certificates; keep them only when they carry an explicit level/exam/certificate marker.
            # JA: 言語名は language_info に属し、資格ではない。明確なレベル・試験・資格の目印がある場合だけ残す。
            if name in {"普通话", "英语", "日语", "德语", "法语", "韩语", "粤语", "西班牙语"}:
                continue
            # 防止工作经历中的职责句穿透到证书列表。证书名称可以是
            # “机动车驾驶证 C1”“PMP”“二级建造师”等，但不应是“投标文件制作”
            # 或“完成整个项目的投标”。
            # EN: Prevent duty sentences from work history leaking into the certificate list. Certificate names can be
            #     "机动车驾驶证 C1" (driving licence C1), "PMP", "二级建造师" (second-class constructor), etc., but not "投标文件制作" (preparing bid documents)
            #     or "完成整个项目的投标" (completed the bid for the whole project).
            # JA: 職歴の職務の文が資格の一覧に漏れ込むのを防ぐ。資格名は
            #     「机动车驾驶证 C1」（運転免許 C1）、「PMP」、「二级建造师」（二級建造師）などはあり得るが、「投标文件制作」（入札書類の作成）
            #     や「完成整个项目的投标」（プロジェクト全体の入札を完了）であってはならない。
            if re.search(
                r"投标|项目计价|完成整个项目|负责整个项目|合同签订|承接和排产|工作内容|工作职责|客户|市场|销售|回款|报价|制定营销|公司规模|公司行业|项目业绩",
                name,
            ) and not re.search(r"证书|资格证|驾驶证|CET|PMP|建造师|工程师|会计师|律师|认证|执业", name, re.I):
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

        # 1. 全文优先提取等级/证书：CET-6 / CET-4 / 大学英语六级 / 大学英语四级 / TEM-8 / TEM-4
        # EN: 1. First extract levels/certificates from the full text: CET-6 / CET-4 / 大学英语六级 / 大学英语四级 / TEM-8 / TEM-4
        # JA: 1. まず全文からレベル・資格を抽出する：CET-6 / CET-4 / 大学英语六级 / 大学英语四级 / TEM-8 / TEM-4
        m_cet6 = re.search(r"大学英语六级|英语六级|CET-?6|CET6", text, re.IGNORECASE)
        m_cet4 = re.search(r"大学英语四级|英语四级|CET-?4|CET4", text, re.IGNORECASE)
        m_tem8 = re.search(r"专八|专业八级|TEM-?8", text, re.IGNORECASE)
        m_tem4 = re.search(r"专四|专业四级|TEM-?4", text, re.IGNORECASE)
        
        if m_cet6:
            langs.append({"language_name": "英语", "language_level": "CET-6", "language_certificate": "CET-6", "language_certificate_time": ""})
            seen.add("英语")
        elif m_cet4:
            langs.append({"language_name": "英语", "language_level": "CET-4", "language_certificate": "CET-4", "language_certificate_time": ""})
            seen.add("英语")
        elif m_tem8 or m_tem4:
            level = "TEM-8" if m_tem8 else "TEM-4"
            langs.append({"language_name": "英语", "language_level": level, "language_certificate": level, "language_certificate_time": ""})
            seen.add("英语")

        m_n1 = re.search(r"(?:日语一級|日本語1級|JLPT\s*N1|\bN1\b|日语国际一级|日本語能力試験N1)[^\n]*(\d{2,3}/\d{2,3}点?)?", text)
        m_n2 = re.search(r"(?:日语二级|日本語2級|JLPT\s*N2|\bN2\b)[^\n]*(\d{2,3}/\d{2,3}点?)?", text)
        if m_n1:
            score = m_n1.group(1) or ""
            level = f"N1（{score}）" if score else "N1"
            langs.append({"language_name": "日语", "language_level": level, "language_certificate": "日语N1证书", "language_certificate_time": ""})
            seen.add("日语")
        elif m_n2:
            score = m_n2.group(1) or ""
            level = f"N2（{score}）" if score else "N2"
            langs.append({"language_name": "日语", "language_level": level, "language_certificate": "日语N2证书", "language_certificate_time": ""})
            seen.add("日语")

        # 2. 语言能力章节补全
        # EN: 2. Complete from the language-skills section
        # JA: 2. 語学力の章から補完する
        m_sec = re.search(r"(?:\|?\s*语言能力|外语水平|语言水平|語学|語学能力)\s*[:：\t\n\s]*([\s\S]{3,300}?)(?=\n\s*(?:\|?\s*技能|\|?\s*自我评价|\|?\s*项目经历|\|?\s*教育经历|Work Experience|Education|\Z))", text, re.IGNORECASE)
        if m_sec:
            sec_txt = m_sec.group(1).strip()
            lines = [l.strip() for l in sec_txt.splitlines() if l.strip()]
            for l in lines:
                parts = re.split(r"[,，、;\s]+", l)
                for p in parts:
                    p_clean = p.strip()
                    if not p_clean: continue
                    for lkw in ["英语", "普通话", "日语", "韩语", "德语", "法语", "西班牙语", "粤语"]:
                        if lkw in p_clean and lkw not in seen:
                            seen.add(lkw)
                            langs.append({
                                "language_name": lkw,
                                "language_level": p_clean if p_clean != lkw else "熟练",
                                "language_certificate": p_clean if ("级" in p_clean or "证书" in p_clean) else "有",
                                "language_certificate_time": ""
                            })

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

    def _extract_training_experiences(self, text: str) -> list[dict[str, Any]]:
        trainings = []
        m_sec = re.search(r"(?:\|?\s*培训经历|培训经验|培训背景|培训及证书|Training(?:\s+Experience)?)\s*[:：\t\n\s]*([\s\S]{5,2500}?)(?=\n\s*(?:\|?\s*证书|\|?\s*资格证书|\|?\s*语言能力|\|?\s*外语水平|\|?\s*技能|\|?\s*自我评价|\|?\s*项目经历|\|?\s*工作经历|\|?\s*教育经历|\Z))", text, re.IGNORECASE)
        if not m_sec:
            return []

        sec_txt = m_sec.group(1).strip()
        sec_txt = re.sub(r"((?:19|20)\d{2})\s*[\r\n]+\s*/\s*(0?[1-9]|1[0-2])", r"\1/\2", sec_txt)
        
        blocks = re.split(r"\n(?=(?:(?:19|20)\d{2}[./-]\d{1,2}|(?:19|20)\d{2}\s*[-—–~∼～至到]))", sec_txt)
        for b in blocks:
            b_clean = b.strip()
            if not b_clean: continue
            
            m_date = re.search(r"((?:19|20)\d{2})[./-](0?[1-9]|1[0-2])\s*[-—–~∼～至到\ufffd\s]+\s*(((?:19|20)\d{2})[./-](0?[1-9]|1[0-2])|至今|现在|目前)", b_clean)
            start_ym = ""
            end_ym = ""
            if m_date:
                start_ym = f"{m_date.group(1)}.{int(m_date.group(2)):02d}"
                if m_date.group(3) in ("至今", "现在", "目前"):
                    end_ym = "至今"
                elif m_date.group(4) and m_date.group(5):
                    end_ym = f"{m_date.group(4)}.{int(m_date.group(5)):02d}"
                    
            content = re.sub(r"^\s*(?:(?:19|20)\d{2}[./-]\d{1,2}\s*[-—–~∼～至到\ufffd\s]+\s*(?:(?:19|20)\d{2}[./-]\d{1,2}|至今|现在|目前)|(?:19|20)\d{2})\s*[:：\t\s]*", "", b_clean).strip().replace("\ufffd", "")
            lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().isdigit()]
            if not lines: continue
            
            org_name = ""
            train_name = ""
            cert_name = ""
            desc_lines = []
            
            for line in lines:
                if not org_name and any(kw in line for kw in ["美斯坦福", "培训", "学院", "中心", "学校", "机构", "大学", "公司"]):
                    org_name = line
                elif not train_name and any(kw in line for kw in ["开发", "课程", "技术", "管理", "设计", "工程师", "软件", "培训", "ASP"]):
                    train_name = line
                elif not cert_name and ("证书" in line or "级别" in line or "资格" in line or "NCIE" in line or "工程师" in line):
                    cert_name = line
                else:
                    desc_lines.append(line)
                    
            if not org_name and lines:
                org_name = lines[0]
            if not train_name and len(lines) > 1:
                train_name = lines[1]
            if not desc_lines:
                desc_lines = lines
                
            if org_name.isdigit() or len(org_name) <= 4:
                org_name = train_name if train_name and not train_name.isdigit() else "培训机构"

            trainings.append({
                "sequence_no": len(trainings) + 1,
                "organization_name": org_name,
                "training_name": train_name or org_name,
                "start_ym": start_ym,
                "end_ym": end_ym,
                "certificate_name": cert_name,
                "description": "\n".join(desc_lines)
            })
            
        return trainings

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
