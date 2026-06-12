"""Persistent, per-domain email-format learning.

When TrueList confirms an address (email_ok) on a normal (non-catch-all) domain,
we record which PATTERNS format produced it. Future people at that company can
then be ranked/resolved with the company's real format instead of a blind guess.

Storage is a small JSON file next to this module. Writes are atomic
(write-temp + os.replace), so concurrent processes can't corrupt it; the only
risk is a lost vote under a race, which is harmless for advisory hints.
"""
import os
import json
import tempfile

_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "email_format_registry.json")


def _load():
    try:
        with open(_REGISTRY_PATH, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _atomic_write(data):
    directory = os.path.dirname(_REGISTRY_PATH) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, _REGISTRY_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def get_format(domain):
    """Best-known format for a domain by majority vote, or None."""
    if not domain:
        return None
    votes = _load().get(domain.lower())
    if not isinstance(votes, dict) or not votes:
        return None
    return max(votes, key=votes.get)


def learn_format(domain, fmt):
    """Record one vote that `domain` uses `fmt`."""
    if not domain or not fmt:
        return
    domain = domain.lower()
    data = _load()
    votes = data.get(domain)
    if not isinstance(votes, dict):
        votes = {}
    votes[fmt] = votes.get(fmt, 0) + 1
    data[domain] = votes
    _atomic_write(data)
