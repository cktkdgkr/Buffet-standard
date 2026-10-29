#!/usr/bin/env bash
# SpaceX and Tesla, end to end.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 오늘 날짜와 자료 신선도"
python3 check_freshness.py --quick

echo; echo "== 오늘 주가"
python3 collect_prices.py SPCX TSLA

echo; echo "== 공시 수집 (10-Q · 10-K · 424B4)"
python3 collect_spx_tsla.py ${REFRESH:+--refresh}

echo; echo "== 산출"
python3 analyse_spx_tsla.py

echo; echo "== 검증 (항등식·합계·앵커·변이)"
python3 verify_spx_tsla.py --mutate

echo; echo "== 마크다운·워드 작성"
python3 export_spx_tsla.py

echo; echo "== 엑셀 작성"
python3 export_spx_tsla_xlsx.py

echo; echo "== 엑셀에 계산값 심기"
python3 embed_xlsx_values.py 스페이스X_테슬라_기업분석.xlsx

echo; echo "== 마크다운 수치 검증"
python3 export_spx_tsla_xlsx.py --verify-md --mutate

echo; echo "완료"
