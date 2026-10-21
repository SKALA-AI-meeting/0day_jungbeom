# 데이터베이스 초기화와 스키마 변경

테이블과 컬럼의 뜻은 [architecture/data-model.md](../architecture/data-model.md), DDL은 `infra/db/schema.sql`이다.

## 새 DB

- compose의 postgres는 볼륨(`pgdata`, 격리 e2e 스택은 `dayzero-debate_pgdata`)이 비어 있을 때만 `infra/db/schema.sql`을 `/docker-entrypoint-initdb.d`로 한 번 적용한다.
- api 단위 테스트는 실행마다 임시 DB(`dayzero_test_<랜덤>`)를 만들어 `schema.sql`을 적용하고 끝나면 지운다(`services/api/tests/conftest.py`). 그래서 `schema.sql` 수정은 다른 사람의 개발 DB를 건드리지 않는다.
- 자료 원문(`materials`)과 검색 청크(`material_chunks`)는 스키마가 아니라 시드가 채운다(`make seed`, 격리 스택은 `make e2e-stack-seed`).

## 기존 DB에 변경 반영

볼륨이 이미 있으면 `schema.sql`을 고쳐도 다시 적용되지 않는다. 보존할 데이터가 있는 DB는 볼륨을 지우지 않고 변경 SQL을 적용한다. 볼륨 삭제(`docker compose down -v`)는 데이터를 버려도 되는 개인 개발 DB에서만 쓰고 기본 절차로 삼지 않는다.

1. 변경 SQL을 쓴다. 다시 실행해도 안전하게(`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` 등) 쓰고, 같은 내용을 `schema.sql`에도 반영한다.
2. 백필이 필요하면 같은 파일에 `UPDATE`를 두고, 새 컬럼의 null이 기존 행에서 무슨 뜻인지 data-model.md에 적는다.
3. 적용 전 백업: `docker compose -f infra/docker-compose.yml --env-file infra/.env exec postgres pg_dump -U dayzero dayzero > backup.sql`
4. 적용: `docker compose -f infra/docker-compose.yml --env-file infra/.env exec -T postgres psql -U dayzero -d dayzero -v ON_ERROR_STOP=1 < <변경 SQL>`
5. 확인: `psql`의 `\d <테이블>`로 컬럼을 보고, api를 다시 띄워 관련 화면·테스트를 한 번 돌린다.
6. 되돌리기가 필요하면 3의 백업을 `psql`로 다시 넣는다.

예: 제출 때 빈 칸 기록 컬럼(`proposals.submit_blank_sections`, `proposals.blank_warning_shown`)을 기존 DB에 더하는 SQL.

```sql
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS submit_blank_sections text[];
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS blank_warning_shown boolean;
-- 기존 행은 null로 둔다(제출 전과 같은 뜻: 기록 없음)
```

## 변경 SQL 보관 규칙 (제안)

지금 저장소에는 변경 SQL 폴더가 없다. 다른 사람과 같은 DB를 이어 쓰려면 아래 규칙을 쓴다.

- 위치 `infra/db/migrations/`, 이름 `NNNN_<짧은 설명>.sql`(번호는 4자리로 1씩 증가).
- 파일 하나는 한 번의 스키마 변경이고, 다시 실행해도 결과가 같아야 한다.
- `schema.sql`은 항상 "모든 변경을 적용한 최종 상태"다. 새 DB는 `schema.sql`만으로 만들고 변경 SQL은 기존 DB에만 쓴다.
- 스키마를 바꾸는 PR은 `schema.sql`, 변경 SQL, data-model.md, 필요하면 계약([contracts/](../contracts/README.md))을 함께 고친다([contributing.md](contributing.md) "DB 변경").
- 적용 이력 테이블과 자동 적용 도구는 아직 없다. 도입하면 이 문서를 그 도구 기준으로 바꾼다.
