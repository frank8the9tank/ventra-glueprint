# CLAUDE.md — ventra-blueprints

Home Assistant blueprints ("glue" automations) for Ventra-EMS, separate from the add-on so they can
change, be tested and be updated on their own. **Private for now**; once public the add-on downloads
them from this repo (raw GitHub URLs of `index.json` and the files). See README.md.

Project documentation lives in `ventra-docs` (`../ventra-docs/`): `SYSTEM.md` (repos),
`DEVELOPMENT.md` § 4b (blueprints), `DEVICES.md` (device kinds, entity names).

## Always

- **Raise `# ventra-ems-blueprint-version` on every change** and end the description with `Version N.`
- **Never break an existing input**; an incompatible blueprint gets a new file name.
- Keep the header complete: device types, brand, `min-version`, `max-version` (empty = no limit).
  Set `max-version` only when a Ventra-EMS change breaks the blueprint.
- After a change run `python tools/build_index.py` and commit `index.json` with it.
- Every blueprint has its own test file in `tests/`.
- Entity names and units follow the add-on (`control_entities.py`, setpoints in W). When the add-on
  changes them, check every blueprint here and set `max-version` / make a new file where needed.

## Commands

```bash
uv run --no-project --python 3.11 --with-requirements requirements-dev.txt pytest tests -q
uv run --no-project --python 3.11 python tools/build_index.py --check
```

Commit and push after every agreed change; the commit subject says what changed for users.
