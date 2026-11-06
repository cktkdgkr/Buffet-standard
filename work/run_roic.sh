#!/usr/bin/env bash
# The ROIC re-derivation, end to end.
#
# Order matters in one place: reconcile_roic.py and diagnose_capital.py compare
# against the FIRST study, so they have to run before apply_corrections.py
# rewrites it. Running the chain twice without restoring the backup would
# compare the corrected file against itself and report that everything agrees.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 오늘 날짜와 자료 신선도"
python3 check_freshness.py --quick

if [ -f analysis.json.pre-roic-correction ]; then
  echo "== 1차 조사 원본 복원 (대조를 위해)"
  cp analysis.json.pre-roic-correction analysis.json
fi

# The cache refetches anything older than a day on its own; REFRESH=1 forces
# the lot, for when the question is whether something changed today.
echo; echo "== 수집: SEC companyfacts"
python3 collect_roic.py ${REFRESH:+--refresh}

echo; echo "== 분자 구성 경로 검정"
python3 test_oi_routes.py

echo; echo "== ROIC 산출"
python3 analyse_roic.py

echo; echo "== 산출값 검증 (항등식·트립와이어·앵커·변이)"
python3 verify_roic.py --mutate

echo; echo "== 1차 조사와 대조"
python3 reconcile_roic.py

echo; echo "== 투하자본 차이의 원인 규명"
python3 diagnose_capital.py

echo; echo "== 1차 조사 정정"
python3 apply_corrections.py

echo; echo "== 보고서 (HTML 전용)"
python3 export_roic_html.py --verify --mutate

echo; echo "완료"
ls -la roic/roic_report.html
