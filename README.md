# 무역구제 조사범위 분쟁 DB

덤핑방지관세가 부과된 뒤 "이 물품이 조사범위에 들어가는가"를 둘러싸고 세관, 관세청, 조세심판원, 법원에서 벌어진 분쟁을, 그 분쟁이 가리키는 부령(조치)과 무역위원회 조사 사건에 사건 단위로 연결한 데이터베이스다. 조치 계열(무역위원회 판정과 부령)과 분쟁 계열(불복 결정)은 서로 다른 기관에 따로 기록되어 있어, 둘을 이어야 어떤 형식의 범위 문언이 분쟁을 부르는지, 부처 간 해석이 얼마나 자주 엇갈리는지를 측정할 수 있다.

배경, 연구 질문, 단계별 절차와 그 진행 상황, 스키마, 한계는 [collection-plan.md](collection-plan.md)에 있다. 이 문서는 무엇이 어디 있고 어떻게 다시 만드는지만 적는다.

## 1. 자료원

모두 공개 누리집에서 받았다. 받은 원문은 `data/raw/`에 두고, 스크립트는 이미 받은 파일을 다시 받지 않는다.

| 자료 | 출처 | 원문 위치 |
|---|---|---|
| 덤핑방지관세 부과 부령(현행·폐지 전 판)과 별표(HWP·PDF) | 국가법령정보센터 | `data/raw/decrees/`, `data/raw/annexes/` |
| 조세심판원 결정문 | 조세심판원 심판결정례 | `data/raw/tt/` |
| 관세청 과세전적부심사·심사청구 결정, 처분청 번호의 심판청구 사본, 판결 요지 | 관세법령정보포털(CLIP) 통합검색 | `data/raw/clip/` |
| 무역위원회 반덤핑조사 사건(종결·진행), 조사대상물품 범위 안내서, 보도자료 | 무역위원회 누리집 | `data/raw/ktc/`, `data/raw/ktc-scope/`, `data/raw/ktc-press/` |
| 무역위원회 30년의 발자취(2017) 부록 운용자료집 | 무역위원회 누리집 PDF | `data/raw/ktc-book/` |
| HSK 10단위 연도별 별표와 개정별 연계표 | KCSDB2 저장소의 HS10 연계표 작업 산출물 | `C:\Work\Projects\KCSDB2\analysis\HS10 연계표 구축\outputs\` (이 저장소에 복사하지 않음) |

결정문의 청구인·회사명은 원문에서 가려져(OOO) 있고, 이 저장소도 그대로 둔다.

## 2. 다시 만들기

`scripts/`의 번호 순서대로 돌린다. 저장소 루트에서 `python scripts/<파일>`로 실행한다. 필요한 패키지는 requests, beautifulsoup4, olefile, openpyxl이고, PDF 텍스트 추출에 pdftotext(poppler)를 쓴다.

| 단계 | 스크립트 | 하는 일 |
|---|---|---|
| 1. 부령 | `01_collect_decrees.py` | 부령 판 목록과 본문 받기 |
| | `02_parse_decrees.py` | 조문·별표에서 범위 문언을 뽑고 판을 조치로 묶기 |
| | `03_collect_annexes.py` | 별표 PDF·HWP 받기와 텍스트 추출 |
| | `04_build_coding_input.py` | 조치별 코딩 입력 만들기 |
| | `05_merge_coding.py` | 코딩 묶음 합치기와 값 검사 |
| | `19_build_coder_form.py` | 두 번째 코더용 엑셀 양식 만들기 |
| | `20_compare_coders.py` | 두 코더 대조(일치율, 카파, 불일치 목록) |
| 2. 분쟁 | `06_collect_tt_decisions.py` | 조세심판원 결정문 받기 |
| | `07_collect_clip_decisions.py` | 관세법령정보포털 결정·판결 받기 |
| | `08_build_dispute_list.py` | 두 출처를 결정 목록으로 합치기 |
| | `09_build_extraction_input.py` | 결정문 추출 입력 묶음 만들기 |
| | `10_merge_extraction.py` | 추출 결과 합치기와 값 검사 |
| 3. 매칭 | `11_match_disputes.py` | 분쟁 결정을 조치에 연결 |
| 4. 무역위원회 | `12_collect_ktc_cases.py` | 반덤핑조사 사건 목록과 상세 받기 |
| | `13_match_ktc.py` | 조치를 사건에 연결 |
| | `14_collect_ktc_scope_guides.py` | 조사대상물품 범위 안내서 받기 |
| | `15_collect_ktc_press.py` | 반덤핑 보도자료 받기 |
| | `16_link_press_to_cases.py` | 보도자료 추출을 사건에 붙이고 사건별로 모으기 |
| | `17_link_book_to_cases.py` | 30년사 부록을 사건에 붙이고 보도자료와 합치기 |
| 5. HSK | `18_hsk_revisions.py` | 열거 HSK의 개정 영향과 부령 정비 여부 판정 |

수집 스크립트 사이에 사람이나 Claude가 문언을 읽고 채우는 단계가 셋 있다. 이 단계의 산출은 스크립트로 다시 만들어지지 않으므로 파일 자체가 원본이다.

| 단계 | 지침 | 산출 |
|---|---|---|
| 부령 범위 문언 코딩 | `data/coding/codebook.md` | `data/coding/coder-a.csv`(초벌), 두 번째 코더의 `coder-b.xlsx` |
| 분쟁 결정문 항목 추출 | `data/extraction/guide.md` | `data/extraction/draft-v2/` |
| 무역위원회 보도자료 항목 추출 | `data/extraction/press-guide.md` | `data/extraction/press-draft/` |
| 30년사 부록 표 구조화 | 계획서 7.4절 | `data/ktc-book-cases.csv`, `data/ktc-book-measures.csv` |

## 3. 주요 산출

| 파일 | 단위 | 내용 |
|---|---|---|
| `data/measures.csv` | 조치 | 부령 제명, 대상국, 시행일, 유효기간, 열거 HSK, 범위 문언 |
| `data/decree-texts.csv` | 부령 판 | 판별 부과대상 조문, 제외 문언, 별표 텍스트 |
| `data/coding/coder-a.csv` | 조치 | 부과대상 조건과 제외 요건의 유형 코딩(초벌) |
| `data/disputes.csv` | 결정 | 조세심판원·관세청·법원 결정 목록 |
| `data/dispute-extract.csv` | 결정 | 쟁점 분류, 인용 부령, 주장, 결과, 판단 기준, 결정 묶음, 분쟁 연쇄 |
| `data/dispute-citations.csv` | 결정 × 회신 | 결정문이 원용한 행정기관 회신과 그 채택 여부 |
| `data/dispute-measure-links.csv` | 결정 × 조치 | 분쟁과 조치의 연결(방법, 수입기간) |
| `data/ktc-cases.csv` | 무역위원회 사건 | 조사번호, 대상국, 재심 종류, 개시·예비·최종판정일 |
| `data/measure-ktc-links.csv` | 조치 × 사건 | 조치와 무역위원회 사건의 연결 |
| `data/ktc-case-summary.csv` | 무역위원회 사건 | 신청인, 판정 결과, 세율, 가격약속, 범위 서술, 출처 |
| `data/hsk-revision-measures.csv` | 조치 × HSK 개정 | 열거 HSK의 개정 영향과 부령 정비 여부 |

건수와 연결률은 각 스크립트가 실행할 때 출력한다. 이 문서에 옮겨 적지 않는다.

## 4. 주의할 점

초벌 코딩과 추출은 Claude가 했다. 부령 범위 문언 코딩, 분쟁 결정문 추출, 보도자료 추출, 30년사 부록 구조화가 여기에 해당하며, 모두 사람의 검토를 거치지 않았다. 범위 문언 코딩은 두 번째 코더(사람)와 대조해 일치율을 보고한 뒤에 분석에 쓴다(계획서 7.1절). 판단의 근거는 각 파일의 근거·비고 칸에 남아 있다.

연결은 추정이다. 분쟁과 조치는 인용된 부령 번호로 대부분 이어지지만 일부는 제명과 수입기간, 물품명, HSK로 이었고 방법 칸에 그 사실을 적었다. 무역위원회 사건과 조치, 보도자료와 사건의 연결은 물품명 유사도와 대상국, 날짜로 고른 것이다. HSK 개정 판정은 KCSDB2 연계표를 쓰므로 그 연계표의 한계(코드 사이의 연결이 추정이고 안분 비율이 수출액 기준)를 그대로 가진다.

원자료에도 오류가 있다. 30년사 부록에는 다른 품목의 조치 내용이 복사된 행과 두 표 사이에 세율이 다른 품목이 있고, 구조화할 때 책의 값을 그대로 두고 비고에 적었다. 보도자료의 게시판 등록일은 실제 보도일보다 늦은 경우가 있다.

받은 원문(`data/raw/`)은 백 메가바이트가 넘어 git에 넣지 않는다(`.gitignore`). 2절의 수집 스크립트를 돌리면 같은 위치에 다시 받아진다. 누리집이 파일을 바꾸거나 내리면 같은 원문을 얻지 못할 수 있으므로, 원문 묶음은 저장소 밖에 따로 보관한다.
