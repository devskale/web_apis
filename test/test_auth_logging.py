"""Regression tests for access-log auth marking (fail2ban api-auth false positive).

A token-less request is an auth FAILURE only when the endpoint rejected it
(401). Public endpoints (/api/duck/*, /help) accept token-less traffic and
answer 200; logging those as "no-auth" made the api-auth jail ban legitimate
callers (5 searches in 10 min -> 30-day ban, both directions, since an
inbound ban also drops the SYN-ACKs the banned peer needs).

Pinned here:
  - token-less 401  -> "no-auth"     (still counts as a failure)
  - token-less 2xx  -> "no-auth-ok"  (must never match the failregex)
  - the access log emits a trailing status field the filter keys on
"""
import logging

import pytest

import main


@pytest.mark.parametrize("status", [200, 202, 301, 404, 429, 500])
def test_tokenless_non_401_is_not_an_auth_failure(status):
    assert main._auth_for_log(None, status) == "no-auth-ok"


def test_tokenless_401_is_an_auth_failure():
    assert main._auth_for_log(None, 401) == "no-auth"


@pytest.mark.parametrize("status", [200, 401])
def test_bearer_calls_keep_their_marker(status):
    """A present Authorization header is never rewritten."""
    assert main._auth_for_log("Bearer secret", status).startswith("Bearer ")


def test_unauthorized_bearer_keeps_its_marker():
    """A rejected Bearer call stays visible as itself, not as no-auth."""
    assert main._auth_for_log("Bearer wrong", 401).startswith("Bearer ")


def test_log_format_contains_status():
    """Regression: `status` was added to the log record but NOT to the
    formatter, so the failregex could never match a real line."""
    fmt = main.access_logger.handlers[0].formatter._fmt
    assert "%(status)s" in fmt, f"access log format lacks the status field: {fmt}"


def test_log_format_field_order_ends_with_status():
    """The filter anchors on the trailing status, so it must come last."""
    fmt = main.access_logger.handlers[0].formatter._fmt
    assert fmt.rstrip().endswith("%(status)s"), fmt


def test_rotation_is_large_enough_for_forensics():
    """Regression: 4 KB / 1 backup rotated the evidence away within hours."""
    handler = next(h for h in main.access_logger.handlers
                   if hasattr(h, "maxBytes"))
    assert handler.maxBytes >= 512 * 1024, f"log rotation too small: {handler.maxBytes}"
    assert handler.backupCount >= 3, f"too few log backups: {handler.backupCount}"
