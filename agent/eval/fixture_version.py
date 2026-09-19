import hashlib


def compute_fixture_version(*paths: str) -> str:
    """Short content hash of one or more fixture files, stored alongside each eval_runs
    row (see schema.sql's eval_runs.fixture_version) so run_judge_drift_check.py can tell
    whether two runs it's comparing actually used the same test cases - a score delta
    between runs whose fixture changed isn't judge/prompt drift, it's an expected
    consequence of editing the fixture, and conflating the two defeats the whole point
    of the drift check.

    A content hash, not a manually-bumped version number - relying on someone to
    remember to bump a version string every time they edit a fixture is exactly the kind
    of manual discipline that doesn't hold up in practice (fixtures got edited multiple
    times this session with no version bump). Hashing the actual bytes means it's always
    correct with zero maintenance.

    Multiple paths (e.g. guardrails' separate input/output fixtures) are hashed together
    into one version string, in the order given - deterministic as long as callers pass
    a stable order.
    """
    digest = hashlib.sha256()
    for path in paths:
        with open(path, "rb") as f:
            digest.update(f.read())
        digest.update(b"\0")  # path separator, so ("ab","c") != ("a","bc")
    return digest.hexdigest()[:12]
