"""Shared helpers: load a blueprint like Home Assistant does (with its !input tag)."""
import glob
import os
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

BLUEPRINTS = sorted(glob.glob(os.path.join(ROOT, "blueprints", "*", "*.yaml")))


class InputTag(str):
    """The value of `!input name`: the input's name."""


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor("!input", lambda loader, node: InputTag(loader.construct_scalar(node)))


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=BlueprintLoader)


def blueprint_path(folder, name):
    return os.path.join(ROOT, "blueprints", folder, name)


@pytest.fixture
def load_blueprint():
    return lambda folder, name: load(blueprint_path(folder, name))
