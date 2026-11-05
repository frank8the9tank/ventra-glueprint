"""The Solax hybrid blueprint (mode 8, 2026-11-05): Ventra-EMS's battery setpoint (W, + = discharge) and
the inverter's power limit → Solax "PV and BAT control"; only the limit → "Enabled Grid Control";
neither → remote control disabled."""
import jinja2
import pytest
import yaml

from conftest import blueprint_path


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))   # !input x → "x"


@pytest.fixture(scope="module")
def blueprint():
    with open(blueprint_path("battery", "solax_hybrid.yaml"), encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


def _env(states, attributes=None):
    """A Jinja environment with HA's states() / is_state() / state_attr() over a dict of states."""
    attributes = attributes or {}
    environment = jinja2.Environment()
    environment.globals.update(
        states=lambda entity_id: str(states.get(entity_id, "unknown")),
        is_state=lambda entity_id, value: str(states.get(entity_id)) == value,
        state_attr=lambda entity_id, name: (attributes.get(entity_id) or {}).get(name))
    return environment


NAMES = {"ems_take_control": "switch.ems_solax_take_control", "ems_setpoint": "number.ems_solax_battery_power",
         "ems_limit_control": "switch.ems_solax_limit_control", "ems_power_limit": "number.ems_solax_power_limit",
         "push_power": "number.solax_remotecontrol_push_mode_power_8_9",
         "pv_power_limit": "number.solax_remotecontrol_pv_power_limit", "max_pv_w": 30000}
RANGE = {"number.solax_remotecontrol_push_mode_power_8_9": {"unit_of_measurement": "W", "min": -30000, "max": 30000},
         "number.solax_remotecontrol_pv_power_limit": {"unit_of_measurement": "W", "min": 0, "max": 30000}}


def _variables(blueprint, battery_on, limit_on, setpoint=0, limit=0):
    states = {NAMES["ems_take_control"]: "on" if battery_on else "off", NAMES["ems_limit_control"]: "on" if limit_on else "off",
              NAMES["ems_setpoint"]: setpoint, NAMES["ems_power_limit"]: limit}
    environment = _env(states, RANGE)
    variables = blueprint["variables"]
    control = environment.from_string(variables["control"]).render(**NAMES).strip()
    context = {**NAMES, "control": control}
    return (control, environment.from_string(variables["target_push"]).render(**context).strip(),
            environment.from_string(variables["target_pv_limit"]).render(**context).strip())


@pytest.mark.parametrize("battery_on, limit_on, setpoint, limit, expected", [
    (True, True, -3000, 4000, ("battery", "-3000", "4000")),     # charge 3 kW, PV capped at 4 kW
    (True, False, 2500, 0, ("battery", "2500", "30000")),        # discharge, no limit: the maximum PV
    (False, True, -3000, 1500, ("limit", "0", "1500")),          # only the limit: grid target 0, PV capped
    (False, False, -3000, 1500, ("off", "0", "30000")),
])
def test_the_three_situations(blueprint, battery_on, limit_on, setpoint, limit, expected):
    assert _variables(blueprint, battery_on, limit_on, setpoint, limit) == expected


def test_values_stay_inside_the_entity_ranges(blueprint):
    assert _variables(blueprint, True, True, -50000, 99999)[1:] == ("-30000", "30000")
    assert _variables(blueprint, True, True, 0, -500)[2] == "0"
    assert _variables(blueprint, True, False, "unavailable", 0)[1] == "0"     # no setpoint → nothing


def test_entities_and_defaults(blueprint):
    inputs = blueprint["blueprint"]["input"]
    for name, domain in (("ems_take_control", "switch"), ("ems_setpoint", "number"),
                         ("ems_limit_control", "switch"), ("ems_power_limit", "number")):
        assert inputs[name]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": domain}
    assert inputs["power_control_mode"]["default"] == "select.solax_remotecontrol_power_control_mode"
    assert inputs["pv_power_limit"]["default"] == "number.solax_remotecontrol_pv_power_limit"
    assert inputs["push_power"]["default"] == "number.solax_remotecontrol_push_mode_power_8_9"
    assert inputs["trigger_button"]["default"] == "button.solax_powercontrolmode8_trigger"
    assert inputs["option_battery"]["default"] == "Mode 8 - PV and BAT control - Duration"
    assert inputs["option_limit"]["default"] == "Enabled Grid Control"
    assert inputs["option_released"]["default"] == "Disabled"


def test_controlled_writes_everything_and_triggers_every_5_seconds(blueprint):
    assert {"trigger": "time_pattern", "seconds": "/5"} in blueprint["triggers"]
    steps = blueprint["actions"][0]["choose"][0]["sequence"]
    targets = [(step.get("action"), str((step.get("target") or {}).get("entity_id"))) for step in steps]
    assert targets[:4] == [("number.set_value", "autorepeat_duration"), ("number.set_value", "import_limit"),
                           ("number.set_value", "pv_power_limit"), ("number.set_value", "push_power")]
    choice = steps[4]
    assert str(choice["then"][0]["data"]["option"]) == "option_battery" and str(choice["else"][0]["data"]["option"]) == "option_limit"
    assert targets[5] == ("button.press", "trigger_button")


def test_released_once_gives_the_inverter_its_own_mode(blueprint):
    branch = blueprint["actions"][0]["choose"][1]
    assert "option_released" in branch["conditions"][0]["value_template"]      # only while not yet released
    steps = branch["sequence"]
    assert steps[0]["data"]["value"] == 0 and str(steps[1]["data"]["option"]) == "option_released"
