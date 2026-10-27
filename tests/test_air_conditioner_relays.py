"""The air conditioner blueprint: while Ventra-EMS has control, each device switch
follows its Ventra-EMS relay (heating, cooling: an air conditioner has no main relay) and its optional extra conditions."""
import jinja2
import pytest

from conftest import blueprint_path, declared_inputs, load

RELAYS = ("heating", "cooling")


@pytest.fixture(scope="module")
def blueprint():
    return load(blueprint_path("air_conditioner", "air_conditioner_relays.yaml"))


def test_one_section_per_relay_with_optional_inputs(blueprint):
    """Ventra-EMS's entities for an air conditioner `airco`: switch.ems_airco_take_control
    and switch.ems_airco_<mode>_relay (the add-on's control_entities.air_conditioner)."""
    sections = blueprint["blueprint"]["input"]
    assert set(sections) == {"ems_take_control", *RELAYS}
    inputs = declared_inputs(blueprint["blueprint"])
    assert inputs["ems_take_control"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    for relay in RELAYS:
        assert inputs[f"ems_{relay}_relay"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
        assert f"switch.ems_airco_{relay}_relay" in inputs[f"ems_{relay}_relay"]["description"]
        assert inputs[f"ems_{relay}_relay"]["default"] == "" and inputs[f"{relay}_switch"]["default"] == ""
        assert inputs[f"{relay}_conditions"] == {**inputs[f"{relay}_conditions"], "default": [], "selector": {"condition": {}}}


def test_acts_only_while_ventra_ems_has_control(blueprint):
    assert blueprint["conditions"] == [{"condition": "template", "value_template": "{{ is_state(ems_take_control, 'on') }}"}]
    assert {"trigger": "time_pattern", "seconds": "/5"} in blueprint["triggers"]


@pytest.mark.parametrize("index, relay", list(enumerate(RELAYS)))
def test_each_relay_follows_its_own_relay_and_extra_conditions(blueprint, index, relay):
    block = blueprint["actions"][index]
    assert f"ems_{relay}_relay != ''" in block["if"][0]["value_template"]
    inner = block["then"][0]
    assert inner["if"][0]["value_template"] == f"{{{{ is_state(ems_{relay}_relay, 'on') }}}}"
    assert inner["if"][1] == {"condition": "and", "conditions": f"{relay}_conditions"}       # the !input
    assert inner["then"][0]["then"][0]["action"] == "homeassistant.turn_on"
    assert inner["else"][0]["then"][0]["action"] == "homeassistant.turn_off"
    assert inner["then"][0]["then"][0]["target"]["entity_id"] == f"{{{{ {relay}_switch }}}}"


def _used(blueprint, relay, ems_state, ems_entity="switch.ems_airco_heating_relay", device="switch.airco_heating"):
    """The first check of a relay block, rendered like HA would."""
    environment = jinja2.Environment()
    environment.globals["states"] = lambda entity_id: ems_state if entity_id == ems_entity else "unknown"
    template = blueprint["actions"][RELAYS.index(relay)]["if"][0]["value_template"]
    return environment.from_string(template).render(**{f"ems_{relay}_relay": ems_entity, f"{relay}_switch": device}).strip()


def test_an_unused_or_unclear_relay_is_skipped(blueprint):
    assert _used(blueprint, "heating", "on") == "True"
    assert _used(blueprint, "heating", "unavailable") == "False"
    assert _used(blueprint, "heating", "on", ems_entity="") == "False"
    assert _used(blueprint, "heating", "on", device="") == "False"


def test_heat_pump_and_air_conditioner_each_have_their_own():
    import build_index
    index, _ = build_index.build()
    kinds = {entry["id"]: entry["device_types"] for entry in index["blueprints"]}
    assert kinds["air_conditioner_relays"] == ["air_conditioner"] and kinds["heatpump_relays"] == ["heatpump"]
