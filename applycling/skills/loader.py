"""Skill loader — reads SKILL.md files with YAML frontmatter.

Each skill lives in applycling/skills/<name>/SKILL.md.
The file format is:

    ---
    name: skill_name
    description: one-line purpose
    inputs:
      - key1
      - key2
    output_file: output.md   # optional
    ---

    Prompt body here.  Uses {key1} and {key2} via str.format.

Usage:
    from applycling.skills import load_skill

    skill = load_skill("cover_letter")
    prompt = skill.render(role_intel=..., tailored_resume=..., ...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SKILLS_DIR = Path(__file__).resolve().parent


class SkillError(Exception):
    """Raised when a skill cannot be loaded or rendered."""


@dataclass
class Skill:
    """A loaded skill with its template and metadata."""

    name: str
    description: str
    inputs: list[str]
    template: str
    output_file: str | None = None
    model_hint: str | None = None
    temperature: float | None = None

    def render(self, **kwargs: Any) -> str:
        """Apply str.format to the template with the given keyword arguments.

        Raises SkillError if any declared input is missing from kwargs.
        """
        missing = [k for k in self.inputs if k not in kwargs]
        if missing:
            raise SkillError(
                f"Skill '{self.name}' missing required inputs: {missing}"
            )
        try:
            return self.template.format(**kwargs)
        except KeyError as exc:
            raise SkillError(
                f"Skill '{self.name}' template references undefined key: {exc}"
            ) from exc


def load_skill(name: str) -> Skill:
    """Load a skill by name from SKILLS_DIR/<name>/SKILL.md.

    Parses the YAML frontmatter block and returns a Skill dataclass.

    Raises SkillError if the file is missing, malformed, or the frontmatter
    name does not match the requested skill name.
    """
    skill_path = SKILLS_DIR / name / "SKILL.md"
    if not skill_path.exists():
        raise SkillError(f"Skill '{name}' not found at {skill_path}")

    raw = skill_path.read_text(encoding="utf-8")

    # Split on the YAML frontmatter delimiters.
    # Format: "---\n<yaml>\n---\n<body>"
    if not raw.startswith("---\n"):
        raise SkillError(
            f"Skill '{name}': SKILL.md must start with '---\\n' frontmatter block."
        )

    # Find the closing ---
    rest = raw[4:]  # strip leading "---\n"
    end_idx = rest.find("\n---\n")
    if end_idx == -1:
        raise SkillError(
            f"Skill '{name}': could not find closing '---' in frontmatter."
        )

    frontmatter_text = rest[:end_idx]
    body = rest[end_idx + 5:]  # skip "\n---\n"

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise SkillError(f"Skill '{name}': invalid YAML frontmatter: {exc}") from exc

    if not isinstance(frontmatter, dict):
        raise SkillError(f"Skill '{name}': frontmatter must be a YAML mapping.")

    # Validate name matches
    fm_name = frontmatter.get("name")
    if fm_name != name:
        raise SkillError(
            f"Skill file name mismatch: requested '{name}' but frontmatter says '{fm_name}'."
        )

    inputs = frontmatter.get("inputs") or []
    if not isinstance(inputs, list):
        raise SkillError(f"Skill '{name}': 'inputs' must be a YAML list.")

    return Skill(
        name=name,
        description=frontmatter.get("description", ""),
        inputs=inputs,
        template=body.lstrip("\n"),
        output_file=frontmatter.get("output_file"),
        model_hint=frontmatter.get("model_hint"),
        temperature=frontmatter.get("temperature"),
    )
