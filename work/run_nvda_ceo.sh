#!/usr/bin/env bash
# 엔비디아 CEO 사임 판정 파이프라인.
# 날짜·신선도 → (선행 엔진) → 수집·산출 → 검증 → 보고서 → 페이지 검증.
#
# 선행 엔진이 둘 있습니다. analyse_fair_value 가 TTM·순현금·주식수·10년
# 기록을, analyse_buffett_standard 가 거시·기초율·격자를 만들고, 이 엔진은
# 그 둘을 읽어 오늘 가격으로 판정만 다시 합니다. 먼저 돌리지 않으면 어제
# 가격으로 판정하게 되므로 순서를 고정합니다.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 오늘 $(date -u '+%Y-%m-%d %H:%M UTC') =="
python3 check_freshness.py --quick || true

if [ "${SKIP_UPSTREAM:-}" != "1" ]; then
  echo
  echo "== 1. 선행 엔진 (4개사 적정주가 → 버핏 기준 격자) =="
  bash run_fair_value.sh
  bash run_buffett_standard.sh
else
  echo
  echo "== 1. 선행 엔진 건너뜀 (SKIP_UPSTREAM=1) =="
fi

echo
echo "== 2. 수집·산출 (8-K·10-K·시세를 오늘 기준으로) =="
python3 analyse_nvda_ceo.py ${REFRESH:+--refresh}

echo
echo "== 3. 산출값 검증 (항등식·앵커·2차 전사 + 변이) =="
python3 verify_nvda_ceo.py --mutate

echo
echo "== 4. 보고서 (HTML 전용) + 페이지 되읽기 =="
python3 export_nvda_ceo_html.py --verify --mutate

echo
echo "== 완료 =="
ls -la fv/nvda_ceo_report.html
