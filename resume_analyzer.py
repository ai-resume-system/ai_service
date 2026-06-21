import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from llm_client import get_client, get_model, get_provider_sequence
from schemas import AnalyzeCvRequest, AnalyzeCvResponseData

PROMPT_VERSION = "cv-analysis-v2"
MAX_INPUT_CHARS = max(int(os.getenv("AI_MAX_INPUT_CHARS", "12000")), 2000)
LOGGER = logging.getLogger("ai_service.resume_analyzer")


PROMPT_TEMPLATE = """
You are an expert AI resume analysis engine for a recruitment platform.
Return STRICT JSON only. Do not return markdown. Do not add explanation outside JSON.
Do not invent facts that are not supported by the resume text.
If information is missing or uncertain, keep the output conservative and record it in `confidenceFlags`.

You are given:
1. Resume raw text
2. Active career categories from the system
3. Active skills from the system, including aliases

Your goals:
1. Infer the candidate's professional profile
2. Match resume skills against the provided system skills
3. Suggest the most relevant career category from the provided category list
4. Evaluate resume quality, readability, and ATS usefulness
5. Provide concrete improvement suggestions
6. Generate keywords and related job titles for later backend matching

Scoring rules for `resumeQualityScore`:
- roleClarity: 15%
- skillCoverage: 20%
- experienceQuality: 20%
- impactEvidence: 15%
- educationRelevance: 10%
- atsReadiness: 10%
- presentationClarity: 10%

Important constraints:
- Do not create job IDs or database IDs
- `careerCategorySuggestion` must come from the provided category list or be null
- `matchedSkills` should only contain skills that can be matched to the provided system skills
- Skills detected but not confidently matched to system skills must go to `otherDetectedSkills`
- `resumeQualityScore` is resume quality only, not a job matching score

Return this exact JSON shape:
{{
  "summary": "string",
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
      "evidence": "string"
    }
  ],
  "otherDetectedSkills": [
    {
      "name": "string",
      "normalizedName": "string",
      "confidence": 0,
      "evidence": "string"
    }
  ],
  "keywords": ["string"],
  "relatedJobTitles": ["string"],
  "strengths": ["string"],
  "weaknesses": ["string"],
  "improvementSuggestions": ["string"],
  "education": [
    {
      "school": "string",
      "degree": "string",
      "fieldOfStudy": "string",
      "startDate": "string",
      "endDate": "string",
      "description": "string"
    }
  ],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "startDate": "string",
      "endDate": "string",
      "durationMonths": 0,
      "description": "string",
      "achievements": ["string"]
    }
  ],
  "projects": [
    {
      "name": "string",
      "role": "string",
      "description": "string",
      "technologies": ["string"],
      "outcomes": ["string"]
    }
  ],
  "atsNotes": ["string"],
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
            response.resumeQualityScore = _clamp_score(response.resumeQualityScore)
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
        "max_tokens": 2200,
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
                    "evidence": f"Detected keyword for {skill.name}",
                }
            )

    if not matched_skills:
        for token in _extract_keywords(text)[:8]:
            other_skills.append(
                {
                    "name": token,
                    "normalizedName": token.lower(),
                    "confidence": 0.4,
                    "evidence": "Detected from fallback keyword extraction",
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
            "summary": text[:400] or "Resume summary unavailable",
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
            "strengths": ["Co noi dung CV de backend co the phan tich tiep"],
            "weaknesses": ["AI fallback dang o muc co ban, do tin cay thap hon provider chinh"],
            "improvementSuggestions": [
                "Bo sung so lieu ket qua cong viec cu the",
                "Lam ro vai tro chinh va cap do kinh nghiem",
                "Bo sung them ky nang cong nghe/noi dung ATS quan trong",
            ],
            "education": [],
            "experience": [],
            "projects": [],
            "atsNotes": [
                "Rule-based fallback duoc su dung, can kiem tra lai ket qua",
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
        "backend developer",
        "frontend developer",
        "full stack developer",
        "devops engineer",
        "data analyst",
        "product designer",
        "ui ux designer",
        "project manager",
    ]
    for role in role_hints:
        if role in lowered:
            return role.title()
    return "Professional Candidate"


def _clamp_score(value: float) -> float:
    return max(0, min(100, round(float(value), 2)))


def _supports_json_response_format(provider: str) -> bool:
    return provider in {"groq", "gemini"}
