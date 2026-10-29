#!/bin/bash
# Runs at every session start, resume, clear and compact.
#
# Two jobs, and the second one is why this file exists.
#
# 1. Install what the analysis scripts need. openpyxl, pypdf and pycryptodome
#    were missing at the start of a previous session and were installed by
#    hand after a script failed on them.
#
# 2. Say what today is and how old the collected data is. A rerun on 29
#    October silently reused a companyfacts cache taken on 3 October, because
#    the cache had no expiry, and four weeks of filings never entered the
#    analysis. Nothing failed. The point of printing this at session start is
#    that the gap is visible before any conclusion is drawn from it.
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-/home/user/Buffet-standard}"

# --- 1. dependencies -------------------------------------------------------
# pip installs into the system Python here, so there is no directory to hang a
# hash file on; the check is a cheap import instead of a reinstall.
PKGS="openpyxl pypdf pycryptodome"
MISSING=""
for mod in openpyxl pypdf Crypto; do
  python3 -c "import ${mod}" 2>/dev/null || MISSING="yes"
done
if [ -n "$MISSING" ]; then
  echo "의존성 설치: ${PKGS}"
  python3 -m pip install --quiet --disable-pip-version-check ${PKGS} \
    || echo "경고: pip 설치 실패 — 스크립트 실행 전 수동 확인 필요"
fi

# --- 2. today's date and data freshness ------------------------------------
echo
echo "=============================================================="
echo " 오늘 $(date -u '+%Y-%m-%d %H:%M UTC') · $(date -u '+%A')"
echo "=============================================================="
if [ -f work/check_freshness.py ]; then
  # --quick: no network, so session start is not held up by 50 SEC requests.
  # The full check (python3 work/check_freshness.py) is one command away and
  # the output below says so when anything looks stale.
  python3 work/check_freshness.py --quick 2>&1 | sed 's/^/ /' || true
  echo
  echo " 분석을 시작하기 전에:"
  echo "   python3 work/check_freshness.py          # 신규 공시 확인 (네트워크)"
  echo "   python3 work/collect_roic.py --refresh   # 오늘 기준으로 재수집"
fi
echo "=============================================================="
