"""The SolarEdge inverter limit blueprint: Ventra-EMS's power limit (W) → the site limit, with the limit
control mode on production control while Ventra-EMS limits, and disabled while it doesn't."""
import jinja2
import pytest
import yaml

from conftest import blueprint_path


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))   # !input x → "x"


@pytest.fixture(scope="module")
def blueprint():
    with open(blueprint_path("inverter", "solaredge_inverter_limit.yaml"), encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


def _branches(blueprint):
    return {branch["conditions"][0]["state"]: branch["sequence"] for branch in blueprint["actions"][0]["choose"]}


def test_picks_the_entities_of_the_integration(blueprint):
    """Ventra-EMS's entities for an inverter `solaredge` with a power limit:
    switch.ems_solaredge_limit_control and number.ems_solaredge_power_limit (control_entities.inverter_limit)."""
    inputs = blueprint["blueprint"]["input"]
    assert inputs["ems_limit_control"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    assert inputs["ems_power_limit"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "number"}
    assert "switch.ems_solaredge_limit_control" in inputs["ems_limit_control"]["description"]
    assert "number.ems_solaredge_power_limit" in inputs["ems_power_limit"]["description"]
    assert inputs["option_limiting"]["default"] == "Production Control" and inputs["option_free"]["default"] == "Disabled"


def test_runs_every_5_seconds_and_on_limit_control(blueprint):
    assert {"trigger": "time_pattern", "seconds": "/5"} in blueprint["triggers"]
    assert {"trigger": "state", "entity_id": "ems_limit_control"} in blueprint["triggers"]


def test_limiting_sets_the_mode_and_the_site_limit_when_they_differ(blueprint):
    mode, limit = _branches(blueprint)["on"]
    assert mode["then"][0]["action"] == "select.select_option" and str(mode["then"][0]["data"]["option"]) == "option_limiting"
    assert limit["then"][0]["action"] == "number.set_value" and limit["then"][0]["data"]["value"] == "{{ target_limit }}"
    assert "!=" in mode["if"][0]["value_template"] and "!=" in limit["if"][0]["value_template"]   # only written on a change


def test_free_disables_the_limit_control_mode(blueprint):
    (mode,) = _branches(blueprint)["off"]
    assert str(mode["then"][0]["data"]["option"]) == "option_free"


def _render(blueprint, limit_w, unit="W", minimum=0, maximum=100000):
    attributes = {"unit_of_measurement": unit, "min": minimum, "max": maximum}
    environment = jinja2.Environment()
    environment.globals.update(
        states=lambda entity_id: str(limit_w) if entity_id == "number.ems_solaredge_power_limit" else "unknown",
        state_attr=lambda entity_id, name: attributes.get(name) if entity_id == "number.solaredge_i1_site_limit" else None)
    template = environment.from_string(blueprint["variables"]["target_limit"])
    return template.render(ems_power_limit="number.ems_solaredge_power_limit", site_limit="number.solaredge_i1_site_limit").strip()


@pytest.mark.parametrize("limit_w, unit, expected", [
    (15000, "W", "15000"),
    (4300, "W", "4300"),
    (4300, "kW", "4.3"),          # a site limit entity in kW
    ("unavailable", "W", "0"),    # no limit → 0 (only while limiting)
])
def test_the_limit_in_the_site_limit_unit(blueprint, limit_w, unit, expected):
    maximum = 100 if unit == "kW" else 100000
    assert _render(blueprint, limit_w, unit, 0, maximum) == expected


def test_the_limit_stays_inside_the_entity_range(blueprint):
    assert _render(blueprint, 150000, maximum=20000) == "20000"
