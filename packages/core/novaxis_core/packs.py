"""Load a pack folder into a `PackSpec`, validating every file.

    packages/packs/novaxis_packs/<id>/
      manifest.yaml     id, name, tools, opening, emergencies, after-intake behaviour
      intake.yaml       ordered questions
      vocabulary.yaml   words the business uses
      workflows.yaml    follow-ups that run later
      dashboard.yaml    columns and buckets the dashboard shows
      prompts/system.md the worker's role and boundaries
      rules.py          optional: classify() for the gate, is_emergency() for the pre-check

Validation errors name the file and the key, so a typo in a pack is a one-line fix.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from novaxis_core.packspec import (
    TOOL_DEFINITIONS,
    DashboardSpec,
    EmergencyCheck,
    IntakeQuestion,
    Manifest,
    PackRule,
    PackSpec,
    WorkflowStep,
)


class PackError(ValueError):
    """A pack folder is missing something or a file is invalid."""


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise PackError(f"{path.name}: not valid YAML: {exc}") from exc


def _validate(model: type[BaseModel], data: Any, where: str) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first.get("loc", ())) or "(root)"
        raise PackError(f"{where}: {loc}: {first.get('msg')}") from exc


def _load_rules(folder: Path) -> tuple[PackRule | None, EmergencyCheck | None]:
    path = folder / "rules.py"
    if not path.exists():
        return None, None
    spec = importlib.util.spec_from_file_location(f"novaxis_pack_rules_{folder.name}", path)
    if spec is None or spec.loader is None:
        raise PackError("rules.py: cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    classify = getattr(module, "classify", None)
    is_emergency = getattr(module, "is_emergency", None)
    if classify is not None and not callable(classify):
        raise PackError("rules.py: classify must be a function")
    if is_emergency is not None and not callable(is_emergency):
        raise PackError("rules.py: is_emergency must be a function")
    return classify, is_emergency


def load_pack(folder: Path) -> PackSpec:
    folder = Path(folder)
    if not folder.is_dir():
        raise PackError(f"{folder}: not a directory")
    manifest_data = _read_yaml(folder / "manifest.yaml")
    if manifest_data is None:
        raise PackError("manifest.yaml: missing")
    manifest: Manifest = _validate(Manifest, manifest_data, "manifest.yaml")
    if manifest.id != folder.name:
        raise PackError(f"manifest.yaml: id: {manifest.id!r} does not match folder {folder.name!r}")

    prompt_path = folder / "prompts" / "system.md"
    if not prompt_path.exists():
        raise PackError("prompts/system.md: missing")
    system_prompt = prompt_path.read_text().strip()

    intake_raw = _read_yaml(folder / "intake.yaml") or {}
    questions = [
        _validate(IntakeQuestion, q, f"intake.yaml: questions[{i}]")
        for i, q in enumerate(intake_raw.get("questions", []))
    ]
    keys = [q.key for q in questions]
    if len(keys) != len(set(keys)):
        raise PackError("intake.yaml: duplicate question keys")
    for q in questions:
        for k in q.skip_if:
            if k not in keys:
                raise PackError(f"intake.yaml: questions.{q.key}.skip_if: unknown key {k!r}")

    workflows_raw = _read_yaml(folder / "workflows.yaml") or {}
    workflows = [
        _validate(WorkflowStep, w, f"workflows.yaml: steps[{i}]")
        for i, w in enumerate(workflows_raw.get("steps", []))
    ]
    dashboard = _validate(
        DashboardSpec, _read_yaml(folder / "dashboard.yaml") or {}, "dashboard.yaml"
    )
    vocabulary_raw = _read_yaml(folder / "vocabulary.yaml") or {}
    vocabulary = {str(k): str(v) for k, v in (vocabulary_raw.get("terms") or {}).items()}

    if manifest.service_area_field and manifest.service_area_field not in keys:
        raise PackError(
            "manifest.yaml: service_area_field: "
            f"{manifest.service_area_field!r} is not an intake key"
        )
    ai = manifest.after_intake
    if ai.service_code_from and ai.service_code_from not in keys:
        raise PackError(
            "manifest.yaml: after_intake.service_code_from: "
            f"{ai.service_code_from!r} is not an intake key"
        )

    if manifest.default_services:
        codes = {sv.code for sv in manifest.default_services}
        wanted = set(ai.service_code_map.values()) | (
            {ai.default_service_code} if ai.default_service_code else set()
        )
        if wanted - codes:
            raise PackError(
                "manifest.yaml: after_intake refers to service codes not in default_services: "
                f"{sorted(wanted - codes)}"
            )

    rule, emergency_check = _load_rules(folder)
    tools = [TOOL_DEFINITIONS[t] for t in manifest.tools if t in TOOL_DEFINITIONS]
    missing = [t for t in manifest.tools if t not in TOOL_DEFINITIONS]
    if missing:
        raise PackError(f"manifest.yaml: tools: no model-facing definition for {missing}")

    return PackSpec(
        id=manifest.id,
        name=manifest.name,
        system_prompt=system_prompt,
        tools=tools,
        intake_opening=manifest.intake_opening,
        intake=questions,
        workflows=workflows,
        dashboard=dashboard,
        vocabulary=vocabulary,
        emergency_keywords=tuple(k.lower() for k in manifest.emergency_keywords),
        emergency_reply=manifest.emergency_reply,
        emergency_alerted=manifest.emergency_alerted,
        emergency_not_alerted=manifest.emergency_not_alerted,
        emergency_check=emergency_check,
        rule=rule,
        high_risk_followup=manifest.high_risk_followup,
        handoff_notice=manifest.handoff_notice,
        service_area_field=manifest.service_area_field,
        out_of_area_reply=manifest.out_of_area_reply,
        after_intake=ai,
        manifest=manifest.model_dump(),
    )
