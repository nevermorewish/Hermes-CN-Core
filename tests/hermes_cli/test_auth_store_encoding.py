from pathlib import Path

import orjson


def test_load_auth_store_does_not_use_locale_text_decoding(tmp_path, monkeypatch):
    from hermes_cli.auth import _load_auth_store

    auth_file = tmp_path / "auth.json"
    expected = {
        "version": 1,
        "providers": {},
        "credential_pool": {"custom:gpt软件研发": [{"label": "企业模型"}]},
    }
    auth_file.write_bytes(orjson.dumps(expected))

    def reject_locale_read(*_args, **_kwargs):
        raise AssertionError("auth.json must be parsed from UTF-8 bytes")

    monkeypatch.setattr(Path, "read_text", reject_locale_read)

    assert _load_auth_store(auth_file) == expected
    assert not auth_file.with_suffix(".json.corrupt").exists()
