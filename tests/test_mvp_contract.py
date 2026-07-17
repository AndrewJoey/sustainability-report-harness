"""Regression checks for the user-visible Markdown-first MVP contract."""

from pathlib import Path

SKILL = Path("skills/sustainability-report-harness/SKILL.md")
README = Path("README.md")


def test_skill_requires_every_conversational_input_before_drafting():
    text = SKILL.read_text(encoding="utf-8")

    for required_phrase in (
        "client materials",
        "existing report or client template",
        "reporting frameworks selected by the consultant",
        "excellent/reference reports",
        "report purpose, audience, tone, and required topics",
    ):
        assert required_phrase in text
    assert "Reference reports are optional" in text
    assert "at least one target framework are required" in text


def test_skill_and_beginner_guide_publish_the_same_markdown_delivery():
    skill = SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    expected_paths = (
        "outputs/markdown/master_report.md",
        "outputs/markdown/adapted_<standard-id>.md",
        "outputs/markdown/report_manifest.json",
    )

    for path in expected_paths:
        assert path in skill
        assert path in readme
    for marker in ("[待确认-推断]", "[建议文本]", "[信息缺口]"):
        assert marker in skill
        assert marker in readme


def test_compatibility_claims_match_selected_mvp_scope():
    compatibility = Path(
        "skills/sustainability-report-harness/references/AGENT-COMPATIBILITY.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(compatibility.split())

    for agent in ("Codex", "Claude Code", "WorkBuddy", "Trae"):
        assert agent in normalized
    assert "Product-specific live execution" in normalized
    assert "is not an MVP acceptance requirement" in normalized
    assert "is not claimed as tested" in normalized
