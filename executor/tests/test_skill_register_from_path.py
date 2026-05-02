"""Test SkillLoader.register_from_path (added during W5+W6 integration)."""
import pytest
from pathlib import Path
from executor.plugins.skill_loader import SkillLoader


def test_register_from_path_loads_skill(tmp_path: Path):
    skill_dir = tmp_path / "git-helper"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: git-helper\ndescription: Git workflow helper\n"
        "triggers: [git, commit]\nagents: []\n---\nbody",
        encoding="utf-8",
    )
    loader = SkillLoader(skills_dir=str(tmp_path), hook_system=None)
    meta = loader.register_from_path(str(skill_dir))
    assert meta is not None
    assert meta.name == "git-helper"
    assert "git-helper" in loader.registry


def test_register_from_path_missing_dir(tmp_path: Path):
    loader = SkillLoader(skills_dir=str(tmp_path), hook_system=None)
    assert loader.register_from_path(str(tmp_path / "nonexistent")) is None


def test_register_from_path_missing_skill_md(tmp_path: Path):
    skill_dir = tmp_path / "empty-skill"
    skill_dir.mkdir()
    loader = SkillLoader(skills_dir=str(tmp_path), hook_system=None)
    assert loader.register_from_path(str(skill_dir)) is None
