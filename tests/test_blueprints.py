"""Every blueprint: valid YAML with !input, the Ventra-EMS header, inputs used = declared, and the
catalogue (index.json) up to date."""
import os

import pytest

import build_index
from conftest import BLUEPRINTS, InputTag, declared_inputs, load


def _inputs_used(node):
    if isinstance(node, InputTag):
        yield str(node)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _inputs_used(value)
    elif isinstance(node, list):
        for value in node:
            yield from _inputs_used(value)


def test_there_are_blueprints():
    assert BLUEPRINTS


@pytest.mark.parametrize("path", BLUEPRINTS, ids=os.path.basename)
def test_blueprint_is_valid(path):
    data = load(path)
    blueprint = data["blueprint"]
    assert blueprint["name"].startswith("Ventra-EMS")
    assert blueprint["domain"] == "automation"
    declared = set(declared_inputs(blueprint))
    used = set(_inputs_used({key: value for key, value in data.items() if key != "blueprint"}))
    assert used == declared, f"inputs used {used} vs declared {declared}"
    assert data.get("triggers") and data.get("actions")


@pytest.mark.parametrize("path", BLUEPRINTS, ids=os.path.basename)
def test_header_is_complete(path):
    entry, problems = build_index.entry_for(path)
    assert problems == []
    assert f"Version {entry['version']}." in load(path)["blueprint"]["description"]      # the version users see


def test_the_index_is_up_to_date():
    """Run `python tools/build_index.py` after changing a blueprint."""
    assert build_index.main(["build_index.py", "--check"]) == 0


@pytest.mark.parametrize("header, problem", [
    ("# ventra-ems-blueprint-version: x\n", "blueprint-version"),
    ("# ventra-ems-blueprint-version: 1\n# ventra-ems-device-types: toaster\n", "device-types"),
    ("# ventra-ems-blueprint-version: 1\n# ventra-ems-device-types: battery\n# ventra-ems-min-version: soon\n", "min-version"),
    ("# ventra-ems-blueprint-version: 1\n# ventra-ems-device-types: battery\n# ventra-ems-min-version: 1.0.600\n"
     "# ventra-ems-max-version: 1.0.599\n", "below"),
])
def test_a_wrong_header_is_refused(tmp_path, header, problem):
    path = tmp_path / "wrong.yaml"
    path.write_text(header + "blueprint: {}\n", encoding="utf-8")
    _, problems = build_index.entry_for(str(path))
    assert any(problem in text for text in problems), problems


def test_versions_compare_as_numbers():
    assert build_index.ems_version("1.0.462.2") > build_index.ems_version("1.0.462")
    assert build_index.ems_version("1.0.1000") > build_index.ems_version("1.0.999")


def test_the_index_lists_the_inputs_with_their_ventra_ems_role():
    index, _ = build_index.build()
    heatpump = next(entry for entry in index["blueprints"] if entry["id"] == "heatpump_relays")
    inputs = {item["name"]: item for item in heatpump["inputs"]}
    assert inputs["ems_take_control"]["ems_role"] == "take_control"
    assert inputs["ems_heating_relay"]["ems_role"] == "heating_relay" and inputs["ems_heating_relay"]["section"] == "Heating"
    assert "ems_role" not in inputs["heating_switch"] and inputs["heating_switch"]["default"] == ""
    assert inputs["heating_conditions"]["selector"] == {"condition": {}}
    assert heatpump["name"].startswith("Ventra-EMS") and heatpump["description"]
