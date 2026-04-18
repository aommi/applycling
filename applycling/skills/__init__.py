"""Skill loader package for applycling.

Usage:
    from applycling.skills import load_skill, Skill, SkillError
"""

from .loader import Skill, SkillError, load_skill

__all__ = ["Skill", "SkillError", "load_skill"]
