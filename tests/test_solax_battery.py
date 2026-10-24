"""The Solax battery blueprint: Ventra-EMS's setpoint (W, − = charge) → Solax remote control (+ = charge)."""
import jinja2
import pytest
import yaml

from conftest import blueprint_path


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))   # !input x → "x"


@pytest.fixture(scope="module")
def blueprint():
    with open(blueprint_path("battery", "solax_battery.yaml"), encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


def _branches(blueprint):
    choose = blueprint["actions"][0]["choose"]
    return {branch["conditions"][0]["state"]: branch["sequence"] for branch in choose}


def test_picks_the_entities_of_the_integration(blueprint):
    """Ventra-EMS's entities for a battery `solax`: switch.ems_solax_take_control and
    number.ems_solax_battery_power (the add-on's control_entities.battery)."""
    inputs = blueprint["blueprint"]["input"]
    assert inputs["ems_take_control"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    assert inputs["ems_setpoint"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "number"}
    assert "switch.ems_solax_take_control" in inputs["ems_take_control"]["description"]
    assert "number.ems_solax_battery_power" in inputs["ems_setpoint"]["description"]


def test_solax_entities_default_to_the_solax_modbus_names(blueprint):
    inputs = blueprint["blueprint"]["input"]
    assert inputs["active_power"]["default"] == "number.solax_remotecontrol_active_power"
    assert inputs["power_control"]["default"] == "select.solax_remotecontrol_power_control"
    assert inputs["autorepeat_duration"]["default"] == "number.solax_remotecontrol_autorepeat_duration"
    assert inputs["trigger_button"]["default"] == "button.solax_remotecontrol_trigger"
    assert inputs["autorepeat_secs"]["default"] == 3660


def test_runs_every_5_seconds_and_writes_every_run(blueprint):
    assert {"trigger": "time_pattern", "seconds": "/5"} in blueprint["triggers"]
    assert blueprint["conditions"] == []                         # no "only when changed"


def test_controlled_sets_autorepeat_power_enables_and_triggers(blueprint):
    steps = _branches(blueprint)["on"]
    assert [(step["action"], str(step["target"]["entity_id"])) for step in steps] == [
        ("number.set_value", "autorepeat_duration"),
        ("number.set_value", "active_power"),
        ("select.select_option", "power_control"),
        ("button.press", "trigger_button"),
    ]
    assert steps[1]["data"]["value"] == "{{ target_power }}"
    assert str(steps[2]["data"]["option"]) == "option_enabled"


def test_released_gives_the_battery_back_to_the_inverter(blueprint):
    steps = _branches(blueprint)["off"]
    assert [(step["action"], str(step["target"]["entity_id"])) for step in steps] == [
        ("number.set_value", "active_power"),
        ("select.select_option", "power_control"),
    ]
    assert steps[0]["data"]["value"] == 0 and str(steps[1]["data"]["option"]) == "option_disabled"


def _render(blueprint, setpoint, unit="W", minimum=-10000, maximum=10000):
    """Render target_power like HA would, with states() / state_attr() for the two entities."""
    attributes = {"unit_of_measurement": unit, "min": minimum, "max": maximum}
    environment = jinja2.Environment()
    environment.globals.update(
        states=lambda entity_id: str(setpoint) if entity_id == "number.ems_solax_battery_power" else "unknown",
        state_attr=lambda entity_id, name: attributes.get(name) if entity_id == "number.solax_remotecontrol_active_power" else None)
    template = environment.from_string(blueprint["variables"]["target_power"])
    return template.render(ems_setpoint="number.ems_solax_battery_power",
                           active_power="number.solax_remotecontrol_active_power").strip()


@pytest.mark.parametrize("setpoint, unit, expected", [
    (-1500, "W", "1500"),          # Ventra charges 1.5 kW → Solax +1500 W
    (2000, "W", "-2000"),          # discharge
    (0, "W", "0"),
    (-1500, "kW", "1.5"),          # an active power entity in kW
    ("unavailable", "W", "0"),     # no setpoint → nothing
])
def test_setpoint_is_negated_and_converted(blueprint, setpoint, unit, expected):
    minimum, maximum = (-10, 10) if unit == "kW" else (-10000, 10000)
    assert _render(blueprint, setpoint, unit, minimum, maximum) == expected


def test_setpoint_is_kept_inside_the_entity_range(blueprint):
    assert _render(blueprint, -20000) == "10000"
    assert _render(blueprint, 20000) == "-10000"
