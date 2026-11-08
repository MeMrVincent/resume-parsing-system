from __future__ import annotations

import re
from typing import Any


class ResumeParser:
    cities = (
        "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆",
        "武汉", "西安", "天津", "青岛", "厦门", "长沙", "郑州", "宁波", "无锡",
        "合肥", "济南", "福州", "东莞", "佛山", "大连", "沈阳", "昆明", "南昌",
        "南宁", "贵阳", "太原", "石家庄", "长春", "哈尔滨", "海口", "珠海",
        "日本", "东京", "大阪", "横滨", "東京", "横浜", "名古屋", "京都", "神戸",
        "札幌", "福岡", "Tokyo", "Osaka", "Yokohama", "Nagoya", "Kyoto",
        "Kobe", "Sapporo", "Fukuoka",
    )

    def parse(self, text: str, filename: str = "") -> dict[str, Any]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        phone = self._find_phone(text)
        email_match = re.search(
            r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",
            text,
            flags=re.IGNORECASE,
        )

        education = None
        education_keywords = {
            "博士": ("博士", "PhD", "Doctorate"),
            "硕士": ("硕士", "修士", "Master"),
            "本科": ("本科", "学士", "Bachelor"),
            "大专": ("大专", "短大", "Associate"),
            "中专": ("中专", "専門学校"),
            "高中": ("高中", "高等学校", "High School"),
        }
        for level, keywords in education_keywords.items():
            if any(keyword.casefold() in text.casefold() for keyword in keywords):
                education = level
                break

        city = self._current_city(text)
        years_experience = self._years_experience(text)

        education_profile = self._education_profile(lines, text)
        career_profile = self._career_profile(lines, text)
        personal_profile = self._personal_profile(lines, text)
        job_expectation = self._job_expectation(text)

        return {
            "full_name": self._guess_name(lines, filename),
            "gender": self._gender(text, lines),
            "age": self._age(text),
            "birth_date": personal_profile["birth_date"],
            "birth_year": personal_profile["birth_year"],
            "marital_status": personal_profile["marital_status"],
            "political_status": personal_profile["political_status"],
            "height_cm": personal_profile["height_cm"],
            "household_registration": personal_profile["household_registration"],
            "address": personal_profile["address"],
            "postal_code": personal_profile["postal_code"],
            "platform_resume_id": personal_profile["platform_resume_id"],
            "resume_language": self._detect_language(text),
            "phone": phone,
            "email": email_match.group(0).lower() if email_match else None,
            "city": city,
            "education_level": education,
            "school": education_profile["school"],
            "major": education_profile["major"],
            "education_period": education_profile["education_period"],
            "education_start_date": education_profile["education_start_date"],
            "education_end_date": education_profile["education_end_date"],
            "language_ability": self._language_ability(lines, text),
            "years_experience": years_experience,
            "current_company": career_profile["current_company"],
            "current_position": career_profile["current_position"],
            "current_salary": career_profile["current_salary"],
            "current_annual_salary_min": career_profile[
                "current_annual_salary_min"
            ],
            "current_annual_salary_max": career_profile[
                "current_annual_salary_max"
            ],
            "current_industry": career_profile["current_industry"],
            "current_status": career_profile["current_status"],
            "expected_city": job_expectation["expected_city"],
            "expected_position": job_expectation["expected_position"],
            "expected_salary": job_expectation["expected_salary"],
            "expected_annual_salary_min": job_expectation[
                "expected_annual_salary_min"
            ],
            "expected_annual_salary_max": job_expectation[
                "expected_annual_salary_max"
            ],
            "expected_industry": job_expectation["expected_industry"],
            "employment_type": job_expectation["employment_type"],
            "availability": job_expectation["availability"],
            "summary": self._section(
                lines,
                ("优势亮点", "个人优势", "自我评价", "自己紹介", "自己PR",
                 "Professional Summary", "Career Summary"),
                ("职业概况", "技能标签", "工作经历", "工作经验", "職務経歴",
                 "Skills", "Work Experience"),
            ),
            "work_experience": self._section(
                lines,
                ("工作经历", "工作经验", "职业经历", "職務経歴", "職歴",
                 "Work Experience", "Professional Experience", "Employment History"),
                ("教育经历", "教育背景", "学歴", "项目经历", "项目经验", "プロジェクト",
                 "Education", "Project Experience", "自我评价", "技能", "Skills"),
            ),
            "education_experience": self._section(
                lines,
                ("教育经历", "教育背景", "学歴", "Education", "Education Background"),
                ("工作经历", "工作经验", "職務経歴", "项目经历", "项目经验", "プロジェクト",
                 "Work Experience", "Project Experience", "自我评价", "技能", "Skills"),
            ),
            "project_experience": self._section(
                lines,
                ("项目经历", "项目经验", "プロジェクト", "Project Experience", "Projects"),
                ("工作经历", "職務経歴", "教育经历", "教育背景", "学歴",
                 "Work Experience", "Education", "自我评价", "技能", "Skills"),
            ),
            "practice_experience": self._section(
                lines,
                ("学生实践经验", "社会实践", "实习经历", "インターン",
                 "Internship Experience", "Practical Experience"),
                ("培训经历", "语言能力", "工作经历", "教育经历",
                 "Training", "Languages", "Work Experience", "Education"),
            ),
            "training_experience": self._section(
                lines,
                ("培训经历", "研修経歴", "Training Experience", "Training"),
                ("语言能力", "工作经历", "教育经历", "项目经历",
                 "Languages", "Work Experience", "Education", "Projects"),
            ),
        }

    @classmethod
    def _guess_name(cls, lines: list[str], filename: str = "") -> str:
        heading_words = (
            r"简历|履歴書|職務経歴|应聘|求职|个人|候选|推荐|报告|"
            r"定稿|基本|情報|信息|"
            r"学历|学歴|教育|经历|経験|技能|スキル|资格|資格|"
            r"项目|連絡先|联系方式|自我评价|自己紹介"
        )
        for line in lines[:80]:
            labeled = re.match(
                r"^(?:姓名|氏名|名前|Name|Full Name|"
                r"Candidate(?:'s)?\s+name)\s*[:：]\s*(.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if labeled:
                candidate = re.split(
                    r"\s+(?=(?:联系电话|电话|手机|移动电话|E-?mail|邮箱|"
                    r"性别|性別|Gender|Sex|出生年月|生年月日|Born|"
                    r"年龄|年齢|Age|籍贯|現住所|住所|学历|学歴|"
                    r"政治面貌)\s*[:：])",
                    labeled.group(1).strip(),
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip(" |｜,，;；")
                if 1 < len(candidate) <= 60:
                    return candidate

        for line in lines[:10]:
            cv_title = re.match(
                r"^(?:CURRICULUM\s+VITAE|RESUME)\s*[-–—:：]\s*"
                r"([A-Z][A-Za-z.'()\-]+"
                r"(?:[\s_-]+[A-Z][A-Za-z.'()\-]+){1,4})\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if cv_title:
                return re.sub(r"[_]+", " ", cv_title.group(1)).strip()

        filename_name = cls._guess_name_from_filename(filename, heading_words)
        if filename_name:
            return filename_name

        if lines:
            first_line_name = re.match(
                r"^([\u4e00-\u9fff]{2,4})(?=\s*[·•|｜]?\s*"
                r"(?:男|女|\d{2}\s*岁))",
                lines[0],
            )
            if first_line_name:
                return first_line_name.group(1)

        for line_index, line in enumerate(lines[:5]):
            candidate = re.sub(
                r"^(姓名|氏名|名前|Name|Full Name)\s*[:：]\s*",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()
            if (
                line_index < 2
                and
                re.fullmatch(r"[\u3040-\u30ff\u4e00-\u9fff・·]{2,12}", candidate)
                and not re.search(heading_words, candidate)
                and candidate not in cls.cities
                and not re.search(r"[省市区县]$", candidate)
            ):
                return candidate
            if (
                line_index < 2
                and
                re.fullmatch(r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4}", candidate)
                and not re.search(r"Resume|Curriculum|Vitae|Profile", candidate, re.IGNORECASE)
            ):
                return candidate
        return filename_name or "待确认姓名"

    @staticmethod
    def _guess_name_from_filename(filename: str, heading_words: str) -> str | None:
        stem = re.sub(r"\.[^.]+$", "", filename).strip()
        stem = re.sub(r"^\d+[\s_.\-－—–]*", "", stem)
        stem = re.sub(
            r"^(?:无关联职位简历|关联职位简历|候选人简历)"
            r"[\s_\-－—–]*",
            "",
            stem,
        )
        stem = re.sub(
            r"^(?:智联招聘|智联|前程无忧|无忧精英网|51job|猎聘|"
            r"BOSS直聘)[\s_\-—–]*",
            "",
            stem,
            flags=re.IGNORECASE,
        )
        anonymous = re.match(
            r"^([\u4e00-\u9fff]{1,4}(?:先生|女士|小姐))(?=\d|[\s_\-])",
            stem,
        )
        if anonymous:
            return anonymous.group(1)
        leading_liepin_name = re.match(
            r"^([\u4e00-\u9fff]{2,4})(?=\s*[-－—–_]\s*"
            r"(?:\d{2}\s*岁|\d{1,2}\s*年经验|[\u4e00-\u9fff]))",
            stem,
        )
        if leading_liepin_name and not re.search(
            heading_words,
            leading_liepin_name.group(1),
            flags=re.IGNORECASE,
        ):
            return leading_liepin_name.group(1)
        platform_name = re.match(
            r"^([\u4e00-\u9fff]{2,4})(?=\d{1,14}[A-Za-z]?\d*)",
            stem,
        )
        if platform_name:
            return platform_name.group(1)
        chinese_before_english_resume = re.search(
            r"(?:^|[\s_\-])([\u4e00-\u9fff]{2,4})(?=Resume|\bCV\b)",
            stem,
            flags=re.IGNORECASE,
        )
        if chinese_before_english_resume:
            return chinese_before_english_resume.group(1)
        platform_parenthetical = re.match(
            r"^([\u4e00-\u9fff]{2,4})\(\d{5,30}\)",
            stem,
        )
        if platform_parenthetical:
            return platform_parenthetical.group(1)
        for explicit_resume_name in re.finditer(
            r"(?:^|[\s_\-－—–]|\d{6,14})"
            r"([\u4e00-\u9fff]{2,4}?)(?:的)?"
            r"(?:中文|日文|英文|日语|英語)?简历"
            r"(?:$|[\s_\-－—–（）()])",
            stem,
        ):
            candidate = explicit_resume_name.group(1).removesuffix("的")
            if candidate and candidate not in {
                "中文", "日文", "英文", "个人", "求职", "工作",
                "猎聘", "智联", "无忧", "职位",
            }:
                return candidate
        parenthetical_name = re.search(
            r"[（(【\[]\s*([\u4e00-\u9fff](?:\s*[\u4e00-\u9fff]){1,3})"
            r"\s*[）)】\]]",
            stem,
        )
        if parenthetical_name:
            return re.sub(r"\s+", "", parenthetical_name.group(1))
        japanese_title_name = re.search(
            r"(?:履\s*歴\s*書|職務経歴書)\s*[ー－—–_【\[]+\s*"
            r"([\u4e00-\u9fff](?:\s*[\u4e00-\u9fff]){1,3})",
            stem,
        )
        if japanese_title_name:
            return re.sub(r"\s+", "", japanese_title_name.group(1))
        chinese_resume_name = re.search(
            r"(?:^|[\s_\-－—–])"
            r"([\u4e00-\u9fff]{2,4})(?=(?:个人)?简历|履历)",
            stem,
        )
        if (
            chinese_resume_name
            and chinese_resume_name.group(1)
            not in {"中文", "日文", "英文", "个人", "求职"}
        ):
            return chinese_resume_name.group(1)
        segments = re.split(r"[\s_\-－—–（）()\[\]【】]+", stem)
        for segment in segments:
            candidate = segment.strip("·・. ")
            candidate = re.sub(r"\d{1,8}$", "", candidate)
            if not candidate or re.search(heading_words, candidate, re.IGNORECASE):
                continue
            if candidate in ResumeParser.cities or re.search(r"[省市区县]$", candidate):
                continue
            if re.search(
                r"大学|学院|公司|集团|岗位|职位|工程师|担当|经理|顾问|"
                r"中文|日文|英文|模板|报告|推荐|20\d{2}",
                candidate,
                flags=re.IGNORECASE,
            ):
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", candidate):
                return candidate
            if (
                re.search(r"[\u3040-\u30ff]", candidate)
                and re.fullmatch(
                    r"[\u3040-\u30ff\u4e00-\u9fff・]{2,12}",
                    candidate,
                )
            ):
                return candidate

        english = re.search(
            r"\b([A-Z][A-Za-z.'-]+(?:\s*\([A-Z][A-Za-z.'-]+\))?"
            r"(?:\s+[A-Z][A-Za-z.'-]+){1,3})\s+(?:CV|Resume)\b",
            stem,
            flags=re.IGNORECASE,
        )
        if english:
            return english.group(1).strip()
        english_patterns = (
            r"^(?:CV|RESUME|CURRICULUM\s+VITAE)"
            r"[\s_+\-—–]*(?:OF\s+)?"
            r"([A-Z][A-Za-z.'-]+(?:[\s_]+[A-Z][A-Za-z.'-]+){1,4})",
            r"^(?:CV|Resume)[\s_+\-—–]*\("
            r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})\)",
            r"^([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})"
            r"(?:\s*[-_]\s*|$)",
        )
        for pattern in english_patterns:
            match = re.search(pattern, stem, flags=re.IGNORECASE)
            if match:
                candidate = re.sub(r"[_]+", " ", match.group(1)).strip()
                if not re.search(
                    r"Resume|Curriculum|Vitae|Profile|Template",
                    candidate,
                    flags=re.IGNORECASE,
                ):
                    return candidate
        return None

    @staticmethod
    def _gender(text: str, lines: list[str]) -> str | None:
        labeled = re.search(
            r"(?:性别|性別|Gender)\s*[:：]?\s*(男|女|男性|女性|Male|Female)",
            text,
            flags=re.IGNORECASE,
        )
        if labeled:
            value = labeled.group(1).casefold()
            return "男" if value in {"男", "男性", "male"} else "女"
        for line in lines[:20]:
            inline = re.search(
                r"(?:^|[\s·•|｜])(男|女)(?:[\s·•|｜]|$)", line
            )
            if inline:
                return inline.group(1)
        return None

    @staticmethod
    def _age(text: str) -> int | None:
        match = re.search(r"(?:年龄\s*[:：]?\s*|[·•|\s])(\d{2})\s*岁", text[:1000])
        if match:
            value = int(match.group(1))
            if 16 <= value <= 80:
                return value
        return None

    def _current_city(self, text: str) -> str | None:
        labeled = re.search(
            r"(?:目前地点|当前地点|现居地|所在地|Location)\s*[:：]\s*"
            r"([^\n]{2,100})",
            text,
            flags=re.IGNORECASE,
        )
        if labeled:
            value = labeled.group(1)
            city = next(
                (item for item in self.cities if item.casefold() in value.casefold()),
                None,
            )
            if city:
                return city
        return next(
            (item for item in self.cities if item.casefold() in text.casefold()),
            None,
        )

    @staticmethod
    def _years_experience(text: str) -> float | None:
        range_match = re.search(
            r"(\d{1,2})\s*[-~～—–]\s*(\d{1,2})\s*年"
            r"(?:工作|実務|职务|職務)?经验",
            text[:2000],
        )
        if range_match:
            lower = int(range_match.group(1))
            upper = int(range_match.group(2))
            if 0 <= lower <= upper <= 60:
                return float(lower)
        patterns = (
            r"(?:工作|実務|职务|職務)\s*(\d{1,2})\s*年"
            r"(?:\s*(\d{1,2})\s*个?月)?",
            r"(\d{1,2})\s*年\s*(\d{1,2})\s*个?月"
            r"(?:工作|実務|职务|職務)?",
        )
        for pattern in patterns:
            match = re.search(pattern, text[:2000], flags=re.IGNORECASE)
            if match:
                years = int(match.group(1))
                months = int(match.group(2) or 0)
                if years <= 60 and months <= 11:
                    return round(years + months / 12, 1)
        english = re.search(
            r"(\d{1,2}(?:\.\d)?)\+?\s*years?(?:\s+of)?\s+experience",
            text,
            flags=re.IGNORECASE,
        )
        return min(60.0, float(english.group(1))) if english else None

    @staticmethod
    def _career_profile(
        lines: list[str],
        text: str,
    ) -> dict[str, str | None]:
        def labeled(pattern: str) -> str | None:
            match = re.search(pattern + r"\s*[:：]\s*([^\n]{1,191})", text)
            return match.group(1).strip() if match else None

        company = labeled(r"(?:目前公司|当前公司|现公司)")
        position = labeled(r"(?:目前职位|当前职位|现职位)")
        salary_match = re.search(
            r"(目前年薪|当前年薪|目前月薪|当前月薪|目前薪资|当前薪资|"
            r"当前薪资)\s*[:：]\s*([^\n]{1,191})",
            text,
        )
        salary = salary_match.group(2).strip() if salary_match else None
        industry = labeled(r"(?:目前行业|当前行业)")
        status = labeled(r"(?:目前状态|当前状态|求职状态)")

        if (company is None or position is None) and len(lines) >= 2:
            combined = re.match(
                r"^(.{2,191}?(?:有限公司|集团|会社|株式会社|Company|Corp\.?))"
                r"\s*[·•|｜]\s*(.{2,191})$",
                lines[1],
                flags=re.IGNORECASE,
            )
            if combined:
                company = company or combined.group(1).strip()
                position = position or combined.group(2).strip()

        if company is None:
            company = labeled(r"(?:公司|公司名称)")
        if position is None:
            position = labeled(r"(?:职位|职务)")
        if industry is None:
            industry = labeled(r"(?:行业|所属行业)")

        salary_period = (
            "annual"
            if salary_match and "年薪" in salary_match.group(1)
            else "monthly"
        )
        annual_min, annual_max = ResumeParser._normalize_salary(
            salary,
            salary_period,
        )

        return {
            "current_company": company,
            "current_position": position,
            "current_salary": salary,
            "current_annual_salary_min": annual_min,
            "current_annual_salary_max": annual_max,
            "current_industry": industry,
            "current_status": status,
        }

    @staticmethod
    def _personal_profile(
        lines: list[str],
        text: str,
    ) -> dict[str, Any]:
        birth_match = re.search(
            r"((?:19|20)\d{2})\s*[年./\-]\s*(\d{1,2})"
            r"(?:\s*[月./\-]\s*(\d{1,2})\s*日?)?",
            text[:1500],
        )
        birth_date = None
        birth_year = None
        if birth_match and re.search(
            r"出生|生年月日|Birth",
            text[max(0, birth_match.start() - 20):birth_match.start()],
            flags=re.IGNORECASE,
        ):
            birth_year = int(birth_match.group(1))
            month = int(birth_match.group(2))
            day = int(birth_match.group(3) or 1)
            try:
                birth_date = f"{birth_year:04d}-{month:02d}-{day:02d}"
            except ValueError:
                birth_date = None

        def labeled(pattern: str, limit: int = 191) -> str | None:
            match = re.search(
                pattern + rf"\s*[:：]\s*([^\n|｜]{{1,{limit}}})",
                text,
                flags=re.IGNORECASE,
            )
            return match.group(1).strip() if match else None

        marital = labeled(r"(?:婚姻状况|婚姻状态|婚姻|配偶者)")
        if marital is None:
            inline = re.search(r"(?:^|[·•|｜\s])(未婚|已婚|离异)(?:[·•|｜\s]|$)", text[:800])
            marital = inline.group(1) if inline else None
        political = labeled(r"(?:政治面貌|政治状态)")
        if political is None:
            inline = re.search(r"(?:^|[·•|｜\s])(群众|党员|团员|民主党派)(?:[·•|｜\s]|$)", text[:800])
            political = inline.group(1) if inline else None
        height_match = re.search(r"(?:身高\s*[:：]?\s*|[·•|｜\s])(\d{3})\s*cm", text[:1000], re.IGNORECASE)
        height = int(height_match.group(1)) if height_match else None
        if height is not None and not 120 <= height <= 230:
            height = None

        return {
            "birth_date": birth_date,
            "birth_year": birth_year,
            "marital_status": marital,
            "political_status": political,
            "height_cm": height,
            "household_registration": labeled(r"(?:户口|户籍|本籍)"),
            "address": labeled(r"(?:地址|住址|住所)", 255),
            "postal_code": labeled(r"(?:邮编|郵便番号)", 20),
            "platform_resume_id": (
                re.search(r"\bID\s*[:：]?\s*(\d{5,30})", text[:2000], re.IGNORECASE).group(1)
                if re.search(r"\bID\s*[:：]?\s*(\d{5,30})", text[:2000], re.IGNORECASE)
                else None
            ),
        }

    def _job_expectation(self, text: str) -> dict[str, Any]:
        def labeled(pattern: str) -> str | None:
            match = re.search(
                pattern + r"\s*[:：]\s*([^\n]{1,191})",
                text,
                flags=re.IGNORECASE,
            )
            return match.group(1).strip() if match else None

        expected_city_raw = labeled(r"(?:目标地点|期望地点|期望城市|希望勤務地)")
        expected_city = None
        if expected_city_raw:
            expected_city = next(
                (
                    city for city in self.cities
                    if city.casefold() in expected_city_raw.casefold()
                ),
                expected_city_raw[:100],
            )
        expected_salary = labeled(r"(?:期望薪资|期望薪酬|希望年収|希望給与)")
        salary_period = (
            "annual"
            if expected_salary and re.search(r"年薪|年収", expected_salary)
            else "monthly"
        )
        annual_min, annual_max = self._normalize_salary(
            expected_salary,
            salary_period,
        )
        return {
            "expected_city": expected_city,
            "expected_position": labeled(
                r"(?:目标职能|期望职位|期望岗位|希望職種)"
            ),
            "expected_salary": expected_salary,
            "expected_annual_salary_min": annual_min,
            "expected_annual_salary_max": annual_max,
            "expected_industry": labeled(
                r"(?:希望行业|期望行业|希望業界)"
            ),
            "employment_type": labeled(
                r"(?:工作性质|雇用形態|Employment Type)"
            ),
            "availability": labeled(
                r"(?:到岗时间|到職時間|入社可能日|Availability)"
            ),
        }

    @staticmethod
    def _normalize_salary(
        raw: str | None,
        period: str,
    ) -> tuple[float | None, float | None]:
        if not raw:
            return None, None
        primary = re.split(r"[（(]", raw, maxsplit=1)[0]
        numbers = [
            float(value)
            for value in re.findall(r"\d+(?:\.\d+)?", primary.replace(",", ""))
        ]
        if not numbers:
            return None, None
        minimum = numbers[0]
        maximum = numbers[1] if len(numbers) >= 2 else minimum
        if "万" in primary:
            minimum *= 10000
            maximum *= 10000
        if period == "monthly" or re.search(r"元\s*/\s*月|月薪", raw):
            minimum *= 12
            maximum *= 12
        return round(minimum, 2), round(maximum, 2)

    @staticmethod
    def _education_profile(
        lines: list[str],
        text: str,
    ) -> dict[str, str | None]:
        school = None
        major = None
        education_period = None
        education_start_date = None
        education_end_date = None

        labeled_school = re.search(
            r"(?:毕业院校|毕业学校|学校|院校|最終学歴)\s*[:：]\s*"
            r"([^\n|｜]{2,80})",
            text,
            flags=re.IGNORECASE,
        )
        if labeled_school:
            school = labeled_school.group(1).strip()

        education_line = next(
            (
                line for line in lines
                if re.search(
                    r"大学|学院|学校|University|College",
                    line,
                    flags=re.IGNORECASE,
                )
                and re.search(
                    r"(?:19|20)\d{2}[./\-年]",
                    line,
                )
            ),
            None,
        )
        if education_line:
            if school is None:
                school_match = re.search(
                    r"([\u4e00-\u9fffA-Za-z（）()·&.\s]{2,80}?"
                    r"(?:大学|学院|学校|University|College))",
                    education_line,
                    flags=re.IGNORECASE,
                )
                if school_match:
                    school = school_match.group(1).strip()
            period_match = re.search(
                r"((?:19|20)\d{2}[./\-年]\d{1,2}"
                r"\s*(?:~|～|\-|—|–|至|到)\s*"
                r"(?:(?:19|20)\d{2}[./\-年]\d{1,2}|至今|現在|Present))",
                education_line,
                flags=re.IGNORECASE,
            )
            if period_match:
                education_period = period_match.group(1).strip()
                date_parts = re.findall(
                    r"((?:19|20)\d{2})[./\-年](\d{1,2})",
                    education_period,
                )
                if date_parts:
                    education_start_date = (
                        f"{date_parts[0][0]}-{int(date_parts[0][1]):02d}"
                    )
                if len(date_parts) >= 2:
                    education_end_date = (
                        f"{date_parts[1][0]}-{int(date_parts[1][1]):02d}"
                    )
                elif re.search(r"至今|現在|Present", education_period, re.IGNORECASE):
                    education_end_date = "至今"
            if school:
                remainder = education_line.split(school, 1)[-1]
                remainder = re.sub(
                    r"(?:19|20)\d{2}[./\-年].*$",
                    "",
                    remainder,
                ).strip(" /｜|,，")
                remainder = re.sub(
                    r"[/｜|]?(?:博士|硕士|修士|本科|学士|大专|短大|"
                    r"中专|高中|Bachelor|Master|PhD).*$",
                    "",
                    remainder,
                    flags=re.IGNORECASE,
                ).strip(" /｜|,，")
                if 1 < len(remainder) <= 100:
                    major = remainder

        labeled_major = re.search(
            r"(?:专业|専攻|Major)\s*[:：]\s*([^\n|｜]{1,100}?)(?="
            r"\s+(?:学历|学位|学校|院校|毕业院校|教育程度|"
            r"Education|Degree)\s*[:：]|$)",
            text,
            flags=re.IGNORECASE,
        )
        if labeled_major:
            major = labeled_major.group(1).strip()

        return {
            "school": school,
            "major": major,
            "education_period": education_period,
            "education_start_date": education_start_date,
            "education_end_date": education_end_date,
        }

    @staticmethod
    def _language_ability(lines: list[str], text: str) -> str | None:
        labeled = re.search(
            r"(?:语言能力|語学力|Language\s+Skills?)\s*[:：]\s*([^\n]{2,200})",
            text,
            flags=re.IGNORECASE,
        )
        if labeled:
            return labeled.group(1).strip()
        headings = {"语言能力", "語学力", "Language Skills", "Languages"}
        stop_pattern = re.compile(
            r"附加信息|其他信息|技能|证书|资格|工作经历|教育经历|"
            r"项目经历|Additional|Skills?|Certificates?",
            flags=re.IGNORECASE,
        )
        for index, line in enumerate(lines):
            if line.strip(" :：").casefold() not in {
                heading.casefold() for heading in headings
            }:
                continue
            values: list[str] = []
            for candidate in lines[index + 1:index + 5]:
                if stop_pattern.search(candidate):
                    break
                values.append(candidate)
            value = "；".join(values).strip()
            return value or None
        return None

    @staticmethod
    def _section(lines: list[str], starts: tuple[str, ...], ends: tuple[str, ...]) -> str | None:
        capturing = False
        result: list[str] = []
        for line in lines:
            normalized = re.sub(r"[\s:：\-—_]+", "", line).casefold()
            if not capturing and any(normalized.startswith(heading.casefold()) for heading in starts):
                capturing = True
                # “工作经验：2013/10-2014/07 某公司 某职位”中，标题
                # 与第一段经历位于同一行，不能把冒号后的正文一起丢掉。
                # EN: In "工作经验：2013/10-2014/07 某公司 某职位" (work experience: dates, company, position), the heading
                #     and the first experience are on the same line; the text after the colon must not be thrown away with it.
                # JA: 「工作经验：2013/10-2014/07 某公司 某职位」（職歴：期間 会社 職位）では、見出しと
                #     最初の経歴が同じ行にあるため、コロンの後の本文まで一緒に捨ててはならない。
                for heading in starts:
                    inline = re.match(
                        rf"^\s*{re.escape(heading)}\s*[:：]\s*(.+)$",
                        line,
                        flags=re.IGNORECASE,
                    )
                    if inline and inline.group(1).strip():
                        result.append(inline.group(1).strip())
                        break
                continue
            if capturing and any(normalized.startswith(heading.casefold()) for heading in ends):
                break
            if capturing:
                result.append(line)
        value = "\n".join(result).strip()
        return value or None

    @staticmethod
    def _find_phone(text: str) -> str | None:
        patterns = (
            r"(?<!\d)(?:\+?86[-\s]?)?(1[3-9]\d{9})(?!\d)",
            r"(?<!\d)(?:(?:\+81[-\s]?)?0?[789]0[-\s]?\d{4}[-\s]?\d{4})(?!\d)",
            r"(?<!\d)\+\d{1,3}[-\s]?(?:\d[-\s]?){7,14}(?!\d)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip()
        return None

    @staticmethod
    def _detect_language(text: str) -> str:
        japanese = len(re.findall(r"[\u3040-\u30ff]", text))
        han = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin = len(re.findall(r"[A-Za-z]", text))
        german_signals = len(
            re.findall(
                r"\b(?:Lebenslauf|Berufserfahrung|Beruflicher\s+Werdegang|"
                r"Ausbildung|Studium|Kenntnisse|Fähigkeiten|Persönliche\s+Daten|"
                r"Geburtsdatum|Staatsangehörigkeit|Tätigkeiten|Arbeitgeber)\b",
                text,
                flags=re.IGNORECASE,
            )
        )

        if japanese >= 4 or re.search(r"氏名|職務経歴|学歴|株式会社", text):
            return "mixed" if latin >= 80 else "ja"
        if latin >= 80 and han >= 20:
            return "mixed"
        if latin >= 40 and german_signals >= 2:
            return "de"
        if latin >= 40 and han < 20:
            return "en"
        return "zh"
