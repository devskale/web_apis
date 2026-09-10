"""Offline unit tests for the lynx wrapper."""
import subprocess
from unittest import mock

from lynx.lynx import lynx_url


def test_lynx_url_keeps_cfg_as_single_flag():
    with mock.patch("lynx.lynx.subprocess.run") as run:
        run.return_value.stdout = "page text"
        out = lynx_url("https://example.com")

    assert out == "page text"
    argv = run.call_args.args[0]
    assert argv[0].endswith("lynx")
    assert "-dump" in argv
    # '-cfg=PATH' must be one argv token; split tokens make lynx treat the
    # path as a startfile and the config is silently ignored.
    assert sum(a.startswith("-cfg=") for a in argv) == 1
    assert not any(a == "-cfg" for a in argv)
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
