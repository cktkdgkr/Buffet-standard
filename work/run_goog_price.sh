#!/usr/bin/env bash
# 알파벳 주가 판정 파이프라인.
# 날짜·신선도 → 공시 수집·산출 → 검증 → 보고서 → 산출물 검증.
# 50개사 파이프라인과 같은 순서입니다.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 오늘 $(date -u '+%Y-%m-%d %H:%M UTC') =="

echo
echo "== 1. 수집·산출 (10-Q·8-K·시세를 오늘 기준으로) =="
python3 analyse_goog_price.py --refresh

echo
echo "== 2. 산출값 검증 (항등식·앵커·재산출 + 변이 검정) =="
python3 verify_goog_price.py --mutate

echo
echo "== 3. 보고서 (마크다운·워드·엑셀·HTML) =="
python3 export_goog_price.py
python3 export_goog_price_xlsx.py
python3 export_goog_price_html.py --verify --mutate

echo
echo "== 4. 산출물 검증 (마크다운·엑셀 되읽기 + 변이 검정) =="
python3 verify_goog_exports.py --mutate

echo
echo "== 완료 =="
ls -la 알파벳_주가하락_투자기준판정.* goog/goog_price_report.html
