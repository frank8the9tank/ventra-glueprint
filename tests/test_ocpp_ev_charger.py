"""The OCPP EV charger blueprint: Ventra-EMS's power (W, − = charging) → the charger's maximum
current (A) + charge control."""
import jinja2
import pytest
import yaml

from conftest import blueprint_path


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))   # !input x → "x"


@pytest.fixture(scope="module")
def blueprint():
    with open(blueprint_path("ev_charger", "ocpp_ev_charger.yaml"), encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


def _branches(blueprint):
    return blueprint["actions"][0]["choose"]


def test_picks_the_entities_of_both_integrations(blueprint):
    """Ventra-EMS's entities for an EV charger `evcharger1`: switch.ems_evcharger1_take_control and
    number.ems_evcharger1_power (the add-on's control_entities.ev_charger); the charger's from OCPP."""
    inputs = blueprint["blueprint"]["input"]
    assert inputs["ems_take_control"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    assert inputs["ems_setpoint"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "number"}
    assert "switch.ems_evcharger1_take_control" in inputs["ems_take_control"]["description"]
    assert "number.ems_evcharger1_power" in inputs["ems_setpoint"]["description"]
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
    assert set(branch["conditions"][1]["state"]) == {"Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing"}
    set_current, start = branch["sequence"]
    assert set_current["action"] == "number.set_value" and set_current["target"]["entity_id"] == "maximum_current"
    assert set_current["data"]["value"] == "{{ target_current }}"
    assert start["if"][0]["state"] == "off" and start["then"][-1]["action"] == "switch.turn_on"


def test_released_stops_charging_and_lowers_the_current(blueprint):
    branch = _branches(blueprint)[1]
    assert branch["conditions"][0]["state"] == "off"
    stop, lower = branch["sequence"]
    assert stop["if"][0]["state"] == "on" and stop["then"][0]["action"] == "switch.turn_off"   # only when it is on
    assert lower["then"][0]["data"]["value"] == "minimum_current"


def _amps(blueprint, setpoint, phases=3, voltage=230, minimum=6, maximum=16, step=1):
    environment = jinja2.Environment()
    environment.globals["states"] = lambda entity_id: str(setpoint)
    template = environment.from_string(blueprint["variables"]["target_current"])
    return template.render(ems_setpoint="number.ems_evcharger1_power", phases=phases, voltage=voltage,
                           minimum_current=minimum, maximum_current_limit=maximum, current_step=step).strip()


@pytest.mark.parametrize("setpoint, settings, expected", [
    (-6900, {}, "10"),                        # 6.9 kW on 3 × 230 V = 10 A
    (-11040, {}, "16"),                       # 16 A
    (-22000, {}, "16"),                       # capped at the maximum
    (-1400, {}, "6"),                         # below the minimum → the minimum
    (0, {}, "6"),
    ("unavailable", {}, "6"),
    (-3680, {"phases": 1}, "16"),             # 3.68 kW on one phase = 16 A
    (-7590, {"step": 2}, "12"),               # 11 A → even amps: 12
    (-6900, {"maximum": 32}, "10"),
])
def test_power_becomes_current(blueprint, setpoint, settings, expected):
    assert _amps(blueprint, setpoint, **settings) == expected
