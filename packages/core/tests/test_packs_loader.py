"""The loader validates every file and names the file and key on failure."""

from __future__ import annotations

from pathlib import Path

import pytest

from novaxis_core.packs import PackError, load_pack

GOOD_MANIFEST = """
id: {id}
name: Test pack
tools: [extract_fields, hand_to_human]
intake_opening: "Hello"
"""


def _write(
    folder: Path,
    manifest: str = GOOD_MANIFEST,
    intake: str = "questions: []",
    rules: str | None = None,
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.yaml").write_text(manifest.format(id=folder.name))
    (folder / "intake.yaml").write_text(intake)
    (folder / "prompts").mkdir(exist_ok=True)
    (folder / "prompts" / "system.md").write_text("You are a test.")
    if rules is not None:
        (folder / "rules.py").write_text(rules)
    return folder


def test_minimal_pack_loads(tmp_path: Path) -> None:
    p = load_pack(_write(tmp_path / "testpack"))
    assert p.id == "testpack" and [t["name"] for t in p.tools] == [
        "extract_fields",
        "hand_to_human",
    ]
    assert p.rule is None and p.emergency_check is None


def test_unknown_action_kind_is_rejected_with_file_and_key(tmp_path: Path) -> None:
    bad = GOOD_MANIFEST.replace("[extract_fields, hand_to_human]", "[extract_fields, teleport]")
    with pytest.raises(PackError, match=r"manifest\.yaml: tools: .*teleport"):
        load_pack(_write(tmp_path / "testpack", manifest=bad))


def test_id_must_match_folder(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="does not match folder"):
        load_pack(_write(tmp_path / "other", manifest=GOOD_MANIFEST.replace("{id}", "testpack")))


def test_missing_prompt_is_named(tmp_path: Path) -> None:
    folder = _write(tmp_path / "testpack")
    (folder / "prompts" / "system.md").unlink()
    with pytest.raises(PackError, match=r"prompts/system\.md: missing"):
        load_pack(folder)


def test_bad_intake_question_is_named(tmp_path: Path) -> None:
    intake = "questions:\n  - key: Name-Bad\n    ask: hi\n"
    with pytest.raises(PackError, match=r"intake\.yaml: questions\[0\]: key"):
        load_pack(_write(tmp_path / "testpack", intake=intake))


def test_skip_if_unknown_key_is_named(tmp_path: Path) -> None:
    intake = "questions:\n  - key: a\n    ask: A?\n  - key: b\n    ask: B?\n    skip_if: {zzz: x}\n"
    with pytest.raises(PackError, match=r"questions\.b\.skip_if: unknown key 'zzz'"):
        load_pack(_write(tmp_path / "testpack", intake=intake))


def test_service_area_field_must_be_an_intake_key(tmp_path: Path) -> None:
    manifest = GOOD_MANIFEST + "service_area_field: postcode\n"
    with pytest.raises(PackError, match="service_area_field"):
        load_pack(_write(tmp_path / "testpack", manifest=manifest))


def test_rules_hooks_load(tmp_path: Path) -> None:
    rules = (
        "def classify(kind, params, ctx):\n    return 'high'\n\n"
        "def is_emergency(text):\n    return 'boom' in text\n"
    )
    p = load_pack(_write(tmp_path / "testpack", rules=rules))
    assert p.rule is not None and p.rule("reply", {}, None) == "high"
    assert (
        p.emergency_check is not None
        and p.emergency_check("boom")
        and not p.emergency_check("calm")
    )


def test_shipped_packs_load() -> None:
    from novaxis_packs import available_packs, get_pack

    assert {"generic", "hvac"} <= set(available_packs())
    hvac = get_pack("hvac")
    assert (
        hvac.service_area_field == "postcode" and len(hvac.intake) == 8 and len(hvac.workflows) == 3
    )
    assert hvac.emergency_check is not None and hvac.rule is not None
    assert get_pack("nonexistent").id == "generic"


def test_emergency_reply_may_not_promise_an_alert() -> None:
    import pytest
    from pydantic import ValidationError

    from novaxis_core.packspec import Manifest

    with pytest.raises(ValidationError, match="emergency_alerted"):
        Manifest.model_validate(
            {
                "id": "x",
                "name": "X",
                "tools": ["reply"],
                "intake_opening": "Hi",
                "emergency_reply": "Leave now. I have alerted our engineer.",
            }
        )
