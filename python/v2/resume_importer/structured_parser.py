from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .parser import ResumeParser


DATE_RANGE = re.compile(
    r"(?P<start>(?:19|20)\d{2}(?:[./\-年]\d{1,2})?)"
    r"\s*(?:~|～|—|–|至|到|－|-)\s*"
    r"(?P<end>(?:(?:19|20)\d{2}(?:[./\-年]\d{1,2})?)|"
    r"至今|现在|目前|現在|Present|Now)",
    flags=re.IGNORECASE,
)

EDUCATION_RANKS = {
    "高中": 1,
    "中专": 2,
    "大专": 3,
    "本科": 4,
    "学士": 4,
    "硕士": 5,
    "修士": 5,
    "博士": 6,
}

LANGUAGE_PATTERNS = (
    ("普通话", r"普通话|国语|中文|汉语|Mandarin|Chinese"),
    ("粤语", r"粤语|广东话|Cantonese"),
    ("英语", r"英语|英文|英語|English|CET[-\s]?[46]|TEM[-\s]?[48]|IELTS|TOEFL"),
    ("日语", r"日语|日文|日本語|Japanese|JLPT|N[1-5]\b"),
    ("韩语", r"韩语|韓国語|朝鲜语|Korean|TOPIK"),
    ("德语", r"德语|ドイツ語|German|Deutsch"),
    ("法语", r"法语|フランス語|French|Français"),
    ("西班牙语", r"西班牙语|スペイン語|Spanish|Español"),
    ("俄语", r"俄语|ロシア語|Russian"),
)

CERTIFICATE_SECTION_HEADINGS = re.compile(
    r"^(?:所获证书|获得证书|证书(?:与资质|及资质|列表)?|资格证书|"
    r"专业资格|职业资格|认证(?:与证书)?|"
    r"certificates?|certifications?|credentials?|licenses?|"
    r"資格|免許|資格・免許|保有資格)\s*[:：]?$",
    flags=re.IGNORECASE,
)
CERTIFICATE_SECTION_STOPS = re.compile(
    r"^(?:工作经历|工作经验|职业经历|教育经历|教育背景|项目经历|"
    r"培训经历|语言能力|技能|自我评价|求职意向|"
    r"work(?:ing)?\s+experience|employment\s+history|education|"
    r"projects?|training|languages?|skills?|professional\s+summary|"
    r"職務経歴|学歴|研修経歴|語学力)\s*[:：]?$",
    flags=re.IGNORECASE,
)
CERTIFICATE_SIGNAL = re.compile(
    r"证书|认证|资格|执照|certificate|certification|certified|"
    r"credential|license|licence|注册会计师|\bCPA\b|\bACCA\b|"
    r"\bCFA\b|\bPMP\b|\bCIA\b|\bCISA\b|\bFRM\b|\bJLPT\b|"
    r"\bCET[-\s]?[46]\b|\bTEM[-\s]?[48]\b|教師資格|免許",
    flags=re.IGNORECASE,
)
ENGLISH_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

COMMON_CHINESE_SURNAMES = frozenset(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华"
    "金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花"
    "方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时"
    "傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝"
    "明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾"
    "路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯"
    "管卢莫房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉钮龚程嵇"
    "邢滑裴陆荣翁荀羊甄家封芮羿储靳汲邴糜松井段富巫乌焦巴弓"
    "牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘厉戎祖武符刘"
    "景詹束龙叶幸司韶黎乔苍双闻莘党翟谭贡劳姬申扶堵冉宰郦雍"
    "郤璩桑桂濮牛寿通边扈燕冀浦尚农温别庄晏柴瞿阎连习容向古"
    "易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚"
    "越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾沙养鞠须丰巢关"
    "蒯相查后荆红游竺权逯盖益桓公仉督岳帅缑亢况郈有琴归海晋"
    "楚闫"
)


def normalized_text(value: str | None) -> str:
    return re.sub(r"[\s\-_.·・（）()\[\]【】]+", "", value or "").casefold()


PERSON_FOLDER_EXCLUSIONS = re.compile(
    r"简历|人才|候选|推荐|报告|销售|市场|产品|生产|质量|采购|"
    r"财务|法务|人事|行政|物流|技术|工程|医药|医疗|化工|审计|"
    r"日语|英语|德语|翻译|应届|岗位|职位|客户|资料|模板|"
    r"北京|上海|广州|深圳|天津|重庆|河北|河南|福建|大金|"
    r"旭化成|蓝杰|纽培|Kas|G7|测试",
    flags=re.IGNORECASE,
)


def candidate_name_hint_from_path(source_path: str | Path | None) -> str | None:
    if not source_path:
        return None
    path = Path(source_path)
    for parent in list(path.parents)[:4]:
        value = re.sub(r"\s+", "", parent.name).strip("._-－—–")
        if (
            re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value)
            and not PERSON_FOLDER_EXCLUSIONS.search(value)
            and not re.search(r"(?:先生|女士|小姐)$", value)
        ):
            return value
    return None


def fingerprint(*values: Any) -> str:
    joined = "\x1f".join(normalized_text(str(value or "")) for value in values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _ym(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"((?:19|20)\d{2})(?:[./\-年](\d{1,2}))?", value)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2) or 1):02d}"


def _range(text: str) -> tuple[str | None, str | None, bool]:
    match = DATE_RANGE.search(text)
    if not match:
        return None, None, False
    end_raw = match.group("end")
    current = bool(re.search(r"至今|现在|目前|現在|Present|Now", end_raw, re.I))
    return _ym(match.group("start")), None if current else _ym(end_raw), current


def _value(text: str, labels: str, limit: int = 191) -> str | None:
    match = re.search(
        rf"(?:{labels})\s*[:：]\s*([^\n]{{1,{limit}}})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    value = match.group(1).strip()
    value = re.split(
        r"\s+(?=(?:工作地点|地点|勤務地|所在部门|部门|部署|"
        r"汇报对象|直属上级|下属人数|管理人数|职位|职务|岗位|"
        r"薪酬状况|薪资|薪酬|工资|給与|职责业绩|工作业绩|"
        r"学历|学位|教育程度|专业|専攻|学校|院校|毕业院校|"
        r"学院|学部|GPA|成绩)"
        r"\s*[:：])",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    if re.match(
        r"^(?:工作地点|地点|勤務地|所在部门|部门|部署|汇报对象|"
        r"直属上级|下属人数|管理人数|职位|职务|岗位|薪酬状况|"
        r"薪资|薪酬|工资|給与|职责业绩|工作业绩)\s*[:：]?",
        value,
        flags=re.IGNORECASE,
    ):
        return None
    return value or None


def _blocks(raw: str | None) -> list[str]:
    if not raw:
        return []
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    starts = [index for index, line in enumerate(lines) if DATE_RANGE.search(line)]
    if not starts:
        return ["\n".join(lines)]
    result: list[str] = []
    for number, original_start in enumerate(starts):
        start = (
            0
            if original_start > 0 and number == 0
            and not DATE_RANGE.search(lines[0])
            else original_start
        )
        end = starts[number + 1] if number + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            result.append(block)
    return result


def _first_line_matching(block: str, pattern: str) -> str | None:
    for line in block.splitlines():
        if re.search(pattern, line, flags=re.IGNORECASE):
            return line.strip()
    return None


def _strip_dates(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = DATE_RANGE.sub("", value)
    cleaned = re.sub(
        r"[（(]\s*\d+\s*年(?:\d+\s*个?月)?\s*[）)]",
        "",
        cleaned,
    )
    cleaned = cleaned.strip(" |｜,，;；-—–")
    return cleaned or None


def _project_blocks(raw: str | None) -> list[str]:
    """按项目日期边界切分项目经历，兼容日期被 Word 拆成两行的模板。

    EN: Split project history at project date boundaries, supporting templates where Word splits a date over two lines.

    JA: プロジェクトの日付の境界でプロジェクト経験を分割する。Word が日付を 2 行に分けたテンプレートにも対応する。
    """
    if not raw:
        return []
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return []
    year_month = r"(?:19|20)\d{2}[./\-年]\d{1,2}"
    start_only = re.compile(rf"^{year_month}\s*[-—–~～至到－]?\s*$", re.I)
    end_only = re.compile(rf"^(?:{year_month}|至今|现在|目前|Present|Now)\s*$", re.I)
    combined = re.compile(
        rf"{year_month}\s*(?:~|～|—|–|至|到|－|-)\s*(?:{year_month}|至今|现在|目前|Present|Now)",
        re.I,
    )
    starts: list[int] = []
    for idx, line in enumerate(lines):
        if combined.search(line) or (start_only.match(line) and idx + 1 < len(lines) and end_only.match(lines[idx + 1])):
            starts.append(idx)
    if not starts:
        return ["\n".join(lines)]
    result: list[str] = []
    for pos, start_idx in enumerate(starts):
        end_idx = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        block_lines = lines[start_idx:end_idx]
        if block_lines:
            result.append("\n".join(block_lines).strip())
    return result


def _salary(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    period = "annual" if re.search(r"年薪|年収|/年", raw) else "monthly"
    currency = "CNY"
    if re.search(r"日元|円|JPY", raw, re.I):
        currency = "JPY"
    elif re.search(r"美元|USD|\$", raw, re.I):
        currency = "USD"
    annual_min, annual_max = ResumeParser._normalize_salary(raw, period)
    numbers = [
        float(item)
        for item in re.findall(r"\d+(?:\.\d+)?", raw.replace(",", ""))
    ]
    minimum = numbers[0] if numbers else None
    maximum = numbers[1] if len(numbers) > 1 else minimum
    if minimum is not None and "万" in raw:
        minimum *= 10000
        maximum = (maximum or minimum) * 10000
    return {
        "salary_raw": raw[:100],
        "salary_currency": currency,
        "salary_period": period,
        "salary_min": minimum,
        "salary_max": maximum,
        "annual_salary_min": annual_min,
        "annual_salary_max": annual_max,
    }


class StructuredResumeParser:
    def __init__(self) -> None:
        self.base = ResumeParser()

    def parse(
        self,
        text: str,
        filename: str = "",
        source_path: str | Path | None = None,
    ) -> dict[str, Any]:
        profile = self.base.parse(text, filename)
        name_confidence = self._name_confidence(
            profile.get("full_name"), filename
        )
        path_name_hint = candidate_name_hint_from_path(source_path)
        if name_confidence == "low" and path_name_hint:
            profile["full_name"] = path_name_hint
            name_confidence = "high"
        work_experiences = self._work(profile)
        education_experiences = self._education(profile)
        if work_experiences:
            latest_work = max(
                work_experiences,
                key=lambda item: item.get("start_ym") or "",
            )
            profile["current_company"] = (
                profile.get("current_company")
                or latest_work.get("company_name")
            )
            profile["current_position"] = (
                profile.get("current_position")
                or latest_work.get("position_name")
            )
            profile["current_salary"] = (
                profile.get("current_salary")
                or latest_work.get("salary_raw")
            )
            if profile.get("years_experience") is None:
                profile["years_experience"] = self._experience_years(
                    work_experiences
                )
        profile.update(
            {
                "name_normalized": normalized_text(profile.get("full_name")),
                "name_confidence": name_confidence,
                "phone_normalized": self._normalize_phone(profile.get("phone")),
                "email_normalized": (
                    (profile.get("email") or "").strip().casefold() or None
                ),
                "work_experiences": work_experiences,
                "education_experiences": education_experiences,
                "project_experiences": self._generic_experiences(
                    profile.get("project_experience"), "project"
                ),
                "training_experiences": self._generic_experiences(
                    profile.get("training_experience"), "training"
                ),
                "languages": self._languages(
                    text, profile.get("language_ability")
                ),
                "certificates": self._certificates(text),
                "communication_assessment": (
                    self._communication_assessment(text)
                ),
                "job_preferences": self._job_preferences(profile),
            }
        )
        return profile

    @staticmethod
    def _experience_years(entries: list[dict[str, Any]]) -> float | None:
        intervals: list[tuple[int, int]] = []
        from datetime import date

        now = date.today()
        for entry in entries:
            start = entry.get("start_ym")
            end = entry.get("end_ym")
            if not start:
                continue
            try:
                start_year, start_month = map(int, start.split("-"))
                start_value = start_year * 12 + start_month - 1
                if end:
                    end_year, end_month = map(int, end.split("-"))
                    end_value = end_year * 12 + end_month
                elif entry.get("is_current"):
                    end_value = now.year * 12 + now.month
                else:
                    continue
                if end_value > start_value:
                    intervals.append((start_value, end_value))
            except (TypeError, ValueError):
                continue
        if not intervals:
            return None
        intervals.sort()
        merged: list[list[int]] = []
        for start, end in intervals:
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        months = sum(end - start for start, end in merged)
        return round(months / 12, 1)

    @staticmethod
    def _normalize_phone(value: str | None) -> str | None:
        if not value:
            return None
        digits = re.sub(r"\D", "", value)
        if digits.startswith("86") and len(digits) == 13:
            digits = digits[2:]
        if digits.startswith("81") and len(digits) in {12, 13}:
            digits = "0" + digits[2:]
        return digits or None

    def _work(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for sequence, block in enumerate(
            _blocks(profile.get("work_experience")), 1
        ):
            start, end, current = _range(block)
            company = _value(block, r"公司(?:名称)?|企业名称|勤務先")
            inline_position = None
            if company is None:
                company_line = _strip_dates(
                    _first_line_matching(
                        block,
                        r"有限公司|有限责任公司|股份有限公司|集团|研究所|研究中心|研究院|"
                        r"株式会社|会社|公司|Company|Corp|Institute|Center",
                    )
                )
                company_match = re.search(
                    r"^(.{2,191}?(?:有限公司|有限责任公司|股份有限公司|"
                    r"集团|研究所|研究中心|研究院|株式会社|会社|公司|Company|Corp\.?|Institute|Center))"
                    r"(?:\s+|[·•|｜])*(.*)$",
                    company_line or "",
                    flags=re.IGNORECASE,
                )
                if company_match:
                    company = company_match.group(1).strip()
                    inline_position = (
                        company_match.group(2).strip(" |｜,，;；") or None
                    )
                else:
                    company = company_line
            position = _value(block, r"职位|职务|岗位|役職|Position")
            position = position or inline_position
            if position is None:
                lines = [
                    line.strip() for line in block.splitlines() if line.strip()
                ]
                for line in lines[1:4]:
                    if (
                        len(line) <= 100
                        and not re.search(r"[:：]|薪|地点|部门|汇报|下属", line)
                        and not DATE_RANGE.search(line)
                    ):
                        position = line
                        break
            salary_raw = _value(
                block, r"薪酬状况|薪资|薪酬|工资|給与|Salary", 100
            )
            responsibility_text = _value(
                block,
                r"工作内容|工作职责|职责描述|职责|業務内容|職務内容|"
                r"Responsibilities?|Duties",
                4000,
            )
            if responsibility_text is None:
                block_lines = [
                    line.strip()
                    for line in block.splitlines()
                    if line.strip()
                ]
                # 第一行通常是“日期 公司 职位”；后续行才是工作内容。
                # EN: The first line is usually "date company position"; only the following lines are job content.
                # JA: 1 行目は通常「日付 会社 職位」で、その後の行が業務内容である。
                content_lines = block_lines[1:] if len(block_lines) > 1 else []
                content_lines = [
                    line
                    for line in content_lines
                    if not re.match(
                        r"^(?:薪酬状况|薪资|薪酬|工资|給与|所在部门|"
                        r"工作地点|汇报对象|下属人数)\s*[:：]",
                        line,
                        flags=re.IGNORECASE,
                    )
                ]
                responsibility_text = "\n".join(content_lines).strip() or None
            entry = {
                "sequence_no": sequence,
                "company_name": company,
                "company_normalized": normalized_text(company) or None,
                "industry_name": _value(block, r"所属行业|行业|業界"),
                "department_name": _value(block, r"所在部门|部门|部署"),
                "position_name": position,
                "location_name": _value(block, r"工作地点|地点|勤務地"),
                "start_ym": start,
                "end_ym": end,
                "is_current": current,
                "date_precision": "month" if start else None,
                "report_to": _value(block, r"汇报对象|上司|直属上级"),
                "subordinate_count": self._integer(
                    _value(block, r"下属人数|管理人数", 30)
                ),
                "responsibilities": responsibility_text,
                "achievements": _value(
                    block, r"工作业绩|职责业绩|业绩", 2000
                ),
                "raw_text": block,
                **_salary(salary_raw),
            }
            entry["fingerprint"] = fingerprint(
                company, position, start, end or "current"
            )
            result.append(entry)

        if not result and (
            profile.get("current_company") or profile.get("current_position")
        ):
            entry = {
                "sequence_no": 1,
                "company_name": profile.get("current_company"),
                "company_normalized": normalized_text(
                    profile.get("current_company")
                ) or None,
                "industry_name": profile.get("current_industry"),
                "position_name": profile.get("current_position"),
                "salary_raw": profile.get("current_salary"),
                "annual_salary_min": profile.get("current_annual_salary_min"),
                "annual_salary_max": profile.get("current_annual_salary_max"),
                "is_current": True,
                "raw_text": profile.get("work_experience"),
            }
            entry["fingerprint"] = fingerprint(
                entry["company_name"], entry["position_name"], "current"
            )
            result.append(entry)
        return result

    def _education(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for sequence, block in enumerate(
            _blocks(profile.get("education_experience")), 1
        ):
            start, end, _current = _range(block)
            school_line = None
            school = _value(block, r"学校|院校|毕业院校|最終学歴")
            if school is None:
                school_line = _strip_dates(
                    _first_line_matching(
                        block, r"大学|学院|学校|University|College"
                    )
                )
                school_match = re.search(
                    r"^(.{2,100}?(?:大学|学院|学校|University|College))"
                    r"(?:\s+|/|｜|$)",
                    school_line or "",
                    flags=re.IGNORECASE,
                )
                school = (
                    school_match.group(1).strip()
                    if school_match
                    else school_line
                )
            level = next(
                (name for name in EDUCATION_RANKS if name in block),
                profile.get("education_level"),
            )
            major = _value(block, r"专业|専攻|Major")
            if major is None and school and school_line:
                remainder = school_line[len(school) :].strip(" /｜|,，")
                remainder = re.sub(
                    r"(?:博士|硕士|修士|本科|学士|大专|中专|高中)$",
                    "",
                    remainder,
                ).strip(" /｜|,，")
                if remainder:
                    major = remainder[:191]
            entry = {
                "sequence_no": sequence,
                "school_name": school,
                "school_normalized": normalized_text(school) or None,
                "education_level": level,
                "education_rank": EDUCATION_RANKS.get(level or ""),
                "education_type": _value(block, r"学历类型|学习形式"),
                "major_name": major,
                "college_name": _value(block, r"学院|学部"),
                "city_name": _value(block, r"城市|地点|所在地"),
                "start_ym": start,
                "end_ym": end,
                "date_precision": "month" if start else None,
                "gpa": _value(block, r"GPA|成绩"),
                "is_highest": False,
                "raw_text": block,
            }
            entry["fingerprint"] = fingerprint(
                school, major, level, start, end
            )
            result.append(entry)

        if not result and (
            profile.get("school") or profile.get("education_level")
        ):
            entry = {
                "sequence_no": 1,
                "school_name": profile.get("school"),
                "school_normalized": normalized_text(profile.get("school"))
                or None,
                "education_level": profile.get("education_level"),
                "education_rank": EDUCATION_RANKS.get(
                    profile.get("education_level") or ""
                ),
                "major_name": profile.get("major"),
                "start_ym": profile.get("education_start_date"),
                "end_ym": profile.get("education_end_date"),
                "date_precision": "month",
                "is_highest": True,
                "raw_text": profile.get("education_experience"),
            }
            entry["fingerprint"] = fingerprint(
                entry["school_name"],
                entry["major_name"],
                entry["education_level"],
                entry["start_ym"],
                entry["end_ym"],
            )
            result.append(entry)
        if result:
            highest = max(
                range(len(result)),
                key=lambda index: result[index].get("education_rank") or 0,
            )
            result[highest]["is_highest"] = True
        return result

    @staticmethod
    def _generic_experiences(
        raw: str | None, experience_type: str
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        source_blocks = _blocks(raw)
        if experience_type == "project":
            source_blocks = _project_blocks(raw)
        for sequence, block in enumerate(source_blocks, 1):
            start, end, _current = _range(block)
            lines = [line for line in block.splitlines() if line.strip()]
            title = _strip_dates(lines[0]) if lines else None
            if experience_type == "project":
                # 日期已经单独存入 start_ym/end_ym；日期后的第一行才是项目名。
                # EN: The dates are already stored separately in start_ym/end_ym; the first line after the dates is the project name.
                # JA: 日付はすでに start_ym/end_ym に個別に保存済みで、日付の後の最初の行がプロジェクト名である。
                date_head = re.compile(
                    r"^(?:(?:19|20)\d{2}[./\-年]\d{1,2}\s*[-—–~～至到－]?|至今|现在|目前|Present|Now)\s*$",
                    re.IGNORECASE,
                )
                while lines and (date_head.match(lines[0]) or DATE_RANGE.fullmatch(lines[0].strip())):
                    lines.pop(0)
                while lines and lines[0].strip() in ("项目经历", "项目经验", "项目描述", "项目简介"):
                    lines.pop(0)
                title = lines[0].strip() if lines else None
                # 某些模板把“项目名称：xxx”作为项目标题。
                # EN: Some templates use "项目名称：xxx" (project name: xxx) as the project heading.
                # JA: テンプレートによっては「项目名称：xxx」（プロジェクト名：xxx）をプロジェクトの見出しにしている。
                if title and re.match(r"^(?:项目名称|项目名|项目标题)\s*[:：]", title):
                    title = re.split(r"[:：]", title, 1)[1].strip() or None
                block_for_content = "\n".join(lines).strip()
                entry = {
                    "sequence_no": sequence,
                    "project_name": title,
                    "company_or_client": _value(block, r"所属公司|客户"),
                    "role_name": _value(block, r"项目角色|担任角色|职位"),
                    "start_ym": start,
                    "end_ym": end,
                    "description": block_for_content,
                    "raw_text": block_for_content,
                }
            else:
                entry = {
                    "sequence_no": sequence,
                    "organization_name": _value(block, r"培训机构|机构")
                    or title,
                    "training_name": _value(block, r"培训名称|课程"),
                    "start_ym": start,
                    "end_ym": end,
                    "certificate_name": _value(block, r"证书|认证"),
                    "description": block,
                    "raw_text": block,
                }
            entry["fingerprint"] = fingerprint(title, start, end, block[:100])
            result.append(entry)
        return result

    @staticmethod
    def _languages(text: str, section: str | None) -> list[dict[str, Any]]:
        search_text = section or text
        result: list[dict[str, Any]] = []
        for language, pattern in LANGUAGE_PATTERNS:
            matches = [
                line.strip()
                for line in search_text.splitlines()
                if re.search(pattern, line, flags=re.IGNORECASE)
            ]
            if not matches:
                continue
            raw = "；".join(matches[:3])[:500]
            rank = 3
            if re.search(r"母语|ネイティブ|native", raw, re.I):
                rank = 5
            elif re.search(
                r"精通|流利|熟练|ビジネス|fluent|advanced|N1|CET-?6",
                raw,
                re.I,
            ):
                rank = 4
            elif re.search(
                r"一般|日常|良好|中级|intermediate|N2|CET-?4",
                raw,
                re.I,
            ):
                rank = 3
            elif re.search(r"初级|基础|beginner|N[45]", raw, re.I):
                rank = 2
            result.append(
                {
                    "language_name": language,
                    "language_normalized": normalized_text(language),
                    "proficiency_raw": raw,
                    "proficiency_rank": rank,
                    "is_native": bool(re.search(r"母语|native", raw, re.I)),
                    "raw_text": raw,
                }
            )
        return result

    @staticmethod
    def _communication_assessment(text: str) -> str | None:
        lines = [line.strip() for line in text.splitlines()]
        heading = re.compile(
            r"^(?:顾问评价|顾问评语|猎头评语|沟通评估|推荐意见|推荐理由|"
            r"コンサルタントコメント|推薦理由|"
            r"consultant\s+(?:evaluation|comments?)|"
            r"headhunter[’']?s?\s+evaluation"
            r"(?:\s+and\s+career\s+objectives?)?)\s*[:：]?\s*(.*)$",
            flags=re.IGNORECASE,
        )
        stop = re.compile(
            r"^(?:薪资水平|薪酬状况|求职意向|基本信息|个人信息|"
            r"教育经历|学历信息|工作经历|职业经历|项目经历|培训经历|"
            r"语言能力|技能|证书|"
            r"salary|career\s+objectives?|personal\s+details|education|"
            r"work(?:ing)?\s+experience|employment\s+history|projects?|"
            r"training|languages?|skills?|certificates?)\s*[:：]?$",
            flags=re.IGNORECASE,
        )
        for index, line in enumerate(lines):
            match = heading.match(line)
            if not match:
                continue
            values: list[str] = []
            inline = match.group(1).strip()
            if inline:
                values.append(inline)
            for candidate in lines[index + 1:]:
                if stop.match(candidate):
                    break
                if heading.match(candidate):
                    break
                if candidate:
                    values.append(candidate)
            value = "\n".join(values).strip()
            return value or None
        return None

    @classmethod
    def _certificates(cls, text: str) -> list[dict[str, Any]]:
        lines = [line.strip() for line in text.splitlines()]
        candidates: list[str] = []
        capturing = False
        for index, line in enumerate(lines):
            if not line:
                continue
            if CERTIFICATE_SECTION_HEADINGS.match(line):
                capturing = True
                continue
            if capturing and CERTIFICATE_SECTION_STOPS.match(line):
                capturing = False
            if capturing:
                if cls._looks_like_date_only(line):
                    next_line = next(
                        (
                            value
                            for value in lines[index + 1:index + 3]
                            if value
                        ),
                        "",
                    )
                    if next_line and not CERTIFICATE_SECTION_STOPS.match(
                        next_line
                    ):
                        combined = f"{line} {next_line}"
                        if cls._strong_certificate_line(
                            combined, in_certificate_section=True
                        ):
                            candidates.append(combined)
                    continue
                if cls._strong_certificate_line(
                    line, in_certificate_section=True
                ):
                    candidates.append(line)
                continue
            if re.search(
                r"(?:证书名称|认证名称|资格名称|Certificate\s+Name|"
                r"Certification)\s*[:：]",
                line,
                flags=re.IGNORECASE,
            ):
                candidates.append(line)
                continue
            if cls._strong_certificate_line(
                line, in_certificate_section=False
            ):
                candidates.append(line)

        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in candidates:
            certificate = cls._certificate_from_line(raw)
            if not certificate:
                continue
            key = certificate["fingerprint"]
            if key in seen:
                continue
            seen.add(key)
            result.append(certificate)
        return result

    @staticmethod
    def _strong_certificate_line(
        line: str, *, in_certificate_section: bool
    ) -> bool:
        value = re.sub(r"\s+", " ", line).strip()
        if not value or len(value) > 400:
            return False
        if re.fullmatch(
            r"资格技能|专业资格|职业资格|证书信息|认证信息|"
            r"证书说明|资格证书|技能资格|"
            r"certificates?|certifications?|credentials?|licenses?",
            value,
            flags=re.IGNORECASE,
        ):
            return False
        if re.search(
            r"最终毕业院校|最终学历|软件名\s*水\s*平|"
            r"资格[/／]?\s*证书\s*取得年|应用水平",
            value,
        ):
            return False
        personal_attainment = re.search(
            r"(?:获得|取得|考取|持有|通过|具备|拥有|获颁|合格).{0,40}"
            r"(?:证书|资格|认证|执照|免許)|"
            r"(?:证书|资格|認定|免許).{0,20}(?:获得|取得|合格)",
            value,
            flags=re.IGNORECASE,
        )
        if personal_attainment:
            return True
        if re.search(
            r"^(?:公司|组织|机构|项目|产品|工作|职责|业绩|"
            r"Company|Organisation|Organization|Project|Product|Duty|"
            r"Responsibilities?)\s*(?:Description)?\s*[:：]",
            value,
            flags=re.IGNORECASE,
        ):
            return False
        if re.search(
            r"认证工程师|认证审核|审核工作|密码认证|测试认证|"
            r"软件\s*license|employees?|客户长期合作",
            value,
            flags=re.IGNORECASE,
        ):
            return False
        standalone = re.search(
            r"\b(?:PMP|CPA|ACCA|CFA|CIA|CISA|FRM|JLPT|"
            r"CET[-\s]?[46]|TEM[-\s]?[48])\b|"
            r"Certified\s+[A-Za-z][A-Za-z &/\-]{2,80}|"
            r"(?:大学英语[四六]级|日语能力考试[一二三四五1-5N](?:级)?|"
            r"日本語能力試験\s*N?[1-5]|J-TEST|"
            r"全国计算机等级考试|中级工程师|高级工程师|"
            r"[A-Z][1-9]驾照|软件工程师证书|簿记[一二三1-3]级|"
            r"通訳資格|教师资格证|律师资格证|注册会计师)",
            value,
            flags=re.IGNORECASE,
        )
        if standalone and len(value) <= 191:
            return True
        return bool(
            in_certificate_section
            and CERTIFICATE_SIGNAL.search(value)
            and len(value) <= 191
        )

    @classmethod
    def _certificate_from_line(
        cls, raw: str
    ) -> dict[str, Any] | None:
        value = re.sub(r"\s+", " ", raw).strip(" |｜;；,，")
        if not value or cls._looks_like_date_only(value):
            return None

        issued_date, issued_precision = cls._certificate_date(
            value,
            (
                r"获得时间|取得时间|颁发日期|发证日期|取证时间|"
                r"issued|awarded|obtained|取得日|交付日",
            ),
        )
        expires_date, expires_precision = cls._certificate_date(
            value,
            (
                r"有效期至|到期时间|失效日期|expires?|expiry|"
                r"有効期限",
            ),
        )
        if issued_date is None:
            issued_date, issued_precision = cls._certificate_date(value)

        issuer = cls._labeled_value(
            value,
            r"颁发机构|发证机构|认证机构|Issuer|Issued\s+by|発行機関",
        )
        certificate_no = cls._labeled_value(
            value,
            r"证书编号|证书号|Certificate\s+No\.?|Credential\s+ID|登録番号",
        )
        labeled_name = cls._labeled_value(
            value,
            r"证书名称|认证名称|资格名称|Certificate\s+Name|Certification",
        )
        name = labeled_name or value
        name = re.sub(
            r"^(?:(?:19|20)\d{2}\s*(?:[./\-年]\s*\d{1,2})?"
            r"(?:[./\-月]\s*\d{1,2}日?)?|"
            r"(?:" + "|".join(ENGLISH_MONTHS) + r")\s+(?:19|20)\d{2})"
            r"\s*[-–—:：]?\s*",
            "",
            name,
            flags=re.IGNORECASE,
        )
        name = re.split(
            r"\s+(?=(?:获得时间|取得时间|颁发日期|发证日期|有效期至|"
            r"到期时间|Issuer|Issued\s+by|Certificate\s+No\.?|"
            r"Credential\s+ID)\s*[:：])",
            name,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" -–—:：,，;；")
        name = re.sub(
            r"^(?:证书名称|认证名称|资格名称|Certificate\s+Name|"
            r"Certification)\s*[:：]\s*",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
        name = re.sub(
            r"^(?:年\s+|英\s*语\s*[:：]\s*|语言能力\s*[:：]\s*)",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
        if (
            len(name) < 2
            or len(name) > 191
            or name.casefold() in {
                "certificate",
                "certificates",
                "certification",
                "certifications",
                "证书",
                "资格证书",
            }
        ):
            return None

        normalized_name = normalized_text(name)
        entry = {
            "certificate_name": name,
            "normalized_name": normalized_name,
            "issuer_name": issuer,
            "issued_date": issued_date,
            "issued_date_precision": issued_precision,
            "expires_date": expires_date,
            "expires_date_precision": expires_precision,
            "certificate_no": certificate_no,
            "certificate_type": cls._certificate_type(name),
            "confidence": 75.0,
            "raw_text": raw,
        }
        entry["fingerprint"] = fingerprint(
            normalized_name,
            issued_date,
            issuer,
            certificate_no,
        )
        return entry

    @staticmethod
    def _labeled_value(text: str, label_pattern: str) -> str | None:
        match = re.search(
            rf"(?:{label_pattern})\s*[:：]\s*"
            r"(.+?)(?=\s+(?:获得时间|取得时间|颁发日期|发证日期|"
            r"有效期至|到期时间|Issuer|Issued\s+by|"
            r"Certificate\s+No\.?|Credential\s+ID)\s*[:：]|$)",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip(" ,，;；")[:191] if match else None

    @staticmethod
    def _looks_like_date_only(value: str) -> bool:
        return re.fullmatch(
            r"(?:19|20)\d{2}(?:\s*[./\-年]\s*\d{1,2})?"
            r"(?:\s*[./\-月]\s*\d{1,2}日?)?"
            r"|(?:" + "|".join(ENGLISH_MONTHS) + r")\s+(?:19|20)\d{2}",
            value.strip(),
            flags=re.IGNORECASE,
        ) is not None

    @staticmethod
    def _certificate_date(
        text: str, labels: tuple[str, ...] | None = None
    ) -> tuple[str | None, str | None]:
        search_text = text
        if labels:
            label_match = re.search(
                rf"(?:{'|'.join(labels)})\s*[:：]?\s*(.+)$",
                text,
                flags=re.IGNORECASE,
            )
            if not label_match:
                return None, None
            search_text = label_match.group(1)
        full = re.search(
            r"((?:19|20)\d{2})\s*[./\-年]\s*(\d{1,2})"
            r"(?:\s*[./\-月]\s*(\d{1,2})日?)?",
            search_text,
        )
        if full:
            year, month, day = full.groups()
            precision = "day" if day else "month"
            return (
                f"{year}-{int(month):02d}-{int(day or '1'):02d}",
                precision,
            )
        month_name = re.search(
            r"\b(" + "|".join(ENGLISH_MONTHS) + r")\s+((?:19|20)\d{2})\b",
            search_text,
            flags=re.IGNORECASE,
        )
        if month_name:
            month = ENGLISH_MONTHS[month_name.group(1).casefold()]
            return f"{month_name.group(2)}-{month:02d}-01", "month"
        year = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", search_text)
        if year:
            return f"{year.group(1)}-01-01", "year"
        return None, None

    @staticmethod
    def _certificate_type(name: str) -> str | None:
        if re.search(
            r"JLPT|CET|TEM|IELTS|TOEFL|语言|語学", name, re.IGNORECASE
        ):
            return "language"
        if re.search(
            r"CPA|ACCA|CFA|CIA|CISA|FRM|PMP|会计|审计|律师|"
            r"工程师|教师|资格",
            name,
            re.IGNORECASE,
        ):
            return "professional"
        if re.search(r"驾驶|驾照|license", name, re.IGNORECASE):
            return "license"
        return None

    @staticmethod
    def _job_preferences(profile: dict[str, Any]) -> list[dict[str, Any]]:
        if not any(
            profile.get(key)
            for key in (
                "expected_city",
                "expected_position",
                "expected_salary",
                "expected_industry",
                "employment_type",
                "availability",
            )
        ):
            return []
        return [
            {
                "expected_city": profile.get("expected_city"),
                "expected_position": profile.get("expected_position"),
                "expected_industry": profile.get("expected_industry"),
                "expected_salary_raw": profile.get("expected_salary"),
                "expected_annual_salary_min": profile.get(
                    "expected_annual_salary_min"
                ),
                "expected_annual_salary_max": profile.get(
                    "expected_annual_salary_max"
                ),
                "employment_type": profile.get("employment_type"),
                "availability": profile.get("availability"),
                "job_status": profile.get("current_status"),
                "is_current": True,
            }
        ]

    @staticmethod
    def _integer(value: str | None) -> int | None:
        match = re.search(r"\d+", value or "")
        return int(match.group(0)) if match else None

    @staticmethod
    def _name_confidence(
        value: str | None, filename: str = ""
    ) -> str:
        normalized = normalized_text(value)
        if (
            not normalized
            or value == "待确认姓名"
            or len(value or "") > 60
            or re.search(
                r"简历|履歴|職務|候选|推荐|评估|报告|定稿|工作|"
                r"资产|运营|建设|维护|申请|职位|岗位|个人信息|测试",
                value or "",
                flags=re.IGNORECASE,
            )
            or re.search(r"(?:先生|女士|小姐)$", value or "")
            or re.search(
                r"猎聘|无忧|智联|前程|公司|集团|大学|学院|"
                r"销售|产品|工程师|专员|代表|主管|经理|总监|部长|课长|"
                r"本科|大专|硕士|博士|Trading|Company|Corporation",
                value or "",
                flags=re.IGNORECASE,
            )
        ):
            return "low"
        if (
            value
            and value.casefold() in filename.casefold()
            and (
                re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value)
                or re.fullmatch(
                    r"[A-Z][A-Za-z.'()-]+"
                    r"(?:\s+[A-Z][A-Za-z.'()-]+){1,4}",
                    value,
                )
            )
        ):
            return "high"
        if (
            re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value or "")
            and (value or "")[0] in COMMON_CHINESE_SURNAMES
        ):
            return "high"
        if re.fullmatch(
            r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4}"
            r"(?:\s*\([A-Z][A-Za-z.' -]{1,40}\))?",
            value or "",
        ):
            return "high"
        if (
            re.search(r"[\u3040-\u30ff]", value or "")
            and re.fullmatch(
                r"[\u3040-\u30ff\u4e00-\u9fff・]{2,20}",
                value or "",
            )
        ):
            return "medium"
        return "low"
