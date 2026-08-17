"""Regression tests for section-3 (``providers:``) same-endpoint grouping in
``list_authenticated_providers`` and for ``format_model_for_display``.

Salvaged with PR #36998 (@antydizajn): section 3 folds ``providers:`` entries
that share (api_url, credential, api_mode, extra_headers) into one picker row,
mirroring section 4's grouping for ``custom_providers:``. An explicit
``provider_key`` preserves routing identity. These are invariant tests —
grouping identity, identity/header-routed separation, list-of-dict model
declarations, and display-only RID stripping.
"""

import hermes_cli.providers as providers_mod
from hermes_cli.model_switch import (
    format_model_for_display,
    list_authenticated_providers,
)


def _providers(monkeypatch, user_providers):
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr(providers_mod, "HERMES_OVERLAYS", {})
    monkeypatch.setattr("hermes_cli.models.fetch_api_models", lambda *a, **k: [])
    return list_authenticated_providers(
        user_providers=user_providers,
        custom_providers=[],
        max_models=50,
    )


def _user_rows(rows):
    return [p for p in rows if p.get("source") == "user-config"]


def test_same_endpoint_same_credential_entries_fold_to_one_row(monkeypatch):
    """Two providers: entries differing only by model id collapse into one
    picker row carrying both models (the Palantir Foundry case)."""
    rows = _user_rows(_providers(monkeypatch, {
        "palantir-claude46": {
            "name": "Palantir Claude 4.6 Opus",
            "base_url": "https://foundry.example.com/anthropic",
            "key_env": "PALANTIR_TOKEN",
            "api_mode": "anthropic_messages",
            "model": "ri.language-model-service..language-model.anthropic-claude-4-6-opus",
        },
        "palantir-claude47": {
            "name": "Palantir Claude 4.7 Opus",
            "base_url": "https://foundry.example.com/anthropic",
            "key_env": "PALANTIR_TOKEN",
            "api_mode": "anthropic_messages",
            "model": "ri.language-model-service..language-model.anthropic-claude-4-7-opus",
        },
    }))
    assert len(rows) == 1
    row = rows[0]
    assert row["slug"] == "palantir-claude46"  # first member's slug wins
    assert row["name"] == "Palantir Claude"    # version suffix stripped
    assert len(row["models"]) == 2


def test_different_extra_headers_keep_distinct_rows(monkeypatch):
    """Header-routed tenants behind one proxy URL are distinct endpoints —
    extra_headers is part of the group identity (mirrors section 4)."""
    rows = _user_rows(_providers(monkeypatch, {
        "tenant-a": {
            "name": "Tenant A",
            "base_url": "https://proxy.example.com/v1",
            "key_env": "PROXY_TOKEN",
            "api_mode": "openai_chat",
            "extra_headers": {"X-Tenant": "a"},
            "model": "model-a",
        },
        "tenant-b": {
            "name": "Tenant B",
            "base_url": "https://proxy.example.com/v1",
            "key_env": "PROXY_TOKEN",
            "api_mode": "openai_chat",
            "extra_headers": {"X-Tenant": "b"},
            "model": "model-b",
        },
    }))
    assert len(rows) == 2


def test_explicit_provider_keys_keep_same_endpoint_models_distinct(monkeypatch):
    """Stable provider identities must not inherit the first row's name.

    Desktop-managed enterprise models share one relay URL and credential but
    use provider_key for exact model-to-provider round trips.
    """
    rows = _user_rows(_providers(monkeypatch, {
        "custom:team-model-a": {
            "provider_key": "custom:team-model-a",
            "name": "team-model-a",
            "base_url": "https://team.example.com/v1",
            "api_key": "shared-token",
            "api_mode": "openai_chat",
            "model": "opaque-model-a",
        },
        "custom:team-model-b": {
            "provider_key": "custom:team-model-b",
            "name": "team-model-b",
            "base_url": "https://team.example.com/v1",
            "api_key": "shared-token",
            "api_mode": "openai_chat",
            "model": "opaque-model-b",
        },
    }))

    assert [(row["slug"], row["name"], row["models"]) for row in rows] == [
        ("custom:team-model-a", "team-model-a", ["opaque-model-a"]),
        ("custom:team-model-b", "team-model-b", ["opaque-model-b"]),
    ]


class TestFormatModelForDisplay:
    def test_palantir_rid_stripped_to_trailing_slug(self):
        rid = "ri.language-model-service..language-model.anthropic-claude-4-7-opus"
        assert format_model_for_display(rid) == "anthropic-claude-4-7-opus"


