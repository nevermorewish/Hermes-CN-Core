"""Tests for the refactored shell-resolution logic in ``tools/environments/local.py``.

Covers ``_find_bash()``, ``_find_pwsh_simple()``, and ``_resolve_shell()`` after
the Windows auto-install logic for Git / pwsh was removed.
"""

import contextlib
import os
from pathlib import Path
from unittest import mock

import pytest

from tools.environments.local import _find_bash, _find_pwsh_simple, _resolve_shell


@contextlib.contextmanager
def _whitelist_fs(*allowed_paths):
    """Make ``os.path.isfile`` and ``Path.exists`` truthy only for *allowed_paths*."""
    allowed = {os.path.normcase(str(p)) for p in allowed_paths}

    def _isfile(path):
        return os.path.normcase(str(path)) in allowed

    def _exists(_self):
        return os.path.normcase(str(_self)) in allowed

    with mock.patch("os.path.isfile", _isfile), mock.patch("pathlib.Path.exists", _exists):
        yield


def _disable_winreg(monkeypatch):
    """Disable the registry strategy so tests don't see the host Git install."""
    import sys
    import types

    fake = types.ModuleType("winreg")
    fake.HKEY_LOCAL_MACHINE = 0
    fake.HKEY_CURRENT_USER = 0

    def _open(*_args, **_kwargs):
        raise FileNotFoundError

    fake.OpenKey = _open
    monkeypatch.setitem(sys.modules, "winreg", fake)


class TestFindBash:
    def test_non_windows_returns_bash_or_fallback(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", False)
        with mock.patch("shutil.which", return_value="/usr/bin/bash"):
            assert _find_bash() == "/usr/bin/bash"

    def test_non_windows_falls_back_to_sensible_defaults(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", False)
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("os.path.isfile", return_value=False):
                with mock.patch.dict(os.environ, {}, clear=True):
                    assert _find_bash() == "/bin/sh"

    def test_windows_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        bash_exe = tmp_path / "my" / "bash.exe"
        bash_exe.parent.mkdir(parents=True)
        bash_exe.write_text("")
        with _whitelist_fs(bash_exe):
            with mock.patch.dict(os.environ, {"HERMES_GIT_BASH_PATH": str(bash_exe)}, clear=True):
                assert _find_bash() == str(bash_exe)

    def test_windows_legacy_portable_git(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        local_appdata = tmp_path / "appdata" / "local"
        local_appdata.mkdir(parents=True)
        legacy_bash = local_appdata / "hermes" / "git" / "bin" / "bash.exe"
        legacy_bash.parent.mkdir(parents=True)
        legacy_bash.write_text("")
        env = {"LOCALAPPDATA": str(local_appdata)}
        with _whitelist_fs(legacy_bash):
            with mock.patch.dict(os.environ, env, clear=True):
                assert _find_bash() == str(legacy_bash)

    def test_windows_derives_from_git_exe(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        git_root = tmp_path / "git"
        git_exe = git_root / "cmd" / "git.exe"
        bash_exe = git_root / "bin" / "bash.exe"
        git_exe.parent.mkdir(parents=True)
        bash_exe.parent.mkdir(parents=True)
        git_exe.write_text("")
        bash_exe.write_text("")
        with _whitelist_fs(git_exe, bash_exe):
            with mock.patch("shutil.which", return_value=str(git_exe)):
                with mock.patch.dict(os.environ, {}, clear=True):
                    assert _find_bash() == str(bash_exe)

    def test_windows_rejects_wsl_launcher(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        system_root = tmp_path / "Windows"
        wsl_bash = system_root / "System32" / "bash.exe"
        wsl_bash.parent.mkdir(parents=True)
        wsl_bash.write_text("")
        real_bash = tmp_path / "Git" / "bin" / "bash.exe"
        real_bash.parent.mkdir(parents=True)
        real_bash.write_text("")

        with mock.patch("shutil.which", side_effect=[None, str(wsl_bash), str(wsl_bash)]):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError):
                with mock.patch("os.path.realpath", lambda p, strict=False: p):
                    with _whitelist_fs(wsl_bash, real_bash):
                        with mock.patch.dict(
                            os.environ,
                            {
                                "SystemRoot": str(system_root),
                                "ProgramFiles": str(tmp_path),
                                "USERPROFILE": str(tmp_path),
                            },
                            clear=True,
                        ):
                            assert _find_bash() == str(real_bash)

    def test_windows_missing_raises_with_manual_install_message(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        with mock.patch("shutil.which", return_value=None):
            with mock.patch("subprocess.run", side_effect=FileNotFoundError):
                with _whitelist_fs():
                    with mock.patch.dict(
                        os.environ, {"USERPROFILE": str(tmp_path)}, clear=True
                    ):
                        with pytest.raises(RuntimeError, match="Install Git for Windows"):
                            _find_bash()


class TestFindPwshSimple:
    def test_non_windows_returns_none(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", False)
        assert _find_pwsh_simple() is None

    def test_windows_returns_pwsh_from_path(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        with mock.patch("shutil.which", side_effect=[r"C:\pwsh\pwsh.exe", None]):
            assert _find_pwsh_simple() == r"C:\pwsh\pwsh.exe"

    def test_windows_falls_back_to_pwsh_exe(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        with mock.patch("shutil.which", side_effect=[None, r"C:\pwsh\pwsh.exe"]):
            assert _find_pwsh_simple() == r"C:\pwsh\pwsh.exe"

    def test_windows_missing_returns_none(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        with mock.patch("shutil.which", return_value=None):
            assert _find_pwsh_simple() is None


class TestResolveShell:
    def test_windows_pwsh_explicit_missing_raises(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        with mock.patch.dict(os.environ, {"HERMES_SHELL_TYPE": "pwsh"}, clear=True):
            with _whitelist_fs():
                with mock.patch("shutil.which", return_value=None):
                    with pytest.raises(RuntimeError, match="HERMES_SHELL_TYPE=pwsh"):
                        _resolve_shell()

    def test_windows_auto_with_pwsh_returns_pwsh(self, monkeypatch):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        env = {"HERMES_SHELL_TYPE": "auto"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("shutil.which", return_value=r"C:\pwsh.exe"):
                with _whitelist_fs(r"C:\pwsh.exe"):
                    assert _resolve_shell() == ("pwsh", r"C:\pwsh.exe")

    def test_windows_auto_without_pwsh_falls_back_to_bash(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        bash_exe = tmp_path / "Git" / "bin" / "bash.exe"
        bash_exe.parent.mkdir(parents=True)
        bash_exe.write_text("")
        env = {"HERMES_SHELL_TYPE": "auto", "ProgramFiles": str(tmp_path)}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("shutil.which", return_value=None):
                with _whitelist_fs(bash_exe):
                    assert _resolve_shell() == ("bash", str(bash_exe))

    def test_windows_explicit_pwsh_path_wins(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        explicit = tmp_path / "custom" / "pwsh.exe"
        explicit.parent.mkdir(parents=True)
        explicit.write_text("")
        env = {"HERMES_SHELL_TYPE": "auto", "HERMES_PWSH_PATH": str(explicit)}
        with mock.patch.dict(os.environ, env, clear=True):
            with _whitelist_fs(explicit):
                assert _resolve_shell() == ("pwsh", str(explicit))

    def test_windows_explicit_bash_path_wins(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", True)
        _disable_winreg(monkeypatch)
        explicit = tmp_path / "custom" / "bash.exe"
        explicit.parent.mkdir(parents=True)
        explicit.write_text("")
        env = {"HERMES_GIT_BASH_PATH": str(explicit)}
        with mock.patch.dict(os.environ, env, clear=True):
            with _whitelist_fs(explicit):
                assert _resolve_shell() == ("bash", str(explicit))

    def test_non_windows_always_bash(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tools.environments.local._IS_WINDOWS", False)
        bash_exe = tmp_path / "bash"
        bash_exe.write_text("")
        with mock.patch("shutil.which", return_value=str(bash_exe)):
            with mock.patch.dict(os.environ, {}, clear=True):
                assert _resolve_shell() == ("bash", str(bash_exe))
