"""Unit tests for fetch_hf_schema response-shape handling.

The HF dataset-viewer /info endpoint returns two different shapes:

- Without a config filter, ``dataset_info`` is keyed by config name, e.g.
  ``{"default": {"features": {...}}}``.
- With a ``config`` filter, ``dataset_info`` is that config's info dict
  *directly* (features at the top level, alongside string fields like
  ``description``). Iterating ``.values()`` there yields strings, which used
  to crash with ``AttributeError: 'str' object has no attribute 'get'``.
"""

from __future__ import annotations

from typing import Any

import inspect_dataset._view.discovery as discovery

_FEATURES = {
    "question": {"_type": "Value", "dtype": "string"},
    "answer": {"_type": "Value", "dtype": "string"},
    "n_choices": {"_type": "Value", "dtype": "int64"},
}


def _patch_response(monkeypatch: Any, payload: dict[str, Any] | None) -> None:
    monkeypatch.setattr(discovery, "_hf_request", lambda _path: payload)


def _names_and_types(schema: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(f["name"], f["type"]) for f in schema}


def test_schema_keyed_by_config(monkeypatch):
    """Shape returned when no config filter is applied."""
    _patch_response(monkeypatch, {"dataset_info": {"default": {"features": _FEATURES}}})
    schema = discovery.fetch_hf_schema("some/dataset")
    assert schema is not None
    assert _names_and_types(schema) == {
        ("question", "str"),
        ("answer", "str"),
        ("n_choices", "int"),
    }


def test_schema_config_direct_shape(monkeypatch):
    """Regression: config-filtered response puts features at the top level."""
    _patch_response(
        monkeypatch,
        {
            "dataset_info": {
                "description": "a long description string",
                "citation": "",
                "config_name": "default",
                "features": _FEATURES,
            }
        },
    )
    schema = discovery.fetch_hf_schema("some/dataset", config="default")
    assert schema is not None
    assert _names_and_types(schema) == {
        ("question", "str"),
        ("answer", "str"),
        ("n_choices", "int"),
    }


def test_schema_prefers_requested_config(monkeypatch):
    """When keyed by config, the requested config wins over others."""
    other = {"only": {"_type": "Value", "dtype": "string"}}
    _patch_response(
        monkeypatch,
        {
            "dataset_info": {
                "other": {"features": other},
                "wanted": {"features": _FEATURES},
            }
        },
    )
    schema = discovery.fetch_hf_schema("some/dataset", config="wanted")
    assert schema is not None
    assert _names_and_types(schema) == {
        ("question", "str"),
        ("answer", "str"),
        ("n_choices", "int"),
    }


def test_schema_none_when_api_unavailable(monkeypatch):
    _patch_response(monkeypatch, None)
    assert discovery.fetch_hf_schema("some/dataset") is None


def test_schema_none_when_no_dataset_info(monkeypatch):
    _patch_response(monkeypatch, {"dataset_info": {}})
    assert discovery.fetch_hf_schema("some/dataset") is None


# ── fetch_hf_configs ────────────────────────────────────────────────────────


def test_configs_returns_sorted_names(monkeypatch):
    _patch_response(
        monkeypatch,
        {"dataset_info": {"zeta": {}, "alpha": {}, "mu": {}}},
    )
    assert discovery.fetch_hf_configs("some/dataset") == ["alpha", "mu", "zeta"]


def test_configs_none_when_api_unavailable(monkeypatch):
    _patch_response(monkeypatch, None)
    assert discovery.fetch_hf_configs("some/dataset") is None


def test_configs_none_when_empty(monkeypatch):
    _patch_response(monkeypatch, {"dataset_info": {}})
    assert discovery.fetch_hf_configs("some/dataset") is None
