import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from llm_client import get_client, get_model, get_provider_sequence
from schemas import AnalyzeCvRequest, AnalyzeCvResponseData

PROMPT_VERSION = "cv-analysis-v3-vi-output"
MAX_INPUT_CHARS = max(int(os.getenv("AI_MAX_INPUT_CHARS", "12000")), 2000)
LOGGER = logging.getLogger("ai_service.resume_analyzer")


PROMPT_TEMPLATE = """
You are an expert AI resume analysis engine for a multi-industry recruitment platform.
Return STRICT JSON only. Do not return markdown. Do not add explanation outside JSON.
Do not invent facts that are not supported by the resume text.
If information is missing or uncertain, keep the output conservative and record it in `confidenceFlags`.

Mandatory language rules:
- Keep all JSON keys exactly in English as defined by the schema below.
- All user-facing string values MUST be written in natural Vietnamese with proper Vietnamese accents.
- Do not return English sentences in `summary`, `strengths`, `weaknesses`, `improvementSuggestions`, `education.description`, `experience.description`, `projects.description`, `atsNotes`, or `evidence`.
- Technical skill names may stay in their original form, for example React, Vue.js, MySQL, C#, C++, SQL Server.

You are given:
1. Resume raw text
2. Active career categories from the system
3. Relevant system skills pre-filtered by the backend, including aliases, parent skill group, and parent career category when available

Your goals:
1. Infer the candidate's professional profile
2. Match resume skills against the provided system skills
3. Suggest the most relevant career category from the provided category list
4. Evaluate resume quality, readability, and ATS usefulness
5. Provide concrete improvement suggestions in Vietnamese
6. Generate keywords and related job titles for later backend matching

Scoring rules for `resumeQualityScore`:
- roleClarity: 15%
- skillCoverage: 20%
- experienceQuality: 20%
- impactEvidence: 15%
- educationRelevance: 10%
- atsReadiness: 10%
- presentationClarity: 10%

Score scale rules:
- `resumeQualityScore`, every `scoreBreakdown` field, and `careerCategorySuggestion.confidence` MUST use a 0-100 numeric scale.
- Never use a 0-1 scale for these score fields. Use 80, not 0.8. Use 62, not 0.62.
- Only skill confidence fields use a 0-1 scale: `matchedSkills[].confidence` and `otherDetectedSkills[].confidence`.

Important constraints:
- Do not create job IDs or database IDs
- Do not assume the resume belongs to Information Technology; infer from the resume and the provided category/skill context
- `careerCategorySuggestion` must come from the provided category list or be null
- If a child skill belongs to a parent skill group, use the parent group and career category to support `careerCategorySuggestion`
- `matchedSkills` should only contain skills that can be matched to the provided system skills
- Skills detected in the resume but not confidently matched to the system catalog must go to `otherDetectedSkills`
- Split and normalize compact skill expressions such as "HTML/CSS/JS", "HTML, CSS, JS", "C#", "C++", "Vue.js", "React.js", "SQL Server" when there is evidence in the resume
- `resumeQualityScore` is resume quality only, not a job matching score
- Keep the response concise: at most 30 matchedSkills, 20 otherDetectedSkills, 5 suggestions, 5 strengths, 5 weaknesses, 5 experience items, and 5 projects

Return this exact JSON shape:
{{
  "summary": "Vietnamese string",
  "resumeQualityScore": 0,
  "scoreBreakdown": {
    "roleClarity": 0,
    "skillCoverage": 0,
    "experienceQuality": 0,
    "impactEvidence": 0,
    "educationRelevance": 0,
    "atsReadiness": 0,
    "presentationClarity": 0
  },
  "primaryRole": "string",
  "seniorityLevel": "intern | fresher | junior | middle | senior | lead | manager | unknown",
  "careerCategorySuggestion": {
    "name": "string",
    "slug": "string",
    "confidence": 0
  },
  "matchedSkills": [
    {
      "name": "string",
      "systemSkillSlug": "string",
      "normalizedName": "string",
      "confidence": 0,
      "level": "beginner | intermediate | advanced | expert | unknown",
      "evidence": "Vietnamese string"
    }
  ],
  "otherDetectedSkills": [
    {
      "name": "string",
      "normalizedName": "string",
      "confidence": 0,
      "evidence": "Vietnamese string"
    }
  ],
  "keywords": ["string"],
  "relatedJobTitles": ["string"],
  "strengths": ["Vietnamese string"],
  "weaknesses": ["Vietnamese string"],
  "improvementSuggestions": ["Vietnamese string"],
  "education": [
    {
      "school": "string",
      "degree": "string",
      "fieldOfStudy": "string",
      "startDate": "string",
      "endDate": "string",
      "description": "Vietnamese string"
    }
  ],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "startDate": "string",
      "endDate": "string",
      "durationMonths": 0,
      "description": "Vietnamese string",
      "achievements": ["Vietnamese string"]
    }
  ],
  "projects": [
    {
      "name": "string",
      "role": "string",
      "description": "Vietnamese string",
      "technologies": ["string"],
      "outcomes": ["Vietnamese string"]
    }
  ],
  "atsNotes": ["Vietnamese string"],
  "confidenceFlags": ["string"]
}

System career categories:
__CAREER_CATEGORIES_JSON__

System skills:
__SKILLS_JSON__

Resume text:
__RAW_TEXT__
""".strip()


def analyze_resume_text(request: AnalyzeCvRequest) -> AnalyzeCvResponseData:
    errors: list[str] = []
    for provider_name in get_provider_sequence(request.requestedProvider):
        model = get_model(provider_name)
        try:
            client, provider = get_client(provider_name)
            LOGGER.info("Attempting CV analysis with provider=%s model=%s", provider, model)
            content = _request_analysis(client, provider, model, request)
            parsed = _parse_json_content(content)
            response = AnalyzeCvResponseData.model_validate(
                {
                    **parsed,
                    "provider": provider,
                    "model": model,
                    "promptVersion": PROMPT_VERSION,
                    "analyzedAt": datetime.now(timezone.utc),
                }
            )
            _normalize_response_scores(response)
            LOGGER.info(
                "CV analysis succeeded with provider=%s model=%s cvId=%s",
                provider,
                model,
                request.cvId,
            )
            return response
        except Exception as exc:
            LOGGER.warning(
                "CV analysis failed with provider=%s model=%s cvId=%s error=%s",
                provider_name,
                model,
                request.cvId,
                exc,
            )
            errors.append(f"{provider_name}: {exc}")
            continue

    fallback = _rule_based_fallback(request)
    if errors:
        fallback.confidenceFlags.append("provider_fallback_exhausted")
        LOGGER.warning(
            "All AI providers failed for cvId=%s. Falling back to rule-based analysis. errors=%s",
            request.cvId,
            "; ".join(errors),
        )
    return fallback


def _request_analysis(
    client: Any, provider: str, model: str, request: AnalyzeCvRequest
) -> str:
    prompt = (
        PROMPT_TEMPLATE.replace("__RAW_TEXT__", request.rawText[:MAX_INPUT_CHARS])
        .replace(
            "__CAREER_CATEGORIES_JSON__",
            json.dumps(
                [item.model_dump() for item in request.availableCareerCategories],
                ensure_ascii=False,
            ),
        )
        .replace(
            "__SKILLS_JSON__",
            json.dumps(
                [item.model_dump() for item in request.availableSkills],
                ensure_ascii=False,
            ),
        )
    )
    timeout_ms = max(int(os.getenv("AI_ANALYZE_TIMEOUT_MS", "60000")), 1000)
    request_payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2600,
        "timeout": timeout_ms / 1000,
    }
    if _supports_json_response_format(provider):
        request_payload["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**request_payload)
    return response.choices[0].message.content or "{}"


def _parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model did not return valid JSON")

    return json.loads(cleaned[start : end + 1])


def _rule_based_fallback(request: AnalyzeCvRequest) -> AnalyzeCvResponseData:
    text = request.rawText[:MAX_INPUT_CHARS]
    text_lower = text.lower()
    matched_skills = []
    other_skills = []
    for skill in request.availableSkills[:300]:
        aliases = [skill.name, skill.slug, *(skill.aliases or [])]
        if any(alias.lower() in text_lower for alias in aliases if alias):
            matched_skills.append(
                {
                    "name": skill.name,
                    "systemSkillSlug": skill.slug,
                    "normalizedName": skill.slug,
                    "confidence": 0.7,
                    "level": "unknown",
                    "evidence": f"Phát hiện từ khóa liên quan đến {skill.name} trong CV.",
                }
            )

    if not matched_skills:
        for token in _extract_keywords(text)[:8]:
            other_skills.append(
                {
                    "name": token,
                    "normalizedName": token.lower(),
                    "confidence": 0.4,
                    "evidence": "Phát hiện bằng cơ chế trích xuất từ khóa dự phòng.",
                }
            )

    category = request.availableCareerCategories[0] if request.availableCareerCategories else None
    score_breakdown = {
        "roleClarity": 60,
        "skillCoverage": 65 if matched_skills else 40,
        "experienceQuality": 55,
        "impactEvidence": 45,
        "educationRelevance": 50,
        "atsReadiness": 55,
        "presentationClarity": 60,
    }
    weighted_score = (
        score_breakdown["roleClarity"] * 0.15
        + score_breakdown["skillCoverage"] * 0.2
        + score_breakdown["experienceQuality"] * 0.2
        + score_breakdown["impactEvidence"] * 0.15
        + score_breakdown["educationRelevance"] * 0.1
        + score_breakdown["atsReadiness"] * 0.1
        + score_breakdown["presentationClarity"] * 0.1
    )

    return AnalyzeCvResponseData.model_validate(
        {
            "summary": text[:400] or "Chưa có đủ nội dung CV để tóm tắt.",
            "resumeQualityScore": _clamp_score(weighted_score),
            "scoreBreakdown": score_breakdown,
            "primaryRole": _infer_primary_role(text),
            "seniorityLevel": "unknown",
            "careerCategorySuggestion": (
                {
                    "name": category.name,
                    "slug": category.slug,
                    "confidence": 40,
                }
                if category
                else None
            ),
            "matchedSkills": matched_skills,
            "otherDetectedSkills": other_skills,
            "keywords": _extract_keywords(text)[:12],
            "relatedJobTitles": [_infer_primary_role(text)],
            "strengths": ["CV có nội dung để hệ thống tiếp tục phân tích và so khớp."],
            "weaknesses": ["Kết quả đang dùng cơ chế dự phòng nên độ chi tiết thấp hơn AI chính."],
            "improvementSuggestions": [
                "Bổ sung số liệu hoặc kết quả cụ thể cho kinh nghiệm và dự án.",
                "Làm rõ vai trò chính, cấp độ kinh nghiệm và mục tiêu nghề nghiệp.",
                "Bổ sung thêm kỹ năng quan trọng theo vị trí muốn ứng tuyển.",
            ],
            "education": [],
            "experience": [],
            "projects": [],
            "atsNotes": [
                "Hệ thống đã dùng cơ chế phân tích dự phòng, nên cần kiểm tra lại kết quả.",
            ],
            "confidenceFlags": ["rule_based_fallback_used"],
            "provider": "rule-based",
            "model": "rule-based",
            "promptVersion": PROMPT_VERSION,
            "analyzedAt": datetime.now(timezone.utc),
        }
    )


def _extract_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{2,}", text)
    unique_tokens: list[str] = []
    seen = set()
    for token in tokens:
        normalized = token.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_tokens.append(token)
    return unique_tokens


def _infer_primary_role(text: str) -> str:
    lowered = text.lower()
    role_hints = [
        ("backend developer", "Lập trình viên Backend"),
        ("frontend developer", "Lập trình viên Frontend"),
        ("full stack developer", "Lập trình viên Fullstack"),
        ("devops engineer", "Kỹ sư DevOps"),
        ("data analyst", "Chuyên viên phân tích dữ liệu"),
        ("product designer", "Thiết kế sản phẩm"),
        ("ui ux designer", "Thiết kế UI/UX"),
        ("project manager", "Quản lý dự án"),
    ]
    for keyword, label in role_hints:
        if keyword in lowered:
            return label
    return "Ứng viên chuyên môn"


def _normalize_response_scores(response: AnalyzeCvResponseData) -> None:
    response.resumeQualityScore = _clamp_score(response.resumeQualityScore)
    response.scoreBreakdown.roleClarity = _clamp_score(response.scoreBreakdown.roleClarity)
    response.scoreBreakdown.skillCoverage = _clamp_score(response.scoreBreakdown.skillCoverage)
    response.scoreBreakdown.experienceQuality = _clamp_score(
        response.scoreBreakdown.experienceQuality
    )
    response.scoreBreakdown.impactEvidence = _clamp_score(
        response.scoreBreakdown.impactEvidence
    )
    response.scoreBreakdown.educationRelevance = _clamp_score(
        response.scoreBreakdown.educationRelevance
    )
    response.scoreBreakdown.atsReadiness = _clamp_score(response.scoreBreakdown.atsReadiness)
    response.scoreBreakdown.presentationClarity = _clamp_score(
        response.scoreBreakdown.presentationClarity
    )
    if response.careerCategorySuggestion:
        response.careerCategorySuggestion.confidence = _clamp_score(
            response.careerCategorySuggestion.confidence
        )


def _clamp_score(value: float) -> float:
    score = float(value)
    if 0 < score <= 1:
        score *= 100
    return max(0, min(100, round(score, 2)))


def _supports_json_response_format(provider: str) -> bool:
    return provider in {"groq", "gemini"}
