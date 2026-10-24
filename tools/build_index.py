"""
build_index.py — read the header of every blueprint and write the catalogue (index.json) that the
Ventra-EMS add-on reads to offer, install and update blueprints.

    python tools/build_index.py           # write index.json
    python tools/build_index.py --check   # exit 1 when index.json is out of date or a header is wrong

Every blueprint starts with these comment lines (see README.md):

    # ventra-ems-blueprint-version: 2
    # ventra-ems-device-types: relay_load, heatpump, air_conditioner
    # ventra-ems-brand: Solax                (empty for a generic blueprint)
    # ventra-ems-min-version: 1.0.561
    # ventra-ems-max-version:                (empty = no upper limit)

The index has no timestamps, so it only changes when a blueprint changes.
"""

import glob
import hashlib
import json
import os
import re
import sys

import yaml

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLUEPRINTS = os.path.join(ROOT, "blueprints")
INDEX      = os.path.join(ROOT, "index.json")

# The Ventra-EMS device kinds a blueprint can be for (config_schema.iter_devices in the add-on)
DEVICE_TYPES  = ("inverter", "battery", "ev_charger", "heatpump", "relay_load", "air_conditioner", "grid_controller")
HEADER        = re.compile(r"^#\s*ventra-ems-([a-z-]+):[ \t]*(.*?)\s*$", re.M)
VERSION       = re.compile(r"^\d+(\.\d+)*$")
INDEX_VERSION = 1   # the format of index.json; raise it on an incompatible change
ENTITY_PREFIX = "ems_"   # inputs named ems_<role> are Ventra-EMS entities the add-on fills in (README)


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: {"input": loader.construct_scalar(node)})


def read_inputs(blueprint: dict) -> list:
    """The inputs in order, also inside input sections: name, section, title, description,
    default (when there is one), selector, and the Ventra-EMS role for ems_<role> inputs."""
    inputs = []

    def add(name, item, section):
        entry = {"name": name, "section": section, "title": item.get("name", name),
                 "description": " ".join(str(item.get("description", "")).split()),
                 "selector": item.get("selector") or {}}
        if "default" in item:
            entry["default"] = item["default"]
        if name.startswith(ENTITY_PREFIX):
            entry["ems_role"] = name[len(ENTITY_PREFIX):]
        inputs.append(entry)

    for name, item in (blueprint.get("input") or {}).items():
        if isinstance(item, dict) and "input" in item:
            for inner, inner_item in item["input"].items():
                add(inner, inner_item, item.get("name", name))
        else:
            add(name, item or {}, None)
    return inputs


def ems_version(text: str) -> tuple:
    """"1.0.462.2" → (1, 0, 462, 2), compared as numbers."""
    return tuple(int(part) for part in text.split("."))


def read_header(path: str) -> dict:
    """The ventra-ems-* header lines of a blueprint (only the comment block at the top)."""
    with open(path, encoding="utf-8") as f:
        top = "".join(line for line in f if line.startswith("#"))
    return {key: value for key, value in HEADER.findall(top)}


def entry_for(path: str) -> tuple:
    """(index entry, problems) for one blueprint file."""
    relative = os.path.relpath(path, ROOT).replace(os.sep, "/")
    header   = read_header(path)
    problems = []
    version  = header.get("blueprint-version", "")
    if not version.isdigit() or int(version) < 1:
        problems.append(f"{relative}: ventra-ems-blueprint-version must be a whole number ≥ 1")
    types = [item.strip() for item in header.get("device-types", "").split(",") if item.strip()]
    if not types or any(item not in DEVICE_TYPES for item in types):
        problems.append(f"{relative}: ventra-ems-device-types must list some of {', '.join(DEVICE_TYPES)}")
    minimum, maximum = header.get("min-version", ""), header.get("max-version", "")
    if not VERSION.match(minimum):
        problems.append(f"{relative}: ventra-ems-min-version must be a version like 1.0.561")
    if maximum and not VERSION.match(maximum):
        problems.append(f"{relative}: ventra-ems-max-version must be a version like 1.0.600 or empty")
    if not problems and maximum and ems_version(maximum) < ems_version(minimum):
        problems.append(f"{relative}: ventra-ems-max-version is below ventra-ems-min-version")
    with open(path, "rb") as f:
        raw = f.read()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        blueprint = (yaml.load(raw.decode("utf-8"), Loader=_Loader) or {}).get("blueprint") or {}
    except yaml.YAMLError as error:
        blueprint = {}
        problems.append(f"{relative}: not valid YAML ({error})")
    entry = {
        "id":              os.path.splitext(os.path.basename(path))[0],
        "path":            relative,
        "name":            blueprint.get("name", ""),
        "description":     " ".join(str(blueprint.get("description", "")).split()),
        "version":         int(version) if version.isdigit() else 0,
        "device_types":    types,
        "brand":           header.get("brand", ""),
        "min_ems_version": minimum,
        "max_ems_version": maximum or None,
        "sha256":          digest,
        "inputs":          read_inputs(blueprint),
    }
    return entry, problems


def build() -> tuple:
    """(index, problems) for all blueprints."""
    entries, problems = [], []
    for path in sorted(glob.glob(os.path.join(BLUEPRINTS, "*", "*.yaml"))):
        entry, found = entry_for(path)
        entries.append(entry)
        problems.extend(found)
    ids = [entry["id"] for entry in entries]
    for duplicate in sorted({item for item in ids if ids.count(item) > 1}):
        problems.append(f"blueprint id '{duplicate}' is used more than once (the file name must be unique)")
    return {"index_version": INDEX_VERSION, "blueprints": entries}, problems


def render(index: dict) -> str:
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def main(argv) -> int:
    index, problems = build()
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    if problems:
        return 1
    text = render(index)
    if "--check" in argv:
        current = open(INDEX, encoding="utf-8").read() if os.path.exists(INDEX) else ""
        if current != text:
            print("ERROR: index.json is out of date: run python tools/build_index.py", file=sys.stderr)
            return 1
        return 0
    with open(INDEX, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"index.json: {len(index['blueprints'])} blueprints")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
