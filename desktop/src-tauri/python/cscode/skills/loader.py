from __future__ import annotations

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
