"""Offline unit tests for the lynx wrapper."""
import subprocess
from unittest import mock

from lynx.lynx import lynx_url


def test_lynx_url_uses_system_config_and_flags():
    with mock.patch("lynx.lynx.subprocess.run") as run:
        run.return_value.stdout = "page text"
        out = lynx_url("https://example.com")

    assert out == "page text"
    argv = run.call_args.args[0]
    assert argv[0].endswith("lynx")
    assert "-dump" in argv
    assert "-accept_all_cookies" in argv
    # A custom -cfg would replace the system config wholesale and break HTTPS.
    assert not any(a.startswith("-cfg") for a in argv)
    assert argv[-1] == "https://example.com"


def test_lynx_url_wraps_failures_in_runtime_error():
    with mock.patch("lynx.lynx.subprocess.run") as run:
        run.side_effect = subprocess.CalledProcessError(1, "lynx")
        try:
            lynx_url("https://example.com")
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError")
