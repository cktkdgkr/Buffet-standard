"""
Disk cache for SEC data that knows how old it is.

The collectors each kept their own cache and none of them had an expiry: the
rule was "if the file exists and is not tiny, use it." That is fine for a
rerun an hour later and wrong for a rerun a month later, which is what
happened - the companyfacts cache was fetched on 3 October, the analysis was
rerun on 29 October, and four weeks of filings never entered it. Nothing failed
and nothing warned; the numbers were simply out of date while looking current.

So age is part of the cache now. A cached file older than max_age_days is
refetched, --refresh forces it, and every reader can see when the copy was
taken.

The SEC asks for a descriptive User-Agent with contact details and limits
callers to ten requests a second. Both are handled here so no collector has to
remember.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone

UA = "Buffett-standard research cktkdgkr@gmail.com"

# Filings land daily, so a copy taken today is current and a copy taken
# yesterday may not be. One day is the default; a collector that wants to be
# stricter passes less.
DEFAULT_MAX_AGE_DAYS = 1.0

_last_request = [0.0]
MIN_INTERVAL = 0.12          # ~8 requests a second, inside the SEC's limit


def _meta_path(path):
    return path + ".fetched"


def fetched_at(path):
    """
    When this copy came from the SEC, as recorded when it was written.

    Not the file's mtime. A container restore, a git checkout or a copy resets
    mtime to now, which makes a month-old cache look like it was fetched
    seconds ago - that is exactly what it did here, reporting "0.0일 전" for
    files taken four weeks earlier. The fetch time is therefore written to a
    sidecar beside the content, and mtime is only a fallback for files cached
    before the sidecar existed.
    """
    meta = _meta_path(path)
    if os.path.exists(meta):
        try:
            with open(meta) as fh:
                return datetime.fromisoformat(json.load(fh)["fetched_at"])
        except Exception:                                      # noqa: BLE001
            pass
    if os.path.exists(path):
        return datetime.fromtimestamp(os.path.getmtime(path),
                                      tz=timezone.utc)
    return None


def age_days(path):
    """How old the cached copy is, or None if there is no usable copy."""
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        return None
    when = fetched_at(path)
    if when is None:
        return None
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0


def has_fetch_record(path):
    """Whether the age of this copy is recorded or merely inferred."""
    return os.path.exists(_meta_path(path))


def is_fresh(path, max_age_days=DEFAULT_MAX_AGE_DAYS, min_bytes=1000):
    """
    Whether the cached copy can be used without refetching.

    A copy with no recorded fetch time is never fresh, however recent its
    mtime looks. Otherwise the bug this module exists to fix survives it: a
    month-old cache whose mtime was reset by a restore reports an age of zero,
    passes the check, and is reused. Refetching those once is cheap and leaves
    every copy with a real record.
    """
    if not os.path.exists(path) or os.path.getsize(path) < min_bytes:
        return False
    if not has_fetch_record(path):
        return False
    age = age_days(path)
    return age is not None and age <= max_age_days


def throttle():
    gap = time.time() - _last_request[0]
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_request[0] = time.time()


def fetch(url, path, max_age_days=DEFAULT_MAX_AGE_DAYS, refresh=False,
          min_bytes=1000, binary=False):
    """
    The file at path, refetched from url when the copy is missing, truncated,
    older than max_age_days, or when refresh is set.

    Returns (path, took_from_network, age_days_before). The age is reported so
    a caller can say what it used rather than leaving the reader to assume.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    before = age_days(path)
    if not refresh and is_fresh(path, max_age_days, min_bytes):
        return path, False, before

    tmp = path + ".part"
    throttle()
    try:
        subprocess.run(["curl", "-sS", "--fail", "--compressed",
                        "-A", UA, url, "-o", tmp], check=True)
        if os.path.getsize(tmp) < min_bytes:
            raise OSError(f"응답이 너무 작음 ({os.path.getsize(tmp)} bytes)")
        os.replace(tmp, path)
        with open(_meta_path(path), "w") as fh:
            json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(),
                       "url": url}, fh)
        return path, True, before
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        # A stale copy beats nothing, but the caller has to be told it is
        # stale rather than discovering it in the output.
        if os.path.exists(path) and os.path.getsize(path) >= min_bytes:
            return path, False, before
        raise


def fetch_json(url, path, **kw):
    p, from_network, before = fetch(url, path, **kw)
    with open(p) as fh:
        return json.load(fh), from_network, before


def companyfacts(cik, cache_dir, **kw):
    """XBRL companyfacts for one CIK."""
    cik = int(cik)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    path = os.path.join(cache_dir, f"CIK{cik:010d}.json")
    return fetch_json(url, path, min_bytes=2000, **kw)


def submissions(cik, cache_dir, **kw):
    """The filing index for one CIK - what it has filed and when."""
    cik = int(cik)
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    path = os.path.join(cache_dir, f"SUB{cik:010d}.json")
    return fetch_json(url, path, min_bytes=500, **kw)


def describe(before, from_network, path=None):
    """One phrase for a log line, so the age of the data is never implicit."""
    if from_network:
        return "새로 받음" if before is None else \
            f"새로 받음 (기존 사본 {before:.1f}일 경과)"
    if before is None:
        return "캐시 사용 (나이 불명)"
    certain = path is None or has_fetch_record(path)
    return (f"캐시 {before:.1f}일 경과" if certain
            else f"캐시 (기록 없음, mtime 기준 {before:.1f}일)")
