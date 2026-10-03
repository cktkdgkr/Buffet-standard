#!/usr/bin/env bash
# The ROIC re-derivation, end to end.
#
# Order matters in one place: reconcile_roic.py and diagnose_capital.py compare
# against the FIRST study, so they have to run before apply_corrections.py
# rewrites it. Running the chain twice without restoring the backup would
# compare the corrected file against itself and report that everything agrees.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f analysis.json.pre-roic-correction ]; then
  echo "== 1차 조사 원본 복원 (대조를 위해)"
  cp analysis.json.pre-roic-correction analysis.json
fi

echo "== 수집: SEC companyfacts"
python3 collect_roic.py

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

echo; echo "== 엑셀 작성"
python3 export_roic_xlsx.py

echo; echo "== 엑셀 수식 검증"
python3 verify_roic_exports.py

# openpyxl writes formulas with no cached result, so phone and web viewers show
# every derived cell as blank. This fills the results in and keeps the formulas.
echo; echo "== 엑셀에 계산값 심기 (재계산 없는 뷰어 대응)"
python3 embed_xlsx_values.py

echo; echo "== 마크다운 작성 (휴대폰용)"
python3 export_roic_md.py

echo; echo "== 마크다운 수치 검증"
python3 verify_roic_md.py --mutate

echo; echo "== 워드 작성"
python3 export_roic_docx_data.py
node export_memo_docx.js roic/roic_report.json 미국50개사_ROIC_WACC비교.docx

echo; echo "완료"
