from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    document_type: str
    confidence: str
    resume_score: int
    jd_score: int
    contract_score: int
    client_score: int
    recommendation_score: int
    offer_score: int
    interview_score: int
    training_score: int
    compensation_score: int
    financial_score: int
    medical_score: int
    reason: str
    resume_kind: str | None = None


class DocumentClassifier:
    resume_patterns = (
        (
            r"个人简历|求职简历|候选人简历报告|候选人履历报告|候选人档案|简历|"
            r"履歴書|職務経歴書|候補者推薦書|面接前送付情報|候補者情報|"
            r"\bresume\b|curriculum\s+vitae|\bcv\b|candidate\s+profile|personal\s+data|"
            r"lebenslauf|berufserfahrung|ausbildung|personaldaten|bewerbung|"
            r"expérience\s+professionnelle|profil\s+du\s+candidat|"
            r"currículum\s+vitae|experiencia\s+laboral|perfil\s+del\s+candidato|"
            r"currículo|experiência\s+profissional|perfil\s+do\s+candidato",
            4,
        ),
        (
            r"工作经历|工作经验|职业经历|職務経歴|職歴|職務内容|プロジェクト|"
            r"work(?:ing)?\s+experience|professional\s+experience|employment\s+history|career\s+history|"
            r"berufserfahrung|beruflicher\s+werdegang|berufstätigkeit|arbeitserfahrung|"
            r"expérience\s+professionnelle|parcours\s+professionnel|"
            r"experiencia\s+laboral|experiencia\s+profesional|historial\s+laboral|"
            r"experiência\s+profissional|histórico\s+profissional",
            2,
        ),
        (
            r"教育经历|教育背景|学历信息|学歴|最終学歴|\beducation\b|educational\s+background|"
            r"ausbildung|schulbildung|hochschulbildung|studium|"
            r"formation|parcours\s+académique|études|"
            r"educación|formación\s+académica|estudios|"
            r"educação|formação\s+acadêmica|escolaridade",
            2,
        ),
        (r"本科|学士|硕士|修士|博士|\bbachelor\b|\bmaster\b|\bphd\b|diplom|licence|master|grado|licenciatura", 1),
        (
            r"姓名\s*[:：]|氏名\s*[:：]|名前\s*[:：]|full\s+name\s*:|candidate(?:'s)?\s+name\s*:|"
            r"kontaktdaten|geburtsdatum|coordonnées|date\s+de\s+naissance|contacto|datos\s+personales",
            2,
        ),
        (r"自我评价|自己紹介|professional\s+summary|career\s+summary|über\s+mich|profil|resumen|sobre\s+mim", 1),
        (r"项目经历|プロジェクト|project\s+experience|projekte|projets|proyectos", 1),
        (r"技能|スキル|\bskills?\b|kenntnisse|compétences|habilidades", 1),
    )
    jd_patterns = (
        (
            r"职位描述|岗位描述|职位名称|职位要求|工作内容|招聘信息|"
            r"job\s+description|職務内容|募集要項|求人票|stellenbeschreibung|description\s+du\s+poste",
            4,
        ),
        (r"岗位职责|工作职责|responsibilit(?:y|ies)|業務内容|aufgaben|responsabilités|responsabilidades", 2),
        (r"任职要求|任职资格|応募資格|必須条件|requirements?|qualifications?|anforderungen|exigences|requisitos", 3),
        (r"招聘人数|招聘岗位|薪资待遇|职位薪资|勤務地|雇用形態|standort|lieu\s+de\s+travail", 2),
        (r"我们正在寻找|we\s+are\s+(?:looking|hiring)|人材を募集|wir\s+suchen|nous\s+recherchons", 2),
    )
    contract_patterns = (
        (r"合同|协议书|契約書|\bcontract\b|\bagreement\b|vertrag|contrat|contrato", 4),
        (r"甲方|乙方|party\s+a|party\s+b|当事者|vertragsparteien|parties", 2),
        (r"违约责任|争议解决|terms\s+and\s+conditions|breach|準拠法|gerichtsstand", 2),
        (r"签字|盖章|署名|捺印|signature|unterschrift|firma", 1),
    )
    client_patterns = (
        (
            r"客户信息|客户资料|客户档案|顧客情報|取引先情報|"
            r"client\s+(?:information|profile)|customer\s+information|kundeninformation|informations\s+client",
            4,
        ),
        (
            r"客户名称|客户编号|联系人|担当者|顧客名|"
            r"contact\s+person|account\s+(?:name|details)|ansprechpartner",
            2,
        ),
        (r"公司简介|企业信息|企业概要|company\s+profile|business\s+overview|unternehmensprofil", 2),
        (r"业务范围|合作需求|客户需求|预算范围|事業内容|取引条件", 1),
    )
    recommendation_patterns = (
        (
            r"候选人(?:推荐|评估)报告|人才推荐报告|推薦報告|候補者推薦書|面接前送付情報|候補者評価|"
            r"candidate\s+(?:recommendation|assessment)\s+report|empfehlungsbericht|rapport\s+de\s+recommandation|"
            r"informe\s+de\s+recomendación|relatório\s+de\s+recomendação",
            6,
        ),
        (
            r"推荐理由|推荐意见|顾问评价|猎头评语|推薦理由|"
            r"コンサルタントコメント|recommendation\s+reason|consultant\s+comments?|beurteilung|remarques",
            3,
        ),
        (r"匹配度|推荐职位|推荐顾问|推荐日期|推薦ポジション|紹介会社", 2),
    )
    offer_patterns = (
        (
            r"录用通知书|聘用通知书|入职通知书|採用通知書|内定通知書|"
            r"採用条件通知書|employment\s+offer|job\s+offer|offer\s+letter|arbeitsangebot|offre\s+d'emploi",
            6,
        ),
        (r"报到日期|入职日期|入社日|雇用開始日|start\s+date|eintrittsdatum", 2),
        (r"录用职位|聘用职位|採用職種|offered\s+position", 2),
        (r"请签署确认|accept\s+this\s+offer|承諾書", 2),
    )
    interview_patterns = (
        (
            r"面试(?:记录|评价|评估|反馈|报告)|面談(?:記録|評価)|面接(?:記録|評価)|"
            r"interview\s+(?:notes?|assessment|evaluation|feedback|report)|vorstellungsgespräch",
            6,
        ),
        (r"面试官|面接官|interviewer|综合评价|総合評価", 2),
        (r"建议录用|不予录用|面试结论|採用判定|hiring\s+recommendation", 2),
    )
    training_patterns = (
        (
            r"操作手册|使用说明书|工作流程|业务流程|培训资料|培训教材|"
            r"業務マニュアル|取扱説明書|training\s+material|user\s+manual|schulungsunterlagen",
            6,
        ),
        (r"操作步骤|注意事项|研修資料|procedure|instructions?", 2),
    )
    compensation_patterns = (
        (
            r"工资表|薪资表|薪酬方案|薪酬报告|給与表|賃金台帳|"
            r"salary\s+sheet|payroll|compensation\s+(?:plan|report)|gehaltsabrechnung",
            6,
        ),
        (r"基本工资|基本給|绩效奖金|賞与|年収一覧", 2),
    )
    financial_patterns = (
        (
            r"报价单|发票|请求书|請求書|見積書|invoice|quotation|purchase\s+order|rechnung|facture",
            6,
        ),
        (r"税率|含税金额|消費税|付款条件|支払条件", 2),
    )
    medical_patterns = (
        (
            r"体检通知(?:单|书)?|体检报告|健康诊断|健康診断|"
            r"medical\s+examination|medical\s+check|health\s+check",
            6,
        ),
        (r"体检项目|检查项目|検査項目|指定医院|指定病院", 2),
    )

    def classify(self, text: str, filename: str = "") -> Classification:
        filename = re.split(r"[\\/]", filename)[-1]
        resume = self._score(text, self.resume_patterns)
        jd = self._score(text, self.jd_patterns)
        contract = self._score(text, self.contract_patterns)
        client = self._score(text, self.client_patterns)
        recommendation = self._score(text, self.recommendation_patterns)
        offer = self._score(text, self.offer_patterns)
        interview = self._score(text, self.interview_patterns)
        training = self._score(text, self.training_patterns)
        compensation = self._score(text, self.compensation_patterns)
        financial = self._score(text, self.financial_patterns)
        medical = self._score(text, self.medical_patterns)
        candidate_resume_report = re.search(
            r"候选人(?:简历|履历)报告|候选人档案|"
            r"履歴書|職務経歴書|候補者推薦書|面接前送付情報|候補者情報|"
            r"candidate\s+(?:resume\s+report|profile)|"
            r"headhunter[’']?s?\s+evaluation|lebenslauf|curriculum\s+vitae",
            text,
            flags=re.IGNORECASE,
        ) is not None
        has_work_structure = re.search(
            r"工作经历|工作经验|职业经历|職務経歴|職歴|職務内容|プロジェクト|经验\s*[:：]|"
            r"work(?:ing)?\s+experience|professional\s+experience|employment\s+history|career\s+history|"
            r"berufserfahrung|beruflicher\s+werdegang|berufstätigkeit|arbeitserfahrung|"
            r"expérience\s+professionnelle|parcours\s+professionnel|"
            r"experiencia\s+laboral|experiencia\s+profesional|historial\s+laboral|"
            r"experiência\s+profissional|histórico\s+profissional",
            text,
            flags=re.IGNORECASE,
        ) is not None
        has_education_structure = re.search(
            r"教育经历|教育背景|学历信息|学歴|最終学歴|教育\s*[:：]|\beducation\b|educational\s+background|"
            r"ausbildung|schulbildung|hochschulbildung|studium|"
            r"formation|parcours\s+académique|études|"
            r"educación|formación\s+académica|estudios|"
            r"educação|formação\s+acadêmica|escolaridade",
            text,
            flags=re.IGNORECASE,
        ) is not None
        has_person_structure = re.search(
            r"姓\s*名\s*[:：]?|氏\s*名\s*[:：]?|名\s*前\s*[:：]?|性\s*别\s*[:：]?|"
            r"full\s+name\s*:|candidate(?:'s)?\s+name\s*:|kontaktdaten|geburtsdatum|coordonnées|"
            r"date\s+de\s+naissance|contacto|datos\s+personales|"
            r"毕\s*业\s*院\s*校|毕业于|学\s*历\s*[:：]?|生\s*年\s*月\s*日|出\s*生\s*年\s*月|"
            r"住\s*址|住\s*所|\bTEL\b|\bFAX\b|手机|联系电话|电子邮箱|"
            r"(?:男|女)\s*\d{2}\s*歳|(?:男|女)\s*\d{2}\s*岁|未婚|既婚|已婚|"
            r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}|"
            r"(?<!\d)(?:\+?\d{1,3}[-\s]?)?(?:\d[-\s]?){8,13}(?!\d)",
            text,
            flags=re.IGNORECASE,
        ) is not None

        has_timeline_structure = re.search(
            r"\d{4}\s*年\s*\d{1,2}\s*月|"
            r"\d{4}[./\-](?:0?[1-9]|1[0-2])\s*[-~～—–至到]\s*(?:\d{4}[./\-]?(?:0?[1-9]|1[0-2])?|至今|現在|present)|"
            r"(?:0?[1-9]|1[0-2])[./\-]\d{4}\s*[-~～—–至到]\s*(?:0?[1-9]|1[0-2])[./\-]\d{4}",
            text,
            flags=re.IGNORECASE,
        ) is not None
        structured_resume = (
            has_work_structure
            and has_education_structure
            and has_person_structure
        )

        candidate_profile_in_report = (
            (has_person_structure or resume >= 1)
            and (has_work_structure or has_education_structure or recommendation >= 1)
        )
        candidate_resume_report = (
            candidate_resume_report or candidate_profile_in_report
        )

        recommendation_filename = re.search(
            r"推荐报告|推薦報告|候选人评估报告|候補者推薦書|面接前送付情報|empfehlungsbericht|rapport\s+de\s+recommandation",
            filename,
            flags=re.IGNORECASE,
        ) is not None
        if recommendation_filename:
            recommendation += 8
        offer_filename = re.search(
            r"(?:^|[\s_\-])offer(?:[\s_\-.]|$)|录用通知|聘用通知|"
            r"採用通知|内定通知|arbeitsangebot",
            filename,
            flags=re.IGNORECASE,
        ) is not None
        if offer_filename:
            offer += 8
        jd_filename = re.search(
            r"JD模板|(?:^|[\s_\-])JD(?:[\s_\-.]|$)|职位信息|岗位说明|"
            r"招聘信息|招聘需求|委托招聘|岗位委托|募集要項|求人票|"
            r"人材紹介依頼書|(?:^|[\s_\-])职位(?:[\s_\-.]|$)|stellenbeschreibung",
            filename,
            flags=re.IGNORECASE,
        ) is not None
        if jd_filename:
            jd += 8
        resume_filename = re.search(
            r"个人简历|中文简历|日文简历|英文简历|智联简历|猎聘简历|简历|履历|履歴|経歴|"
            r"求职申请表|求職申請表|求职|求職|履歴書|職務経歴書|(?:^|[\s_\-])resume(?:[\s_\-.]|$)|"
            r"(?:^|[\s_\-])CV(?:[\s_\-.]|$)|lebenslauf|currículum|currículo|"
            r"(?:\(|（)[^)]*(?:担当|工程师|经理|专员|主管|助理|翻译|会計|営業|開発|中文|日文|日本語|English)[^)]*(?:\)|）)|"
            r"^[^\s_\\/-]{2,4}[\s_\-].*$",
            filename,
            flags=re.IGNORECASE,
        ) is not None
        if resume_filename:
            resume += 8
        if re.search(
            r"客户信息|客户资料|客户档案|联系人|通讯录|公司介绍|会社案内",
            filename,
            flags=re.IGNORECASE,
        ):
            client += 6
        if re.search(r"合同|协议|契約", filename, flags=re.IGNORECASE):
            contract += 6
        if re.search(r"面试|面談|面接.*(?:评价|评估|記録|評価)", filename, flags=re.IGNORECASE):
            interview += 8
        if re.search(r"说明|流程|手册|培训|训练|マニュアル|研修", filename, flags=re.IGNORECASE):
            training += 6
        if re.search(r"工资|薪资|薪酬|給与|年収", filename, flags=re.IGNORECASE):
            compensation += 6
        if re.search(r"发票|报价|请求书|請求書|見積書|invoice", filename, flags=re.IGNORECASE):
            financial += 8
        medical_filename = re.search(
            r"体检|健康诊断|健康診断|medical.?check",
            filename,
            flags=re.IGNORECASE,
        ) is not None
        if medical_filename:
            medical += 8

        if re.search(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text, re.IGNORECASE):
            resume += 1
        if re.search(r"(?<!\d)(?:\+?\d{1,3}[-\s]?)?(?:\d[-\s]?){8,13}(?!\d)", text):
            resume += 1
        if re.search(r"(?:19|20)\d{2}\s*[-–—~至到年/]\s*(?:(?:19|20)\d{2}|至今|現在|present)", text, re.IGNORECASE):
            resume += 1

        if offer_filename or offer >= 8:
            return Classification(
                "offer", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "录用/聘用通知特征明显"
            )
        if (
            (recommendation_filename or recommendation >= 3)
            and (has_person_structure or has_work_structure or has_education_structure or resume >= 1)
        ):
            return Classification(
                "resume", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical,
                "包含候选人信息的推荐/评估报告，按简历入库",
                resume_kind="candidate_resume_report",
            )
        if (
            resume_filename
            or structured_resume
            or candidate_profile_in_report
            or (has_person_structure and (has_work_structure or has_education_structure or resume >= 1))
            or (has_timeline_structure and (has_person_structure or has_work_structure or has_education_structure or resume >= 1))
            or (resume >= 1 and (has_person_structure or has_timeline_structure or re.search(r"简历|履历|求职|氏名|姓名", text)))
            or (resume >= 2 and not jd_filename)
        ):
            return Classification(
                "resume", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "包含候选人履历或个人档案特征，按简历入库"
            )
        if recommendation_filename or recommendation >= 8:
            return Classification(
                "recommendation_report", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "不含个人信息的纯候选人推荐表单/模板"
            )
        if medical_filename:
            return Classification(
                "medical_document", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "体检通知/报告特征明显"
            )
        if jd_filename:
            return Classification(
                "job_description", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "文件名明确标注为职位JD"
            )
        if medical >= 8 and medical >= max(resume, jd) + 2:
            return Classification(
                "medical_document", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "体检通知/报告特征明显"
            )
        if interview >= 6 and interview >= max(resume, jd) + 2:
            return Classification(
                "interview_assessment", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "面试记录/评估特征明显"
            )
        if compensation >= 6 and compensation >= max(resume, jd) + 2:
            return Classification(
                "compensation_document", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "工资/薪酬资料特征明显"
            )
        if financial >= 6 and financial >= max(resume, jd, client) + 2:
            return Classification(
                "financial_document", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "报价/发票资料特征明显"
            )
        if training >= 6 and training >= max(resume, jd) + 2:
            return Classification(
                "training_material", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "说明/流程/培训资料特征明显"
            )
        if contract >= 5 and contract >= resume + 2 and contract >= max(jd, client):
            return Classification(
                "contract", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "合同/协议特征明显"
            )
        if client >= 6 and client >= resume + 2 and client >= contract:
            return Classification(
                "client_information", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "客户资料特征明显"
            )
        if jd >= 5 and jd >= resume + 2 and jd > contract:
            return Classification(
                "job_description", "high", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "职位JD特征明显"
            )
        if resume >= 5 and resume >= max(jd, contract, client):
            confidence = "high" if resume >= 8 else "medium"
            return Classification(
                "resume", confidence, resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "个人简历特征充分"
            )

        if resume > 0:
            return Classification(
                "ambiguous_resume", "low", resume, jd, contract, client,
                recommendation, offer, interview, training, compensation,
                financial, medical, "有简历特征但不足以安全入库，需要人工检查"
            )
        return Classification(
            "other_document",
            "low",
            resume,
            jd,
            contract,
            client,
            recommendation,
            offer,
            interview,
            training,
            compensation,
            financial,
            medical,
            "可读取，但未检测到简历或已知业务资料特征",
        )

    @staticmethod
    def _score(text: str, patterns: tuple[tuple[str, int], ...]) -> int:
        return sum(
            weight
            for pattern, weight in patterns
            if re.search(pattern, text, flags=re.IGNORECASE)
        )
