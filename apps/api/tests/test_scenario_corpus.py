import re
from pathlib import Path

import pytest

from app.modules.neural.models import MemoryKind
from app.modules.neural.service import understand_with_rules

CORPUS = (
    Path(__file__).resolve().parents[3] / "docs" / "validation" / "B00-scenarios.md"
)
SCENARIO_ROW = re.compile(r"^\| (S\d{2}) \| ([^|]+) \| (.+?) \| (.+?) \|$")


def scenario_rows() -> list[tuple[str, str, str, str]]:
    return [
        match.groups()
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if (match := SCENARIO_ROW.match(line))
    ]


def test_scenario_corpus_has_sixty_unique_french_contract_cases() -> None:
    rows = scenario_rows()
    identifiers = [row[0] for row in rows]

    assert len(rows) == 60
    assert identifiers == [f"S{index:02d}" for index in range(1, 61)]
    assert {row[1].strip() for row in rows} >= {
        "capture",
        "sécurité",
        "reprise",
        "voix",
    }
    assert any("conversations cachées" in row[2] for row in rows)


@pytest.mark.parametrize(
    ("text", "expected_kind"),
    [
        ("Appeler le plombier demain", MemoryKind.INTENTION),
        ("Je dois être à la gare samedi à 8 h", MemoryKind.ENGAGEMENT),
        ("Rappelle-moi les poubelles jeudi à 20 h", MemoryKind.ENGAGEMENT),
    ],
)
def test_deterministic_corpus_examples_use_safe_capture_kinds(
    text: str, expected_kind: MemoryKind
) -> None:
    result = understand_with_rules(text)

    assert result.kind is expected_kind
    assert result.capability in {"task", "reminder"}
