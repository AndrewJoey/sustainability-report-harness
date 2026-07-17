from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "user-guide.html"


class GuideParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.references: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.ids.add(element_id)
        for name in ("href", "src"):
            if reference := attributes.get(name):
                self.references.append((name, reference))


def parse_guide() -> tuple[str, GuideParser]:
    html = GUIDE.read_text(encoding="utf-8")
    parser = GuideParser()
    parser.feed(html)
    return html, parser


def test_user_guide_is_self_contained_and_has_required_sections() -> None:
    html, parser = parse_guide()

    assert "<!doctype html>" in html.lower()
    assert {
        "overview",
        "clone",
        "start",
        "prepare",
        "workflow",
        "outputs",
        "safety",
        "manual",
        "faq",
    } <= parser.ids
    assert not [
        reference
        for _, reference in parser.references
        if reference.startswith(("http://", "https://", "//"))
    ]
    assert all(
        reference.removeprefix("#") in parser.ids
        for _, reference in parser.references
        if reference.startswith("#")
    )


def test_user_guide_relative_document_links_exist() -> None:
    _, parser = parse_guide()

    relative_documents = [
        reference
        for _, reference in parser.references
        if not reference.startswith(("#", "http://", "https://", "//"))
    ]
    assert relative_documents
    assert all((GUIDE.parent / reference).resolve().is_file() for reference in relative_documents)


def test_user_guide_matches_public_markdown_commands_and_outputs() -> None:
    html, _ = parse_guide()

    expected_contracts = (
        "git clone https://github.com/AndrewJoey/sustainability-report-harness.git",
        "confirm_intake.py confirm",
        "standards.py lock",
        "export_markdown.py generate",
        "export_markdown.py validate",
        "outputs/markdown/master_report.md",
        "outputs/markdown/adapted_&lt;standard-id&gt;.md",
        "outputs/markdown/report_manifest.json",
        "[待确认-推断]",
        "[建议文本]",
        "[信息缺口]",
    )
    for contract in expected_contracts:
        assert contract in html


def test_readme_links_to_user_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "[可视化 HTML 使用指南](./docs/user-guide.html)" in readme
