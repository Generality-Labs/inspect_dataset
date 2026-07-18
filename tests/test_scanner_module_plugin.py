import sys
import textwrap

import click
import pytest

from inspect_dataset.cli import _load_scanner_module

PLUGIN = textwrap.dedent(
    """
    from inspect_dataset._types import Finding
    from inspect_dataset.scanner import ScannerDef

    def _scan(records, fields):
        return []

    my_check = ScannerDef(name="my_check", fn=_scan, description="test scanner")
    other = ScannerDef(name="other", fn=_scan, description="not declared")
    SCANNERS = [my_check]
    """
)


@pytest.fixture
def plugin_on_path(tmp_path):
    (tmp_path / "my_audit_plugin.py").write_text(PLUGIN)
    sys.path.insert(0, str(tmp_path))
    yield
    sys.path.remove(str(tmp_path))
    sys.modules.pop("my_audit_plugin", None)


def test_declared_scanners_list_takes_precedence(plugin_on_path):
    defs = _load_scanner_module("my_audit_plugin")
    assert [s.name for s in defs] == ["my_check"]


def test_attribute_scan_when_no_scanners_list(tmp_path):
    (tmp_path / "attr_plugin.py").write_text(
        PLUGIN.replace("SCANNERS = [my_check]", "")
    )
    sys.path.insert(0, str(tmp_path))
    try:
        defs = _load_scanner_module("attr_plugin")
        assert {s.name for s in defs} == {"my_check", "other"}
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("attr_plugin", None)


def test_missing_module_raises_bad_parameter():
    with pytest.raises(click.BadParameter, match="Could not import"):
        _load_scanner_module("definitely_not_a_module_xyz")


def test_module_without_scanners_raises(tmp_path):
    (tmp_path / "empty_plugin.py").write_text("X = 1\n")
    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(click.BadParameter, match="No ScannerDef"):
            _load_scanner_module("empty_plugin")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("empty_plugin", None)
