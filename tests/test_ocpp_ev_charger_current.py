"""The OCPP EV charger blueprint with Ventra-EMS's current (A): number.ems_<id>_current → the
charger's maximum current (even amps, at least 6) + charge control."""
import jinja2
import pytest
import yaml

from conftest import blueprint_path


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))   # !input x → "x"


@pytest.fixture(scope="module")
def blueprint():
    with open(blueprint_path("ev_charger", "ocpp_ev_charger_current.yaml"), encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


def _branches(blueprint):
    return blueprint["actions"][0]["choose"]


def test_picks_the_entities_of_both_integrations(blueprint):
    """Ventra-EMS's entities for an EV charger `evcharger1`: switch.ems_evcharger1_take_control and
    number.ems_evcharger1_current (the add-on's control_entities.ev_charger); the charger's from OCPP.
    No phases, voltage or step: Ventra-EMS's current has them already, even amps are built in."""
    inputs = blueprint["blueprint"]["input"]
    assert set(inputs) == {"ems_take_control", "ems_current", "connector_status", "maximum_current", "charge_control"}
    assert inputs["ems_current"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "number"}
    assert "number.ems_evcharger1_current" in inputs["ems_current"]["description"]
    for name, domain in (("connector_status", "sensor"), ("maximum_current", "number"), ("charge_control", "switch")):
        assert inputs[name]["selector"]["entity"]["filter"][0] == {"integration": "ocpp", "domain": domain}


def test_checks_every_15_seconds_on_plugging_in_and_on_take_control(blueprint):
    triggers = blueprint["triggers"]
    assert {"trigger": "time_pattern", "seconds": "/15"} in triggers
    assert {"trigger": "state", "entity_id": "connector_status", "to": "Preparing"} in triggers
    assert {"trigger": "state", "entity_id": "ems_take_control"} in triggers


def test_controlled_with_a_car_sets_the_current_and_starts_charging(blueprint):
    branch = _branches(blueprint)[0]
    assert branch["conditions"][0] == {"condition": "state", "entity_id": "ems_take_control", "state": "on"}
    set_current, start = branch["sequence"]
    assert set_current["target"]["entity_id"] == "maximum_current" and set_current["data"]["value"] == "{{ target_current }}"
    assert start["then"][-1]["action"] == "switch.turn_on"


def test_released_stops_charging_and_goes_back_to_six_amps(blueprint):
    branch = _branches(blueprint)[1]
    stop, lower = branch["sequence"]
    assert stop["then"][0]["action"] == "switch.turn_off"
    assert lower["if"][0]["above"] == 6 and lower["then"][0]["data"]["value"] == 6


def _amps(blueprint, current):
    environment = jinja2.Environment()
    environment.globals["states"] = lambda entity_id: str(current)
    return environment.from_string(blueprint["variables"]["target_current"]).render(ems_current="number.x").strip()


@pytest.mark.parametrize("current, expected", [
    (16.0, "16"), (15.9, "16"), (13.0, "14"), (10.7, "10"), (6.0, "6"),
    (4.0, "6"), (0, "6"), ("unavailable", "6"),
])
def test_the_current_becomes_even_amps_from_six(blueprint, current, expected):
    assert _amps(blueprint, current) == expected
