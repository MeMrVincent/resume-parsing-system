"""全量清洗 complete-transfered-jsons：非简历/应届无经验清理、多语言校验、关键词和 raw_text。

默认仅预检；传入 --apply 才会原子改写 JSON 并删除明确无效文件。
翻译使用工作区内 Argos Translate 离线模型，不向外部服务发送简历内容。

EN: Full clean-up of complete-transfered-jsons: remove non-résumés / new graduates without experience, multilingual validation, keywords and raw_text.

Dry run by default; only with --apply are JSON files rewritten atomically and clearly invalid files deleted.
Translation uses the offline Argos Translate model in the workspace; no résumé content is sent to external services.

JA: complete-transfered-jsons の全件クレンジング：非履歴書・経験なし新卒の整理、多言語検証、キーワードと raw_text。

既定では事前チェックのみ。--apply を渡したときだけ JSON をアトミックに書き換え、明らかに無効なファイルを削除する。
翻訳はワークスペース内の Argos Translate オフラインモデルを使い、履歴書の内容を外部サービスに送らない。
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "common"))
import rc_config as _rc  # noqa: E402  项目统一配置（python/common/rc_config.py）
# EN: noqa: E402  project-wide configuration (python/common/rc_config.py)
# JA: noqa: E402  プロジェクト共通設定（python/common/rc_config.py）

import argparse
import copy
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = _rc.project_root()
DEFAULT_INPUT = ROOT / _rc.dirname("complete-transfered-jsons")
DATE_MAP_PATH = DEFAULT_INPUT / "_json_source_date_map.json"
ARGOS_ROOT = ROOT / ".argos"

os.environ.setdefault("XDG_DATA_HOME", str(ARGOS_ROOT / "data"))
os.environ.setdefault("XDG_CONFIG_HOME", str(ARGOS_ROOT / "config"))
os.environ.setdefault("XDG_CACHE_HOME", str(ARGOS_ROOT / "cache"))
os.environ.setdefault("ARGOS_PACKAGES_DIR", str(ARGOS_ROOT / "packages"))
os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")

if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

FRESH_RE = re.compile(
    r"应届(?:生)?|在校生|高校毕业生|校园招聘|校招|新卒|"
    r"fresh\s+graduate|new\s+graduate|recent\s+graduate",
    re.I,
)
NON_RESUME_NAME_RE = re.compile(
    r"(?:^|[\\/_\-])(?:职位\s*JD|JD模板|案件更新|入职须知|录用通知|聘用通知|"
    r"offer(?:\s*letter)?|招聘需求|募集要項|求人票|操作手册|培训资料|工资表|报价单|发票)"
    r"(?:[\\/_\-.]|$)",
    re.I,
)
NON_RESUME_TEXT_RES = (
    ("offer", re.compile(r"录用通知书|聘用通知书|採用通知書|内定通知書|offer\s+letter", re.I)),
    ("job_description", re.compile(r"募集職種|招聘人数|岗位职责|任职要求|职位描述|募集要項|求人票", re.I)),
    ("onboarding", re.compile(r"入职所需材料|入职资料|报到所需材料", re.I)),
    ("manual", re.compile(r"操作手册|使用说明书|培训教材|業務マニュアル", re.I)),
    ("financial", re.compile(r"工资表|薪资表|报价单|发票|請求書|見積書", re.I)),
)
EXPERIENCED_RE = re.compile(
    r"(?:[1-9]\d*(?:\.\d+)?\s*年(?:以上)?工作经验|工作年限\s*[:：]?\s*[1-9]\d*|"
    r"[1-9]\d*\+?\s*years?\s+(?:of\s+)?(?:work|professional)\s+experience|"
    r"職歴\s*[:：]?.{0,80}(?:19|20)\d{2})",
    re.I | re.S,
)
NO_EXPERIENCE_RE = re.compile(r"应届生简历\s*/?\s*无工作经验|(?:暂无|没有|无|缺少)工作经验|no\s+work\s+experience", re.I)
RAW_WORK_ENTRY_RE = re.compile(
    r"(?:工作经历|工作经验|职历|職歴|professional\s+experience|employment\s+history)"
    r".{0,800}(?:19|20)\d{2}[./年-].{0,40}(?:至今|现在|今|present|(?:19|20)\d{2})"
    r".{0,500}(?:有限公司|株式会社|公司|职位|職位|役職|position|实习生|インターン)",
    re.I | re.S,
)

LANG_ALIASES = {"zh": "zh", "cn": "zh", "chinese": "zh", "ja": "jp", "jp": "jp", "japanese": "jp", "en": "en", "english": "en"}
PROTECTED_KEYS = {
    "full_name", "phone", "email", "platform_resume_id", "postal_code",
    "birth_date", "birth_year", "work_start_time", "work_end_time",
    "school_start_time", "school_end_time", "project_start_time", "project_end_time",
    "training_start_time", "training_end_time", "position_start", "position_resigned",
}
ENTITY_KEYS = {"company_name", "school_name", "full_name", "platform_from"}
ZH_TRANSLATE_KEYS = {
    "position_responsibilities", "position_responsibility", "responsibilities", "description",
    "project_description", "pr", "communicate_content", "achievements", "position_achievements",
    "leave_reason", "resigned_reason", "position", "expected_position", "position_dept",
    "school_major_name", "company_industry", "expected_industry", "project_name", "project_role",
    "training_name", "gender", "marital_status", "employment_status", "expected_start_date",
    "expected_employment_type", "school_degree_type", "school_education_type", "language_name",
    "language_level", "skill_level", "nationality",
}
ZH_GLOSSARY = {
    "male": "男", "female": "女", "man": "男", "woman": "女", "single": "未婚",
    "married": "已婚", "divorced": "离异", "full-time": "全职", "full time": "全职",
    "part-time": "兼职", "part time": "兼职", "present": "至今", "current": "目前",
    "immediate": "立即到岗", "bachelor": "本科", "bachelor's degree": "学士",
    "master": "硕士", "master's degree": "硕士", "phd": "博士", "doctor": "博士",
    "associate": "大专", "high school": "高中", "fluent": "流利", "native": "母语",
    "excellent": "优秀", "good": "良好", "intermediate": "中级", "beginner": "初级",
    "english": "英语", "japanese": "日语", "chinese": "中文",
    "男性": "男", "女性": "女", "未婚": "未婚", "既婚": "已婚", "現在": "目前",
    "正社員": "全职", "学士": "学士", "修士": "硕士", "博士": "博士",
}
EN_GLOSSARY = {
    "男": "Male", "女": "Female", "未婚": "Single", "已婚": "Married", "离异": "Divorced",
    "全职": "Full-time", "兼职": "Part-time", "至今": "Present", "目前": "Current",
    "立即到岗": "Available immediately", "即时": "Available immediately", "本科": "Bachelor's degree",
    "学士": "Bachelor's degree", "硕士": "Master's degree", "博士": "Doctorate", "大专": "Associate degree",
    "高中": "High school", "流利": "Fluent", "母语": "Native", "优秀": "Excellent", "良好": "Good",
    "中级": "Intermediate", "初级": "Beginner", "中文": "Chinese", "英语": "English", "日语": "Japanese",
    "男性": "Male", "女性": "Female", "既婚": "Married", "現在": "Current", "正社員": "Full-time",
    "修士": "Master's degree",
}
JP_GLOSSARY = {
    "男": "男性", "女": "女性", "未婚": "未婚", "已婚": "既婚", "离异": "離婚",
    "全职": "正社員", "兼职": "パートタイム", "至今": "現在", "目前": "現在",
    "立即到岗": "即日勤務可能", "即时": "即日勤務可能", "本科": "学士", "学士": "学士",
    "硕士": "修士", "博士": "博士", "大专": "短期大学", "高中": "高等学校",
    "流利": "流暢", "母语": "母語", "优秀": "優秀", "良好": "良好", "中级": "中級", "初级": "初級",
    "中文": "中国語", "英语": "英語", "日语": "日本語", "male": "男性", "female": "女性",
    "single": "未婚", "married": "既婚", "full-time": "正社員", "part-time": "パートタイム",
    "present": "現在", "bachelor": "学士", "master": "修士", "phd": "博士", "english": "英語",
    "japanese": "日本語", "chinese": "中国語", "fluent": "流暢",
}
TARGET_GLOSSARIES = {"zh": ZH_GLOSSARY, "en": EN_GLOSSARY, "jp": JP_GLOSSARY}
KEYWORD_KEYS = {
    "expected_position", "expected_industry", "position", "position_type", "position_dept",
    "company_industry", "school_major_name", "school_degree_type", "project_name", "project_role",
    "certificate_name", "language_name", "language_level", "skill_name", "skills_name",
    "training_name", "employment_type", "city", "expected_city",
}
GENERIC_KEYWORDS = {
    "全职", "兼职", "至今", "现在", "目前", "其他", "不限", "无", "暂无", "未知",
    "full-time", "part-time", "present", "other", "none", "unknown",
    "正社員", "現在", "その他", "なし",
}

BODY_UPDATED_RE = re.compile(
    r"(?:简历\s*)?(?:更新时间|更新日期|更新日(?:時)?|last\s+updated|resume\s+updated|updated\s+on)"
    r"\s*[:：]?\s*(?P<year>(?:19|20)\d{2})\s*[年./\-]\s*(?P<month>\d{1,2})\s*[月./\-]\s*(?P<day>\d{1,2})\s*日?",
    re.I,
)
DATE_VALUE_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--no-translate", action="store_true", help="应用其它修复但只报告语言问题" " / Apply the other repairs but only report language problems / ほかの修復は適用するが、言語の問題は報告するだけにする")
    return p.parse_args()


def strings(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, path + (str(key),))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from strings(child, path + (str(i),))
    elif isinstance(value, str) and value.strip():
        yield path, value.strip()


def valid_works(resume: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for work in resume.get("work_experiences") or []:
        if not isinstance(work, dict):
            continue
        meaningful = [str(work.get(k, "")).strip() for k in (
            "company_name", "position", "position_responsibility", "work_start_time", "work_end_time"
        )]
        if any(meaningful):
            result.append(work)
    return result


def valid_educations(resume: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in (resume.get("education_list") or []) if isinstance(e, dict) and any(
        str(e.get(k, "")).strip() for k in ("school_name", "school_major_name", "school_degree_type", "school_start_time", "school_end_time")
    )]


def personal_name(value: str) -> bool:
    value = value.strip()
    if not value or len(value) > 40:
        return False
    if re.search(r"简历|须知|通知|公司|案件|招聘|职位|模板|报告|resume|curriculum", value, re.I):
        return False
    return bool(re.search(r"[\u3400-\u9fffA-Za-zぁ-んァ-ヶ]", value))


def deletion_reason(data: Any, path: Path) -> str:
    if not isinstance(data, dict):
        return "非简历聚合清单/顶层不是对象"
    classification = data.get("classification") or {}
    if classification.get("document_type") not in (None, "resume"):
        return f"原分类明确为非简历:{classification.get('document_type')}"
    sd = data.get("structured_data") or {}
    resumes = sd.get("resumes") or []
    if not resumes or not isinstance(resumes[0], dict):
        return "缺少有效 resumes 结构"
    all_works = [w for r in resumes if isinstance(r, dict) for w in valid_works(r)]
    all_edus = [e for r in resumes if isinstance(r, dict) for e in valid_educations(r)]
    r0 = resumes[0]
    base = r0.get("base_info") or {}
    contact = bool(str(base.get("phone", "")).strip() or str(base.get("email", "")).strip())
    name_ok = personal_name(str(base.get("full_name", "")))
    source = data.get("source") or {}
    source_name = " ".join(str(source.get(k, "")) for k in ("path", "original_path", "filename"))
    raw = str(data.get("raw_text") or "")
    explicit_types = [label for label, rx in NON_RESUME_TEXT_RES if rx.search(raw[:30000])]
    explicit_name = bool(NON_RESUME_NAME_RE.search(source_name))
    # 明确的非简历文种，同时没有可信的个人履历结构，才删除。正文中提到
    # “发票/操作手册”常常只是候选人的工作内容，不能单独作为删除理由。
    # EN: Delete only documents that are clearly a non-résumé type and also lack any credible personal-history structure. Mentions of
    #     "invoice/operation manual" in the body are often just the candidate's work content and cannot alone justify deletion.
    # JA: 明らかに履歴書以外の文書で、かつ信頼できる経歴構造がない場合のみ削除する。本文中の
    #     「請求書／操作マニュアル」への言及は候補者の業務内容にすぎないことが多く、それだけを削除理由にはできない。
    resume_evidence = int(contact) + int(name_ok) + 2 * int(bool(all_works)) + int(bool(all_edus))
    decisive = [x for x in explicit_types if x in {"offer", "onboarding"}]
    if decisive and resume_evidence < 4:
        return "明确非简历特征:" + ",".join(decisive)
    if explicit_name and resume_evidence < 4:
        return "文件名/路径明确为非简历"
    # JD 即使误抽出公司电话、学历要求，也没有候选人的工作经历。
    # EN: Even if a JD mistakenly yields a company phone number or degree requirement, it has no candidate work history.
    # JA: JD から会社の電話番号や学歴要件が誤って抽出されても、候補者の職歴はない。
    if "job_description" in explicit_types and not all_works and explicit_name:
        return "职位JD/招聘需求，不是候选人简历"
    # 应届/在校且所有语言版本都没有工作经历。
    # EN: New graduate / student, and no language version has any work history.
    # JA: 新卒・在学中で、どの言語版にも職歴がない。
    blob = json.dumps({"raw_text": raw, "resumes": resumes}, ensure_ascii=False)
    raw_has_work = bool(EXPERIENCED_RE.search(raw)) or (
        bool(RAW_WORK_ENTRY_RE.search(raw)) and not bool(NO_EXPERIENCE_RE.search(raw))
    )
    if not all_works and FRESH_RE.search(blob) and not raw_has_work:
        return "应届生/在校生且无工作经验"
    return ""


def char_counts(text: str) -> tuple[int, int, int]:
    han = len(re.findall(r"[\u3400-\u9fff]", text))
    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return han, kana, latin


def source_language(text: str, target: str, key: str) -> str | None:
    if key in PROTECTED_KEYS or not text.strip() or re.fullmatch(r"[\d\W_]+", text):
        return None
    if re.search(r"https?://|www\.|@", text, re.I):
        return None
    han, kana, latin = char_counts(text)
    letters = han + kana + latin
    if letters < 2:
        return None
    glossary = TARGET_GLOSSARIES.get(target, {})
    if target == "zh":
        # 姓名、公司/学校、证书、技能和技术缩写属于专名；强行机翻会破坏检索。
        # 仅翻译叙述字段和有明确语义的枚举/职位字段。
        # EN: Names, companies/schools, certificates, skills and technical abbreviations are proper nouns; forced machine translation would break search.
        #     Only narrative fields and enum/position fields with clear meaning are translated.
        # JA: 氏名・会社／学校・資格・スキル・技術略語は固有名詞であり、無理に機械翻訳すると検索性が損なわれる。
        #     叙述的なフィールドと、意味の明確な列挙値・職位フィールドだけを翻訳する。
        if text.strip().casefold() not in glossary and key not in ZH_TRANSLATE_KEYS:
            return None
        if kana >= 2:
            return "ja"
        if latin >= 4 and latin >= max(3, han * 2):
            return "en"
    elif target == "en":
        if text.strip().casefold() not in glossary and key not in ZH_TRANSLATE_KEYS:
            return None
        if kana >= 2:
            return "ja"
        if han >= 2 and han >= latin:
            return "zh"
    elif target == "jp":
        if text.strip().casefold() not in glossary and key not in ZH_TRANSLATE_KEYS:
            return None
        if kana >= 2:
            return None
        if latin >= 4 and latin >= max(3, han * 2):
            return "en"
        # 汉字专名在中日文可共用；只翻译较长的中文语句/职责。
        # EN: Kanji proper nouns can be shared between Chinese and Japanese; only translate longer Chinese sentences/duties.
        # JA: 漢字の固有名詞は中国語と日本語で共用できる。長めの中国語の文や職務内容だけを翻訳する。
        if han >= 5 and (key not in ENTITY_KEYS) and (len(text) >= 8 or re.search(r"负责|管理|开发|销售|设计|工作|经验|能力", text)):
            return "zh"
    return None


class OfflineTranslator:
    """NLLB 本地批量翻译器；只把中文主版本中的外文叙述翻成中文。

    EN: Local NLLB batch translator; only translates foreign-language narrative in the Chinese primary version into Chinese.

    JA: ローカルの NLLB バッチ翻訳器。中国語主版に含まれる外国語の叙述部分だけを中国語に翻訳する。
    """
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.cache_path = ROOT / ".models" / "nllb_translation_cache.json"
        self.cache: dict[str, str] = {}
        self.calls = 0
        self.failures: list[str] = []
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                self.cache = {}
        self.model = None
        self.tokenizer = None

    @staticmethod
    def cache_key(text: str, source: str, target: str) -> str:
        target_code = "ja" if target == "jp" else target
        return f"{source}>{target_code}\0{text}"

    @staticmethod
    def segments(text: str, max_chars: int = 300) -> list[str]:
        """按自然边界切开长字段，避免模型截断职责/项目描述的后半段。

        EN: Split long fields at natural boundaries so the model does not truncate the second half of duties/project descriptions.

        JA: 長いフィールドを自然な区切りで分割し、モデルが職務・プロジェクト説明の後半を切り捨てないようにする。
        """
        if len(text) <= max_chars:
            return [text]
        parts = re.split(r"(?<=[。！？.!?；;])\s*|\s*\n+\s*", text)
        chunks: list[str] = []
        current = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            while len(part) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(part[:max_chars])
                part = part[max_chars:]
            if not part:
                continue
            if current and len(current) + 1 + len(part) > max_chars:
                chunks.append(current)
                current = part
            else:
                current = f"{current} {part}".strip()
        if current:
            chunks.append(current)
        return chunks or [text]

    def precompute(self, requests: set[tuple[str, str, str]]) -> None:
        pending_originals = [(a, b, s) for a, b, s in requests
                   if self.cache_key(s, a, b) not in self.cache
                   and s.strip().casefold() not in TARGET_GLOSSARIES.get(b, {})]
        if not self.enabled or not pending_originals:
            return
        pending = sorted({(a, b, segment) for a, b, original in pending_originals
                          for segment in self.segments(original)
                          if self.cache_key(segment, a, b) not in self.cache})
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        from transformers.utils import logging as transformers_logging
        transformers_logging.set_verbosity_error()
        model_path = ROOT / ".models" / "nllb-200-distilled-600M"
        if not (model_path / "pytorch_model.bin").exists():
            raise RuntimeError(f"缺少NLLB模型: {model_path}")
        print(f"loading_nllb pending_originals={len(pending_originals)} pending_segments={len(pending)}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_path, local_files_only=True).eval()
        torch.set_num_threads(max(1, (os.cpu_count() or 4) - 2))
        lang_codes = {"zh": "zho_Hans", "en": "eng_Latn", "ja": "jpn_Jpan", "jp": "jpn_Jpan"}
        by_pair: dict[tuple[str, str], list[str]] = {}
        for source, target, text in pending:
            target_code = "ja" if target == "jp" else target
            if source in lang_codes and target_code in lang_codes:
                by_pair.setdefault((source, target), []).append(text)
        total_done = 0
        max_batch_size = max(1, int(os.environ.get("NLLB_BATCH_SIZE", "64")))
        next_report = 256
        next_save = 128
        for (source, target), texts in by_pair.items():
            # 相近长度同批，减少 padding 和 CPU 浪费。
            # EN: Put similar lengths in the same batch to reduce padding and wasted CPU.
            # JA: 長さの近いものを同じバッチにまとめ、パディングと CPU の無駄を減らす。
            texts = sorted(set(texts), key=len)
            start = 0
            while start < len(texts):
                current_length = len(texts[start])
                if current_length <= 60:
                    batch_size = max_batch_size
                elif current_length <= 180:
                    batch_size = min(max_batch_size, 24)
                else:
                    batch_size = min(max_batch_size, 6)
                batch = texts[start:start + batch_size]
                start += len(batch)
                self.tokenizer.src_lang = lang_codes[source]
                inputs = self.tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=384)
                try:
                    input_tokens = int(inputs["attention_mask"].sum(dim=1).max().item())
                    output_limit = min(384, max(32, input_tokens * 2 + 16))
                    with torch.inference_mode():
                        output = self.model.generate(
                            **inputs,
                            forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(lang_codes[target]),
                            max_new_tokens=output_limit,
                            num_beams=1,
                            no_repeat_ngram_size=3,
                        )
                    results = self.tokenizer.batch_decode(output, skip_special_tokens=True)
                    for original, translated in zip(batch, results):
                        translated = translated.strip()
                        # 证书/技术缩写若模型漏掉，追加保留，避免检索信息丢失。
                        # EN: If the model drops a certificate/technical abbreviation, append it back so search information is not lost.
                        # JA: モデルが資格・技術略語を落とした場合は追記して残し、検索情報の欠落を防ぐ。
                        acronyms = re.findall(r"\b[A-Z][A-Z0-9+.#-]{1,12}\b", original)
                        missing = [x for x in acronyms if x.casefold() not in translated.casefold()]
                        if missing:
                            translated = f"{translated} ({' / '.join(missing)})".strip()
                        self.cache[self.cache_key(original, source, target)] = translated or original
                        self.calls += 1
                except Exception as exc:
                    self.failures.append(f"batch:{source}>{target}:{type(exc).__name__}:{str(exc)[:160]}")
                total_done += len(batch)
                if total_done >= next_report:
                    print(f"nllb_translated={total_done}/{len(pending)}", flush=True)
                    next_report = ((total_done // 256) + 1) * 256
                if total_done >= next_save:
                    self.save()
                    next_save = ((total_done // 128) + 1) * 128
        # 长字段用所有分段结果合并，额外保存完整字段键，transform 阶段可直接命中。
        # EN: Long fields are merged from all segment results, and the full field key is also stored so the transform stage can hit it directly.
        # JA: 長いフィールドは全セグメントの結果を結合し、さらにフィールド全体のキーも保存して transform 段階で直接ヒットさせる。
        for source, target, original in pending_originals:
            translated_parts = []
            for segment in self.segments(original):
                translated_parts.append(self.cache.get(self.cache_key(segment, source, target), segment))
            self.cache[self.cache_key(original, source, target)] = " ".join(translated_parts).strip() or original
        self.save()
        self.model = None
        self.tokenizer = None

    def translate(self, text: str, source: str, target: str) -> str:
        # strings() 在请求收集时会 strip；实际字段常带一个尾换行。缓存查询必须
        # 使用同一规范化文本，否则会出现“已预计算但运行时 missing_precompute”。
        # EN: strings() strips text when collecting requests, while real fields often carry a trailing newline. Cache lookups must
        #     use the same normalised text, otherwise you get "precomputed but missing_precompute at run time".
        # JA: strings() はリクエスト収集時に strip するが、実際のフィールドには末尾の改行が付いていることが多い。キャッシュ検索も
        #     同じ正規化テキストを使わないと「事前計算済みなのに実行時に missing_precompute」になる。
        normalized_text = text.strip()
        glossary = TARGET_GLOSSARIES.get(target, {}).get(normalized_text.casefold())
        if glossary:
            return glossary
        key = self.cache_key(normalized_text, source, target)
        if key in self.cache:
            return self.cache[key]
        if self.enabled:
            self.failures.append(f"missing_precompute:{source}>{target}:{normalized_text[:80]}")
        return text

    def save(self) -> None:
        if not self.enabled:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.cache_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.cache_path)


def transform_language(value: Any, target: str, translator: OfflineTranslator, path: tuple[str, ...] = (), audit: list[dict[str, str]] | None = None) -> Any:
    if isinstance(value, dict):
        return {k: transform_language(v, target, translator, path + (str(k),), audit) for k, v in value.items()}
    if isinstance(value, list):
        return [transform_language(v, target, translator, path + (str(i),), audit) for i, v in enumerate(value)]
    if not isinstance(value, str):
        return value
    key = path[-1] if path else ""
    source = source_language(value, target, key)
    if not source:
        return value
    if audit is not None:
        audit.append({"path": ".".join(path), "source_language": source, "target_language": target, "sample": value[:160]})
    return translator.translate(value, source, target)


def normalize_resume_languages(sd: dict[str, Any], translator: OfflineTranslator, audit: list[dict[str, str]]) -> tuple[list[dict[str, Any]], bool]:
    original = sd.get("resumes") or []
    resumes: list[dict[str, Any]] = []
    for item in original:
        if not isinstance(item, dict):
            continue
        item = copy.deepcopy(item)
        lang_raw = item.pop("resume_languge", item.get("resume_language", "zh"))
        lang = LANG_ALIASES.get(str(lang_raw).strip().lower(), "zh")
        item["resume_language"] = lang
        item = transform_language(item, lang, translator, ("resumes", str(len(resumes))), audit)
        item["resume_language"] = lang
        resumes.append(item)
    if not resumes:
        return [], False
    zh_index = next((i for i, r in enumerate(resumes) if r.get("resume_language") == "zh"), None)
    created = False
    if zh_index is None:
        zh = copy.deepcopy(resumes[0])
        zh["resume_language"] = "zh"
        zh = transform_language(zh, "zh", translator, ("resumes", "new_zh"), audit)
        zh["resume_language"] = "zh"
        resumes.insert(0, zh)
        created = True
    elif zh_index != 0:
        resumes.insert(0, resumes.pop(zh_index))
    return resumes, created


def keyword_values(resume: dict[str, Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for path, value in strings(resume):
        key = path[-1] if path else ""
        if key not in KEYWORD_KEYS:
            continue
        for part in re.split(r"[|｜,，、;/；\n]+", value):
            part = re.sub(r"\s+", " ", part).strip(" .。:：-—")
            norm = part.casefold()
            if not (2 <= len(part) <= 48) or norm in GENERIC_KEYWORDS or norm in seen:
                continue
            if re.search(r"@|https?://|(?<!\d)\d{7,}(?!\d)", part):
                continue
            seen.add(norm)
            found.append(part)
            if len(found) >= 80:
                return found
    return found


def sync_top_level(sd: dict[str, Any], r0: dict[str, Any], translator: OfflineTranslator, audit: list[dict[str, str]]) -> None:
    # 先把 resumes 外的所有文本转成中文，再用中文 0 号位覆盖关键快照。
    # EN: First convert all text outside resumes to Chinese, then overwrite the key snapshots with Chinese slot 0.
    # JA: まず resumes 以外のテキストをすべて中国語に変換し、その後中国語の 0 番要素で主要スナップショットを上書きする。
    for key in list(sd):
        if key != "resumes":
            sd[key] = transform_language(sd[key], "zh", (translator), ("structured_data", key), audit)
    if isinstance(r0.get("base_info"), dict):
        sd["base_info"] = copy.deepcopy(r0["base_info"])
    if isinstance(r0.get("expected_info"), list):
        sd["expected_info"] = copy.deepcopy(r0["expected_info"])
    edus = valid_educations(r0)
    if edus and isinstance(sd.get("education_info"), dict):
        e = edus[0]
        mapping = {
            "school_name": "school_name", "school_major_name": "school_major_name",
            "school_degree_type": "school_degree_type", "school_degree_rank": "school_degree_rank",
            "school_education_type": "school_education_type", "school_start_ym": "school_start_time",
            "school_end_ym": "school_end_time",
        }
        for top_key, resume_key in mapping.items():
            if top_key in sd["education_info"] or resume_key in e:
                sd["education_info"][top_key] = copy.deepcopy(e.get(resume_key, ""))
    works = valid_works(r0)
    if works and isinstance(sd.get("current_info"), dict):
        w = works[0]
        for key in list(sd["current_info"]):
            if key in w:
                sd["current_info"][key] = copy.deepcopy(w[key])


def rebuild_raw_text(sd: dict[str, Any]) -> str:
    values: list[str] = []
    seen: set[str] = set()
    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for child in v.values():
                walk(child)
        elif isinstance(v, list):
            for child in v:
                walk(child)
        elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
            text = re.sub(r"\s+", " ", str(v)).strip()
            if text and text not in seen:
                seen.add(text)
                values.append(text)
    walk(sd)
    return " | ".join(values)


def body_updated_date(raw_text: str, old_dates: dict[str, Any]) -> tuple[str, str]:
    """提取正文明确的简历更新时间；不把投递/下载日期混进来。

    EN: Extract the résumé update time stated explicitly in the body; do not mix in application/download dates.

    JA: 本文に明記された履歴書の更新日時を抽出する。応募日・ダウンロード日は混ぜない。
    """
    match = BODY_UPDATED_RE.search(raw_text[:100000])
    if match:
        try:
            value = datetime(
                int(match.group("year")), int(match.group("month")), int(match.group("day"))
            ).strftime("%Y-%m-%d %H:%M:%S")
            return value, "body_explicit"
        except ValueError:
            pass
    old_source = str(old_dates.get("resume_updated_date_source") or "")
    old_value = str(old_dates.get("resume_updated_date") or "")
    if ("正文" in old_source and "更新" in old_source) and DATE_VALUE_RE.fullmatch(old_value):
        if len(old_value) == 10:
            old_value += " 00:00:00"
        return old_value, "body_existing_verified"
    return "", "source_mtime_fallback"


def update_dates(
    data: dict[str, Any], json_path: Path, date_map: dict[str, Any], batch_time: str
) -> tuple[str, str]:
    old_dates = data.get("dates") if isinstance(data.get("dates"), dict) else {}
    old_dates = copy.deepcopy(old_dates)
    raw_before = str(data.get("raw_text") or "")
    body_date, body_method = body_updated_date(raw_before, old_dates)

    mapped = date_map.get(str(json_path.resolve()).casefold())
    if isinstance(mapped, dict) and DATE_VALUE_RE.fullmatch(str(mapped.get("modified") or "")):
        source_date = str(mapped["modified"])
        source_method = str(mapped.get("method") or "workbook")
    else:
        # 仅用于不在根目录文件报告中的历史上传压缩包。明确记录 fallback，
        # 不把这个分支伪装成来自工作簿的精确结果。
        # EN: Only for historical uploaded archives that are not in the root-directory file report. The fallback is recorded explicitly;
        #     this branch is not disguised as an exact result from the workbook.
        # JA: ルートディレクトリのファイルレポートにない、過去にアップロードされたアーカイブ専用。fallback であることを明示的に記録し、
        #     この分岐をワークブック由来の正確な結果に見せかけない。
        candidates = (
            str(old_dates.get("resume_download_date") or ""),
            str(old_dates.get("resume_updated_date") or ""),
        )
        source_date = next((v for v in candidates if DATE_VALUE_RE.fullmatch(v)), "")
        if len(source_date) == 10:
            source_date += " 00:00:00"
        if not source_date:
            source_date = datetime.fromtimestamp(json_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        source_method = "unresolved_legacy_fallback"

    data["dates"] = {
        "resume_updated_date": source_date,
        "resume_download_date": body_date or source_date,
        "sys_created_date": old_dates.get("sys_created_date") or batch_time,
        "sys_updated_date": batch_time,
    }
    return source_method, body_method


def collect_translation_requests(data: dict[str, Any]) -> set[tuple[str, str, str]]:
    requests: set[tuple[str, str, str]] = set()
    sd = data.get("structured_data") or {}
    resumes = [r for r in (sd.get("resumes") or []) if isinstance(r, dict)]
    if not resumes:
        return requests
    for resume in resumes:
        target = LANG_ALIASES.get(str(resume.get("resume_language", resume.get("resume_languge", "zh"))).lower(), "zh")
        for path, text in strings(resume):
            source = source_language(text, target, path[-1] if path else "")
            if source:
                requests.add((source, target, text))
    if not any(LANG_ALIASES.get(str(r.get("resume_language", r.get("resume_languge", "zh"))).lower(), "zh") == "zh" for r in resumes):
        for path, text in strings(resumes[0]):
            source = source_language(text, "zh", path[-1] if path else "")
            if source:
                requests.add((source, "zh", text))
    # 外部快照固定对应中文 0 号位，因此全部按中文校验。
    # EN: External snapshots always correspond to Chinese slot 0, so everything is validated as Chinese.
    # JA: 外部スナップショットは常に中国語の 0 番要素に対応するため、すべて中国語として検証する。
    for value in (v for k, v in sd.items() if k != "resumes"):
        for path, text in strings(value):
            source = source_language(text, "zh", path[-1] if path else "")
            if source:
                requests.add((source, "zh", text))
    return requests


def atomic_json_write(path: Path, data: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    args = parse_args()
    root = args.input_dir.resolve()
    if root != DEFAULT_INPUT.resolve() and DEFAULT_INPUT.resolve() not in root.parents:
        raise SystemExit(f"拒绝处理工作区外目录: {root}")
    paths = [p for p in root.rglob("*.json") if not p.name.startswith("_")]
    if args.limit:
        paths = paths[: args.limit]
    batch_time = datetime.now().astimezone().isoformat(timespec="seconds")
    date_map: dict[str, Any] = {}
    if DATE_MAP_PATH.exists():
        try:
            date_map = json.loads(DATE_MAP_PATH.read_text(encoding="utf-8"))["map"]
        except Exception as exc:
            raise SystemExit(f"源文件日期映射读取失败: {exc}") from exc
    translator = OfflineTranslator(enabled=args.apply and not args.no_translate)
    if translator.enabled:
        requests: set[tuple[str, str, str]] = set()
        for path in paths:
            try:
                candidate = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if isinstance(candidate, dict) and not deletion_reason(candidate, path):
                requests.update(collect_translation_requests(candidate))
        print(f"translation_requests_unique={len(requests)}")
        translator.precompute(requests)
    report: dict[str, Any] = {
        "mode": "apply" if args.apply else "preview",
        "started_at": batch_time,
        "input_dir": str(root), "scanned": len(paths), "delete": [], "changes": [],
        "language_issue_count": 0, "language_issue_samples": [], "created_zh_count": 0,
        "keyword_item_count": 0, "raw_text_rebuilt_count": 0, "errors": [],
        "date_source_method_counts": {}, "download_date_method_counts": {},
        "date_unresolved_samples": [],
    }
    date_source_counts: Counter[str] = Counter()
    download_date_counts: Counter[str] = Counter()
    changed_count = 0
    for index, path in enumerate(paths, 1):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            report["errors"].append({"path": str(path), "error": f"parse:{exc}"})
            continue
        reason = deletion_reason(data, path)
        if reason:
            report["delete"].append({"path": str(path), "reason": reason})
            if args.apply:
                path.unlink()
            continue
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)
        sd = data.get("structured_data")
        if not isinstance(sd, dict):
            report["errors"].append({"path": str(path), "error": "structured_data不是对象"})
            continue
        audit: list[dict[str, str]] = []
        resumes, created = normalize_resume_languages(sd, translator, audit)
        if not resumes:
            report["errors"].append({"path": str(path), "error": "没有有效resume item"})
            continue
        report["created_zh_count"] += int(created)
        for resume in resumes:
            resume["keywords"] = keyword_values(resume)
            report["keyword_item_count"] += 1
        sd["resumes"] = resumes
        sync_top_level(sd, resumes[0], translator, audit)
        source_date_method, download_date_method = update_dates(data, path, date_map, batch_time)
        date_source_counts[source_date_method] += 1
        download_date_counts[download_date_method] += 1
        if source_date_method == "unresolved_legacy_fallback" and len(report["date_unresolved_samples"]) < 100:
            report["date_unresolved_samples"].append(str(path))
        data["raw_text"] = rebuild_raw_text(sd)
        report["raw_text_rebuilt_count"] += 1
        report["language_issue_count"] += len(audit)
        for item in audit[: max(0, 300 - len(report["language_issue_samples"]))]:
            report["language_issue_samples"].append({"file": str(path), **item})
        after = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if before != after:
            changed_count += 1
            report["changes"].append({"path": str(path), "language_issues": len(audit), "created_zh": created, "resume_items": len(resumes)})
            if args.apply:
                atomic_json_write(path, data)
        if index % 500 == 0:
            print(f"processed={index}/{len(paths)} delete={len(report['delete'])} changed={changed_count} lang_issues={report['language_issue_count']}")
    translator.save()
    report["changed_count"] = changed_count
    report["deleted_count"] = len(report["delete"])
    report["translation_calls"] = translator.calls
    report["translation_failures"] = translator.failures[:100]
    report["delete_reason_counts"] = dict(Counter(x["reason"] for x in report["delete"]))
    report["date_source_method_counts"] = dict(date_source_counts)
    report["download_date_method_counts"] = dict(download_date_counts)
    report["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    report_path = root / ("_all_json_batch_apply_report.json" if args.apply else "_all_json_batch_preview.json")
    atomic_json_write(report_path, report)
    print(json.dumps({k: report[k] for k in (
        "mode", "scanned", "deleted_count", "changed_count", "language_issue_count",
        "created_zh_count", "keyword_item_count", "raw_text_rebuilt_count", "translation_calls"
    )}, ensure_ascii=False, indent=2))
    print(f"report={report_path}")
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
