"""Tests for P1-3: Skill Guidance — guidance generation and context-aware suggestions.

Tests cover:
- SkillGuidance.generate_guidance: formatted guidance strings
- SkillGuidance.suggest_skills: context-aware ranking
- Edge cases: empty context, no matches, single skill
"""

from __future__ import annotations

from cscode.skills.loader import Skill, SkillGuidance

# ─── Fixtures ────────────────────────────────────────────────────────

SAMPLE_SKILLS = [
    Skill(
        name="Python Testing",
        slug="python-testing",
        content="# Python Testing\n\n## Description\nGuidelines for pytest usage.",
        path="/tmp/skills/python-testing.md",
        description="Guidelines for pytest usage.",
    ),
    Skill(
        name="React Components",
        slug="react-components",
        content="# React Components\n\n## Description\nBest practices for React component design.",
        path="/tmp/skills/react-components.md",
        description="Best practices for React component design.",
    ),
    Skill(
        name="Database Migrations",
        slug="database-migrations",
        content="# Database Migrations\n\n## Description\nSQL migration patterns and tools.",
        path="/tmp/skills/database-migrations.md",
        description="SQL migration patterns and tools.",
    ),
]


# ─── Guidance Generation ────────────────────────────────────────────


class TestGenerateGuidance:
    def test_generate_guidance_returns_string(self) -> None:
        guidance = SkillGuidance.generate_guidance(SAMPLE_SKILLS[0])
        assert isinstance(guidance, str)
        assert len(guidance) > 0

    def test_guidance_includes_skill_name(self) -> None:
        guidance = SkillGuidance.generate_guidance(SAMPLE_SKILLS[0])
        assert "Python Testing" in guidance

    def test_guidance_includes_description(self) -> None:
        guidance = SkillGuidance.generate_guidance(SAMPLE_SKILLS[0])
        assert "pytest" in guidance

    def test_guidance_format(self) -> None:
        guidance = SkillGuidance.generate_guidance(SAMPLE_SKILLS[1])
        assert guidance.startswith("##")
        assert "React Components" in guidance
        assert "**Trigger**" in guidance
        assert "**File**" in guidance


# ─── Context-Aware Suggestions ──────────────────────────────────────


class TestSuggestSkills:
    def test_suggest_returns_list(self) -> None:
        results = SkillGuidance.suggest_skills("testing", SAMPLE_SKILLS)
        assert isinstance(results, list)

    def test_suggest_empty_context(self) -> None:
        results = SkillGuidance.suggest_skills("", SAMPLE_SKILLS)
        assert results == []

    def test_suggest_returns_tuples(self) -> None:
        results = SkillGuidance.suggest_skills("testing", SAMPLE_SKILLS)
        for item in results:
            assert len(item) == 2
            skill, score = item
            assert isinstance(skill, Skill)
            assert isinstance(score, float)

    def test_suggest_ranks_testing_highest(self) -> None:
        results = SkillGuidance.suggest_skills("test pytest", SAMPLE_SKILLS)
        assert len(results) >= 1
        # Python Testing should be first (highest score)
        assert results[0][0].name == "Python Testing"

    def test_suggest_ranks_react_highest(self) -> None:
        results = SkillGuidance.suggest_skills("react component ui", SAMPLE_SKILLS)
        assert results[0][0].name == "React Components"

    def test_suggest_ranks_database_highest(self) -> None:
        results = SkillGuidance.suggest_skills("sql migration database", SAMPLE_SKILLS)
        assert results[0][0].name == "Database Migrations"

    def test_suggest_returns_top_k(self) -> None:
        results = SkillGuidance.suggest_skills("test", SAMPLE_SKILLS, top_k=1)
        assert len(results) == 1

    def test_suggest_returns_all_when_top_k_large(self) -> None:
        results = SkillGuidance.suggest_skills("testing", SAMPLE_SKILLS, top_k=10)
        assert len(results) <= len(SAMPLE_SKILLS)

    def test_suggest_with_threshold(self) -> None:
        results = SkillGuidance.suggest_skills("xyzzy", SAMPLE_SKILLS, min_score=0.5)
        assert results == []

    def test_suggest_empty_skills_list(self) -> None:
        results = SkillGuidance.suggest_skills("testing", [])
        assert results == []

    def test_suggest_score_between_zero_and_one(self) -> None:
        results = SkillGuidance.suggest_skills("test pytest database", SAMPLE_SKILLS)
        for _, score in results:
            assert 0.0 <= score <= 1.0

    def test_suggest_ordered_by_score_desc(self) -> None:
        results = SkillGuidance.suggest_skills("test pytest react ui", SAMPLE_SKILLS)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    def test_suggest_with_context_in_name_and_description(self) -> None:
        results = SkillGuidance.suggest_skills("database migrations", SAMPLE_SKILLS)
        best_skill, best_score = results[0]
        assert best_skill.name == "Database Migrations"
        assert best_score > 0.0
        assert best_score <= 1.0

    def test_suggest_no_matching_keywords(self) -> None:
        """Completely unrelated context should return empty or very low scores."""
        results = SkillGuidance.suggest_skills("quantum physics astronomy", SAMPLE_SKILLS, min_score=0.1)
        # None of our skills mention quantum/astronomy
        assert len(results) == 0
