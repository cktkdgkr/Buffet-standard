#!/usr/bin/env bash
# S&P 500·나스닥100 지수 판정 파이프라인.
# 날짜 → 수집(시세·S&P 이익·실러·나스닥100 구성종목 SEC 집계) → 산출 →
# 검증 → 보고서 → 페이지 검증.
#
# 선행 엔진: analyse_buffett_standard 의 기초율·버핏 인용·기대인플레이션을
# 읽습니다. 그 JSON 이 오늘 것이 아니면 먼저 돌리십시오
# (bash run_buffett_standard.sh).
set -euo pipefail
cd "$(dirname "$0")"

echo "== 오늘 $(date -u '+%Y-%m-%d %H:%M UTC') =="

echo
echo "== 1. 수집 (시세·S&P 500 이익·실러·나스닥100 구성종목 SEC 공시) =="
python3 collect_index.py ${REFRESH:+--refresh}

echo
echo "== 2. 산출 (30년 기록·격자·매수선·요구 성장률·백테스트) =="
python3 analyse_index.py

echo
echo "== 3. 산출값 검증 (항등식·두 출처 대조·앵커 + 변이) =="
python3 verify_index.py --mutate

echo
echo "== 4. 보고서 (HTML 전용) + 페이지 되읽기 =="
python3 export_index_html.py --verify --mutate

echo
echo "== 완료 =="
ls -la idx/index_report.html
