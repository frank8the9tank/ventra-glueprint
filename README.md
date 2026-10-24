# Ventra-EMS glueprints

Home Assistant blueprints for the "glue" automations of [Ventra-EMS](https://ventra-ems.com) — glueprints. Ventra-EMS
never talks to hardware: for every device it writes a **take control** switch and a **setpoint**
(or a relay) in Home Assistant. A glue automation, made from one of these blueprints, passes that on
to the device's own integration (Solax Modbus, a smart plug, an OCPP charger, …).

Using a blueprint is optional: any automation that follows the rule below works.

The Ventra-EMS add-on reads `index.json` and the blueprint files straight from this repository
(raw GitHub URLs), offers the ones that fit a device and its Ventra-EMS version, installs them into
Home Assistant and keeps them up to date. You can also import one by hand: in Home Assistant,
*Settings → Automations & scenes → Blueprints → Import blueprint* with the file's GitHub URL.

## Layout

```
blueprints/<device type>/<id>.yaml   one blueprint (the file name is its id, unique over all folders)
index.json                           the catalogue the add-on reads (generated, committed)
tools/build_index.py                 builds and checks index.json
tests/                               pytest: every blueprint, plus one test file per blueprint
```

| Blueprint | For | Version |
|---|---|---|
| `battery/solax_battery.yaml` | A battery behind a Solax inverter (Solax Modbus remote control) | 1 |
| `ev_charger/ocpp_ev_charger.yaml` | An EV charger in the OCPP integration (lbbrhzn/ocpp): power → charging current + charge control | 1 |
| `heatpump/heatpump_relays.yaml` | A heat pump or air conditioner with relays (main, heating, cooling, hot water), each with optional extra conditions of your own | 1 |
| `relay_device/relay_device.yaml` | A relay device, heat pump or AC relay switched by a switch / smart plug | 2 |

## The rule every glue follows

`switch.ems_<id>_take_control` says whether Ventra-EMS controls the device.

- **On:** the device follows the Ventra-EMS output: the relay (`switch.ems_<id>_relay`, …) or the
  setpoint (`number.ems_<id>_battery_power`, … in **W**: − = charge / consume, + = discharge).
- **Off:** Ventra-EMS doesn't control the device. A relay device is left alone; a battery is handed
  back to its own mode; an EV charger stops charging (Ventra-EMS's rules decide when it charges).
- Check on every change of take control and the output, and every 5 seconds (OCPP chargers every
  15 seconds: each command takes time).

## The header: version and compatibility

Every blueprint starts with:

```yaml
# ventra-ems-blueprint-version: 2
# ventra-ems-device-types: relay_load, heatpump, air_conditioner
# ventra-ems-brand: Solax
# ventra-ems-min-version: 1.0.561
# ventra-ems-max-version:
```

| Line | Meaning |
|---|---|
| `blueprint-version` | Whole number. **Raise it on every change**: installed systems update only to a higher version. Also end the description with `Version N.` |
| `device-types` | The Ventra-EMS device kinds it is for: `inverter`, `battery`, `ev_charger`, `heatpump`, `relay_load`, `air_conditioner`, `grid_controller` |
| `brand` | The brand it is made for; empty for a generic blueprint |
| `min-version` | The oldest Ventra-EMS version it works with (it needs the entities and units of that version) |
| `max-version` | The newest Ventra-EMS version it works with; **empty = no upper limit**. Set it only when a Ventra-EMS change breaks this blueprint |

Versions compare as numbers (`1.0.462.2` > `1.0.462`). The add-on offers a blueprint only when its own
version is inside the range, and replaces an installed one automatically with a higher compatible
version.

## Rules for changes

- **Never break an existing input** (rename, remove, change its meaning): every automation made
  from the blueprint follows the new file. An incompatible version gets a new file name (`…_v2.yaml`).
- The name starts with "Ventra-EMS"; the description says what to pick and ends with the version.
  Inputs use selectors; the Ventra-EMS entities are filtered on `integration: ventra_ems`.
- After a change: raise the version, run `python tools/build_index.py`, run the tests, commit
  `index.json` with the blueprint.
- Batteries: one blueprint per brand; the brand's entities default to its integration's names.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests -q
python tools/build_index.py --check
```

Templates are rendered with `jinja2` and Home Assistant's `states()` / `state_attr()` stubbed
(see `tests/test_solax_battery.py`). CI runs the same on every push.
