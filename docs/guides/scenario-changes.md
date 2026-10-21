# 시나리오·척도·프롬프트 바꾸기

미션 카탈로그(`scenarios/missions/debate/`)를 바꾸는 순서다. 카탈로그 구조와 규칙은 [product/scenario.md](../product/scenario.md), 평가 척도는 [product/rubric.md](../product/rubric.md)가 정본이다.

## 버전이 정해지는 방식

- `catalog_version`은 미션 폴더 전체(파일 경로와 내용)의 해시다(`scenarios/version.py`, 16자리). 미션 바로 아래 `tests/`와 점으로 시작하는 파일은 넣지 않는다. 자료·프롬프트·픽스처 본문 한 글자만 바꿔도 버전이 바뀐다.
- 채용 건은 생성 때 그 시점의 시나리오 전체(자리·키워드·고정 입장·카드·척도·프롬프트·평가 프롬프트·금지 패턴·자료 목록)를 `positions.scenario`에 복사하고 `catalog_version`을 저장한다. **이미 있는 채용 건은 카탈로그를 바꿔도 자기 복사본으로 계속 진행·평가한다.** 바뀐 시나리오는 새 채용 건부터 적용된다.
- 자료 원문(`materials`)과 검색 청크(`material_chunks`)는 `catalog_version`별로 저장되고 이전 버전 행을 지우지 않는다. 옛 채용 건은 자기 버전 원문을 계속 읽는다.

## 순서

1. **문서 먼저**: 규칙이나 표가 바뀌면 [product/scenario.md](../product/scenario.md)·[product/rubric.md](../product/rubric.md)를 고친다. 기획 방향이 바뀌는 변경이면 [decisions.md](../decisions.md)에 날짜·이유·대안을 적는다.
2. **카탈로그 수정**: `mission.yaml`·`keywords.yaml`·`personas.yaml`·`cards.yaml`·`rubric.yaml`·`materials/<keyword>/*.md`·`prompts/` 중 해당 파일.
   - `rubric.yaml`의 차원·앵커·담당자 참고 문구·기록 없음 사유는 rubric.md 3장·5장 표와 글자 그대로 같아야 한다.
   - 키워드·카드 표는 scenario.md 2.4·4.2 표와 같아야 한다.
   - 아바타는 파일을 덮어쓰지 않고 새 중립 이름(`avatar-NN.png`)으로 더한 뒤 `personas.yaml`의 `avatar`를 바꾼다(진행 중 채용 건이 옛 경로를 쓰기 때문).
3. **정합 검사**: `make test`(루트의 `scenarios/missions/debate/tests`가 카탈로그 ↔ 문서 표, 프롬프트 픽스처를 대조한다). 계약 예시(`tests/fixtures/contracts/`)에 카탈로그 값이 들어 있으면 함께 고친다.
4. **프롬프트 확인**: 페르소나·의도 분류·평가 프롬프트를 바꿨으면 `make eval-live`로 실제 모델 결과를 한 번 남긴다(기준선과 비교). 평가 프롬프트를 바꾸면 `prompt_versions` 해시가 바뀌어 리포트에 새 버전이 기록된다.
5. **시드·재색인**: 자료나 카탈로그가 바뀌면 새 `catalog_version`으로 원문 시드와 재색인을 한다. 로컬 개발 모드는 `make seed`(원문 시드 → 관리자·채용 건 → rag-mcp `reindex_materials`), 격리 e2e 스택은 `make e2e-stack-seed`. api·rag-mcp·report-worker는 카탈로그를 마운트로 읽으므로 컨테이너 재빌드는 필요 없다.
6. **새 채용 건으로 확인**: 관리자 화면 또는 `make stage`로 새 채용 건·세션을 만들어 바뀐 내용이 보이는지 본다. 기존 채용 건의 세션은 바뀌지 않는 것이 정상이다.

## 주의

- 카탈로그 변경은 기존 채용 건에 적용되지 않는다. 변경은 새 채용 건 단위로 공지한다.
- 리포트 재생성(`report/regenerate`)은 채용 건 복사본의 척도·평가 프롬프트를 다시 쓴다(복사본이 없는 옛 채용 건만 현재 파일). 카탈로그의 새 프롬프트로 옛 세션을 다시 평가하는 경로는 없다.
- 카드 시각·단계 예산을 바꾸면 15분 압축 값(최소 20초)과 테스트의 시각 단언이 함께 바뀐다([testing.md](testing.md)).
