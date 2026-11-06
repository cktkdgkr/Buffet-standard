#!/usr/bin/env bash
# 성장률 재검증 + 버핏 기준 적정주가.
# 본문 파이프라인(run_fair_value.sh)이 먼저 돌아 fv/fair_value.json 이
# 있어야 합니다.
set -euo pipefail
cd "$(dirname "$0")"
echo "== 오늘 $(date -u '+%Y-%m-%d %H:%M UTC') =="
echo; echo "== 1. 산출 (기초율·거시·버핏 기준 격자) =="
python3 analyse_buffett_standard.py --refresh
echo; echo "== 2. 산출값 검증 =="
python3 verify_buffett_standard.py --mutate
echo; echo "== 3. 보고서 (HTML 전용) =="
python3 export_buffett_standard_html.py --verify --mutate
echo; echo "== 완료 =="
ls -la fv/buffett_standard_report.html
