#!/usr/bin/env bash
# 네 기업 적정주가 파이프라인.
# 날짜·신선도 → 50개사 ROIC 갱신 → 시세 → 산출 → 검증 → 보고서 → 산출물 검증.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 오늘 $(date -u '+%Y-%m-%d %H:%M UTC') =="

echo
echo "== 1. 50개사 ROIC 를 오늘 기준으로 (10년 기록이 시나리오의 입력입니다) =="
python3 collect_roic.py --refresh
bash run_roic.sh 2>&1 | grep -E "^==|검사|변이|실패" || true

echo
echo "== 2. 시세 =="
python3 collect_prices.py MSFT GOOG NVDA SPCX

echo
echo "== 3. 산출 (TTM 재구성 + 시나리오 DCF) =="
python3 analyse_fair_value.py --refresh

echo
echo "== 4. 산출값 검증 (항등식·앵커·규칙재현 + 변이) =="
python3 verify_fair_value.py --mutate

echo
echo "== 5. 보고서 (HTML 전용) =="
python3 export_fair_value_html.py --verify --mutate

echo
echo "== 완료 =="
ls -la fv/fair_value_report.html
