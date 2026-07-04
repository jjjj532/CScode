from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    """Loaded skill definition."""

    name: str
    slug: str
    content: str
    path: str
    description: str = ""


class SkillLoader:
    async def load_skill(self, path: str) -> Skill | None:
        skill_path = Path(path)
        if not skill_path.exists():
            return None

        content = skill_path.read_text(encoding="utf-8")
        slug = skill_path.stem
        name = self._extract_title(content) or slug
        description = self._extract_description(content)

        return Skill(
            name=name,
            slug=slug,
            content=content,
            path=str(skill_path.resolve()),
            description=description,
        )

    async def discover(self, skills_dir: str) -> list[Skill]:
        path = Path(skills_dir)
        if not path.exists() or not path.is_dir():
            return []

        skills: list[Skill] = []
        for item in sorted(path.iterdir()):
            if item.suffix.lower() in (".md", ".markdown"):
                skill = await self.load_skill(str(item))
                if skill is not None:
                    skills.append(skill)
        return skills

    def _extract_title(self, content: str) -> str | None:
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    def _extract_description(self, content: str) -> str:
        in_description = False
        for line in content.splitlines():
            if line.strip().startswith("## Description"):
                in_description = True
                continue
            if in_description and line.strip().startswith("## "):
                break
            if in_description and line.strip():
                return line.strip()
        return ""


class SkillGuidance:
    """Guidance generation and context-aware skill suggestions.

    Provides:
    - generate_guidance(skill): formatted guidance string for using a skill
    - suggest_skills(context, skills, ...): rank skills by relevance to context
    """

    @staticmethod
    def generate_guidance(skill: Skill) -> str:
        """Generate a formatted guidance string for a skill.

        Returns a markdown section describing the skill, its purpose,
        and usage context.
        """
        return (
            f"## {skill.name}\n\n"
            f"{skill.description}\n\n"
            f"**Trigger**: Use when working with {skill.name.lower()}.\n"
            f"**File**: `{skill.path}`\n\n"
        )

    @staticmethod
    def suggest_skills(
        context: str,
        skills: list[Skill],
        top_k: int = 3,
        min_score: float = 0.0,
    ) -> list[tuple[Skill, float]]:
        """Suggest skills relevant to a given context.

        Uses keyword overlap scoring between the context and each skill's
        name + description. Skills with no overlap or score below
        min_score are excluded.

        Args:
            context: Free-text description of the current task.
            skills: List of available skills.
            top_k: Maximum number of suggestions to return.
            min_score: Minimum relevance score [0.0-1.0].

        Returns:
            List of (skill, score) tuples sorted by score descending.
        """
        if not context.strip() or not skills:
            return []

        context_tokens = _tokenize(context)
        if not context_tokens:
            return []

        scored: list[tuple[Skill, float]] = []
        for skill in skills:
            skill_text = f"{skill.name} {skill.description}"
            skill_tokens = _tokenize(skill_text)
            if not skill_tokens:
                continue

            matches = sum(1 for t in context_tokens if t in skill_tokens)
            score = matches / len(skill_tokens)
            if score >= min_score:
                scored.append((skill, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase words, excluding very short tokens."""
    words = re.findall(r"[a-zA-Z_]\w+", text.lower())
    return {w for w in words if len(w) > 1}
