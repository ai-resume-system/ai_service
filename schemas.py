from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CareerCategoryContext(BaseModel):
    name: str
    slug: str

    @field_validator("name", "slug")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class SkillContext(BaseModel):
    name: str
    slug: str
    careerCategorySlug: str | None = None
    aliases: list[str] = Field(default_factory=list)

    @field_validator("name", "slug", "careerCategorySlug")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class AnalyzeCvRequest(BaseModel):
    cvId: str = Field(min_length=1)
    rawText: str = Field(min_length=1)
    fileExtension: Literal["pdf", "docx", "doc"]
    requestedProvider: Literal["groq", "gemini", "glm"] | None = None
    availableCareerCategories: list[CareerCategoryContext] = Field(
        default_factory=list
    )
    availableSkills: list[SkillContext] = Field(default_factory=list)


class AnalysisScoreBreakdown(BaseModel):
    roleClarity: float = Field(ge=0, le=100)
    skillCoverage: float = Field(ge=0, le=100)
    experienceQuality: float = Field(ge=0, le=100)
    impactEvidence: float = Field(ge=0, le=100)
    educationRelevance: float = Field(ge=0, le=100)
    atsReadiness: float = Field(ge=0, le=100)
    presentationClarity: float = Field(ge=0, le=100)


class CareerCategorySuggestion(BaseModel):
    name: str
    slug: str
    confidence: float = Field(ge=0, le=100)


class MatchedSkill(BaseModel):
    name: str
    systemSkillSlug: str | None = None
    normalizedName: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    level: (
        Literal["beginner", "intermediate", "advanced", "expert", "unknown"]
        | None
    ) = "unknown"
    evidence: str | None = None

    @field_validator("name", "normalizedName", "systemSkillSlug", "evidence")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class OtherDetectedSkill(BaseModel):
    name: str
    normalizedName: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: str | None = None

    @field_validator("name", "normalizedName", "evidence")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class AnalysisEducation(BaseModel):
    school: str | None = None
    degree: str | None = None
    fieldOfStudy: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    description: str | None = None


class AnalysisExperience(BaseModel):
    company: str | None = None
    title: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    durationMonths: int | None = Field(default=None, ge=0)
    description: str | None = None
    achievements: list[str] = Field(default_factory=list)


class AnalysisProject(BaseModel):
    name: str | None = None
    role: str | None = None
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)


class AnalyzeCvResponseData(BaseModel):
    summary: str
    resumeQualityScore: float = Field(ge=0, le=100)
    scoreBreakdown: AnalysisScoreBreakdown
    primaryRole: str | None = None
    seniorityLevel: Literal[
        "intern",
        "fresher",
        "junior",
        "middle",
        "senior",
        "lead",
        "manager",
        "unknown",
    ] = "unknown"
    careerCategorySuggestion: CareerCategorySuggestion | None = None
    matchedSkills: list[MatchedSkill]
    otherDetectedSkills: list[OtherDetectedSkill]
    keywords: list[str]
    relatedJobTitles: list[str]
    strengths: list[str]
    weaknesses: list[str]
    improvementSuggestions: list[str]
    education: list[AnalysisEducation]
    experience: list[AnalysisExperience]
    projects: list[AnalysisProject]
    atsNotes: list[str]
    provider: str | None = None
    model: str | None = None
    confidenceFlags: list[str] = Field(default_factory=list)
    promptVersion: str | None = None
    analyzedAt: datetime | None = None


class AnalyzeCvResponse(BaseModel):
    data: AnalyzeCvResponseData
