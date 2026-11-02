# 이메일 인증 없는 회원가입 정책 변경

작업일: 2026-10-31 (KST). **코드 구현과 로컬 검증은 완료했다. 운영 반영 상태는 아래에서 별도로 구분한다.**

> 후속 SQL 수정: 운영 DB에 `usage_reset_at`이 없다는 사용자 확인에 따라 새 마이그레이션을 수정했다. 아래 548개 테스트 등은 **이 SQL 수정 이전 버전의 결과**다. 수정한 SQL은 사용자의 적용 전 보고 지시에 따라 실행하지 않았다. 후속 검토와 적용 전후 확인 방법은 문서 마지막에 기록했다.

## 변경 내용

- 누구나 이메일·비밀번호·표시 이름으로 가입하고 비밀번호로 로그인한다. Supabase 비밀번호 인증, 원격 세션 검증, HttpOnly·Secure·SameSite=Lax 쿠키, Origin/CSRF 검사를 유지했다.
- HTML `minlength=6`, JavaScript 검사, FastAPI 검사 모두 비밀번호 6~256자를 요구한다. 빈 값·6자 미만은 원격 인증 호출 전에 거부한다. 별도 문자 조합은 요구하지 않는다.
- 가입은 표시 이름만 사용자 메타데이터로 보낸다. 역할·승인은 DB 소유다. 새 마이그레이션은 회원 테이블 기본값과 가입 트리거를 명시적으로 `pending/member`로 유지한다. 가입 응답의 Supabase 세션은 브라우저에 전달하지 않고 비밀번호 로그인을 안내한다.
- FastAPI의 이메일 인증 필수 검사를 제거했다. 변환·사용량·결과 조회는 승인된 회원, 관리자 API는 승인된 관리자만 허용한다.
- 새 SQL은 `brain_set_member_status`, `brain_reserve`, `brain_budget_reserve`에서 이메일 인증 조건만 제거하고 기존 승인·역할·작업 소유권·동시 실행·쿼터·예산·권한 설정을 유지한다.
- 관리자 승인 버튼은 이메일 인증 시각에 의존하지 않는다. 화면에는 별도 경로로 가입자 신원을 확인하라는 사칭 위험 안내를 표시한다.
- 첫 관리자 설정 스크립트는 이메일 주소로 사용자를 고르지 않고 독립적으로 확인한 사용자 UUID를 명시해야 실행된다. 기존 관리자 역할이나 상태는 변경하지 않았으며, 이 스크립트를 운영 DB에서 실행하지 않았다.
- 오래된 인증 링크는 URL의 인증 값을 제거하고 비밀번호 로그인을 안내한다. 링크 토큰을 세션으로 가져오거나 인증 확인 API를 호출하지 않는다. 기존 인증 확인 API는 제거했다.
- Resend SDK·SMTP를 호출하는 앱 코드는 없다. 가입 시 Supabase 공개 설정의 autoconfirm을 먼저 확인하고, Confirm email이 아직 켜져 있으면 메일을 보내기 전에 503으로 중단한다.

## 보존 범위와 위험

기존 `private.brain_members`, 관리자 승인 구조, 회원·작업 결과·사용량·예산·비용 원장을 삭제하거나 초기화하지 않았다. 운영 환경 파일·AI 활성화 상태·Cloudflare Tunnel·DNS 설정도 변경하지 않았다. 과거 사용량 초기화 SQL을 운영 DB에 다시 실행하지 않았다.

이메일 소유를 확인하지 않으면 타인의 이메일·이름으로 가입할 수 있다. Supabase의 자동 인증 시각도 실제 이메일 소유 증명이 아니다. 관리자는 이메일·이름·인증 표시만으로 승인하지 않고 기존 연락처나 대면 확인 등 별도 신뢰 경로로 본인을 확인해야 한다. 이미 타인이 선점한 이메일의 계정을 임의로 승인·합병하면 안 된다. 기존 계정의 비밀번호는 이번 작업에서 변경하지 않았다. 근거: [Supabase 인증 설정](https://supabase.com/docs/guides/auth/general-configuration), [이메일 인증 비활성화의 위험](https://supabase.com/docs/guides/auth/testing-auth-flows).

비밀번호 재설정·이메일 변경 등 향후 메일 기능은 별도 설계 대상이며, 가입·비밀번호 로그인에 Custom SMTP는 필요하지 않다.

## 완료한 검증

| 검증 | 결과 |
| --- | --- |
| Python 전체 테스트 | 548개 통과 (SQL 테스트 42개 포함) |
| JavaScript 테스트 | 49개 통과 |
| 정적 검사·운영 환경 사전 검사 | 통과 |
| 실제 PostgreSQL 16 마이그레이션·권한·예산·동시성 | 통과, 임시 Unix socket DB 사용 |
| 마이그레이션 2회 재적용 후 데이터 동일성 | 회원·작업·예산·비용·초기화 기록·승인 감사 행 동일 |
| 실제 Chrome 흐름 | 가입 → 로그인 → 승인 대기 → 별도 관리자 승인 → 승인 후 모의 변환 → 로그아웃 통과 |
| 브라우저의 외부 네트워크·오류 | 외부 요청 없음, JavaScript 오류 없음 |
| 유료 OpenAI 생성 | 호출하지 않음 |

실제 브라우저 검사는 실제 앱과 모의 Supabase Auth/RPC, 모의 모델을 연결한 임시 서버에서 수행했다. 가짜 회원과 별도 가짜 관리자를 사용했고 운영 DB에는 테스트 회원을 만들거나 승인하지 않았다. 운영 Supabase의 실제 비밀번호 로그인·관리자 승인 성공을 대신 증명하는 검사는 아니다. 브라우저 결과: `PASSWORD_ONLY_BROWSER_VERIFICATION.json`.

재현 명령:

```bash
RUN_SQL_TESTS=1 BRAIN_TEST_PG_BIN=/tmp/brain-policy-postgres/root/usr/lib/postgresql/16/bin \
  LD_LIBRARY_PATH=/tmp/brain-policy-postgres/root/usr/lib/x86_64-linux-gnu .venv/bin/pytest -q
node --test backend/tests/*.test.mjs
.venv/bin/ruff check backend scripts/check_production_config.py scripts/verify_production.py
.venv/bin/python -m scripts.check_production_config --env-file
```

PostgreSQL은 Ubuntu 패키지를 `/tmp/brain-policy-postgres`에 추출해 실행했다. OS 전역 패키지를 설치하거나 DB 서비스를 만들지 않았다. Docker가 있다면 `RUN_SQL_TESTS=1 .venv/bin/pytest -q`로 실행할 수 있다.

## 운영 반영 상태

- 서비스 재시작: `systemctl --no-ask-password restart brainconverter.service`가 Ubuntu Polkit 인증을 기다리다가 `Connection timed out`으로 실패했다. 기존 PID `10057`, 시작 시각 `2026-10-31 17:16:31 KST`가 그대로여서 **변경 후 재배포 미완료**다. 서비스와 터널은 계속 active/running이다.
- 운영 Supabase 설정: 마지막 조회에서 신규 가입 허용, 이메일 공급자 ON, **Confirm email ON**이었다. 대시보드의 Confirm email OFF 변경이 필요하다.
- 운영 DB: `brain_auth_policy_ready` RPC가 404였다. **새 마이그레이션 미적용** 상태다. 현재 환경에는 SQL 실행용 DB 접속 정보·Supabase 관리 토큰이 없다.
- 최소 비밀번호 길이·문자 조합·Custom SMTP 상태는 공개 Auth settings API에 없어 확인하지 못했다. 대시보드에서 최소 6자·문자 조합 요구 없음·Custom SMTP OFF로 설정해야 한다.
- 로컬·공개 페이지와 정적 리소스 해시는 일치한다. 정적 파일은 즉시 반영되지만 Python은 기존 프로세스가 실행 중이므로 새 가입 preflight·이메일 검사 제거 로직이 활성화됐다고 볼 수 없다. 자동 점검에서도 `confirmation_api_retired`가 양쪽 모두 실패했다.
- 운영의 실제 새 회원 가입·로그인·승인·변환 흐름은 아직 검증하지 못했다. 유료 생성은 수행하지 않는다.

운영자가 Supabase SQL Editor에서 `supabase/migrations/202610310001_password_only_membership.sql` **전체만** 실행하고, 신규 가입 허용 ON / Confirm email OFF / 최소 6자 / 문자 조합 요구 없음 / Custom SMTP OFF를 저장해야 한다. 관리 토큰을 `.env.local`에 제공하면 새 SQL만 HTTPS 관리 API로 적용할 수도 있다. 토큰·비밀번호는 채팅이나 로그에 출력하지 않는다.

운영 반영 완료에 필요한 명령 (사용자가 Ubuntu 터미널에서 OS 인증 완료):

```bash
sudo systemctl restart brainconverter.service
```

정책 완료 확인:

```bash
systemctl show brainconverter.service -p ActiveState -p SubState -p MainPID -p ExecMainStartTimestamp
.venv/bin/python scripts/verify_production.py --output docs/PASSWORD_ONLY_VERIFICATION.json
```

자동 점검은 페이지·보안 헤더·미인증 접근 차단·로컬과 공개 페이지 일치·Supabase autoconfirm·DB 정책 readiness를 검사한다. 계정을 생성하거나 로그인하지 않으며 작업·예산을 예약하지 않는다. 각 실행 결과의 `passed`와 실패 항목을 확인한다.

마지막 상태 기록: 2026-10-31T17:22:39+09:00

## 후속 SQL 검토: usage_reset_at 없는 DB 지원 — 미실행

사용자가 현재 DB에 `usage_reset_at` 컬럼이 없음을 확인했다. 앞서 작성한 `brain_reserve()`가 후속 사용량 초기화 마이그레이션의 컬럼을 전제한 것이 문제였다. `202610310001_password_only_membership.sql`을 다음과 같이 수정했다.

- `greatest(month_start/day_start, usage_reset_at)`을 제거하고 한국 시간 기준 `month_start`와 `day_start`를 직접 사용한다. 컬럼을 새로 만들거나 기존 카운터를 초기화하지 않는다. 컬럼이 이미 있는 DB에 적용해도 리셋 시점은 반영하지 않고 달력 월·일의 모든 작업을 집계한다.
- 사용자당 월 50회, 일 20회, 최근 1분 2회, 전체 월 1,000회 제한을 유지한다. 기존 작업도 집계에 포함하므로 이미 제한에 도달한 사용자는 계속 제한된다. 작업 상태별 집계 기준과 동일 요청 ID 재사용 규칙도 유지한다.
- `approved` 검사, 승인된 관리자만 승인 변경 가능, 관리자 계정 변경 제한, 승인 감사 기록, 작업 소유권과 해시 검사, 전역 advisory lock, 실행 슬롯 20개와 FIFO 큐는 유지한다.
- 예산 예약 함수 본문은 수정 전 파일과 동일하다. 요청당 34원, 34원 이외 단가 거부, 승인된 사용자의 실행 중인 소유 작업만 예약, 중복 예약 차단과 예산 상한 검사는 그대로다. 기존 비용 원장과 집계 값을 재설정하지 않는다.
- 작업 예약 중 수행되던 24시간 경과 결과 비우기와 35일 경과 작업 삭제를 제거했다. 적용 시뿐 아니라 이후 예약 호출도 이 정리 구문으로 기록·결과를 삭제하지 않는다. 작업 상태의 정상 전이·만료 처리는 유지하고, 기존 결과 조회 유효기간은 변경하지 않는다. 장기 보관량은 늘어날 수 있으며 별도 보존 정책을 이 변경에서 도입하지 않는다.
- readiness 함수에도 예약 함수가 `usage_reset_at`에 의존하지 않는지 확인하는 조건을 추가했다. readiness는 보조 표시이며 카탈로그·권한 검토나 동작 검증을 대신하지 않는다.

### 함수 보안·실행 권한 검토

수정 전후 `GRANT/REVOKE` 문장은 동일하다. 모든 변경 대상 함수는 `SECURITY DEFINER SET search_path = ''`를 유지하고 테이블·앱 함수는 스키마를 명시한다. 함수 소유자는 새로 지정하지 않는다. `CREATE OR REPLACE FUNCTION`은 기존 함수의 소유자와 권한을 보존하며, 뒤의 명시적 GRANT/REVOKE로 API 역할 접근을 제한한다. 출처: [PostgreSQL CREATE FUNCTION](https://www.postgresql.org/docs/16/sql-createfunction.html), [Supabase 함수 권한 지침](https://supabase.com/docs/guides/database/functions).

| 함수 | PUBLIC / anon | authenticated | service_role |
| --- | --- | --- | --- |
| `brain_set_member_status(uuid,text)` | 실행 차단 | 실행 가능하되 본문에서 `approved/admin` 필수 | 기존 ACL 유지, 별도 부여 없음 |
| `brain_reserve(uuid,uuid,text)` | 실행 차단 | 실행 차단 | 실행 허용 |
| `brain_budget_reserve(uuid,uuid,text,integer)` | 실행 차단 | 실행 차단 | 실행 허용 |
| `brain_auth_policy_ready()` | 실행 차단 | 실행 차단 | 실행 허용 |
| `private.brain_new_member()` | 직접 실행 차단 | 직접 실행 차단 | 기존 트리거·소유자 설정 유지 |

표는 SQL 선언을 검토한 결과이며 운영 DB의 현재 ACL을 실제 조회했다는 의미는 아니다. 신뢰된 SQL Editor에서 아래 읽기 전용 파일로 함수의 모든 overload·소유자·실효 권한·`prosecdef`·`proconfig`를 확인해야 한다. 특히 기존 3인자 `brain_budget_reserve`가 남아 있거나 다른 역할의 추가 권한이 있으면 자동 삭제·권한 변경하지 말고 먼저 검토한다.

### 적용 전 확인 방법

1. 사용자가 신뢰된 SQL Editor에서 `supabase/verify_password_only_membership_readonly.sql` 전체를 실행하고 결과를 저장한다. 파일은 READ ONLY 트랜잭션에서 카탈로그·예산 설정·데이터 건수 및 내용 해시를 조회한 뒤 ROLLBACK한다. 애플리케이션 RPC를 실행하거나 예산을 예약하지 않는다. 같은 DB·같은 신뢰된 역할로 비교해야 한다.
2. `pg_attribute` 기준 실제 컬럼을 확인한다. `information_schema.columns`의 0행은 조회 역할 권한의 영향도 받을 수 있다. 수정 SQL은 실제 유무와 관계없이 `usage_reset_at`을 참조하지 않는다.
3. `brain_jobs`에 큐용 `running_at`, `last_seen_at`이 있고 `brain_job(uuid,uuid)`가 설치되어 있는지 확인한다. 예산 테이블에 `singleton`, `limit_krw`, `accounted_krw`, 비용 원장에 `request_id`, `allowance_krw`가 있어야 하며 단가 제약이 34원을 허용해야 한다. 기존 함수 인자명·반환형·소유자도 확인한다. 맞지 않으면 적용을 보류한다. `gpt_usage_reset.sql`을 해결책으로 실행하지 않는다.
4. 다섯 private 테이블에 RLS가 있고 anon/authenticated 직접 CRUD는 차단되어야 한다. 현재 관리자·회원 상태, 예산 값, 행 수·해시를 저장한다. 적용 중 실제 가입·승인·변환 등 동시 쓰기가 없는 시간대를 선택하면 전후 비교가 가능하다. 해시는 변경 탐지용이며 백업을 대신하지 않는다.

### 승인 후 적용 및 확인 방법

1. 사용자 확인 후에만 수정된 `202610310001_password_only_membership.sql` 전체를 한 번 적용한다. 명시적 BEGIN/COMMIT 안에서 처리되므로 오류가 나면 COMMIT하지 말고 ROLLBACK한다. 과거 초기화 SQL을 함께 실행하지 않는다.
2. 같은 읽기 전용 검증 파일을 다시 실행한다. 예약 함수 본문에 `usage_reset_at` 참조·이메일 인증 조건·DELETE·결과 NULL 정리가 없어야 하며 네 가지 제한과 승인 검사는 남아 있어야 한다. 관리·예산 예약 함수 정의와 모든 실행 권한·SECURITY DEFINER·search_path를 확인한다.
3. 동시 쓰기가 없었다면 다섯 테이블의 행 수와 내용 해시, 예산 설정·집계 값이 전과 동일해야 한다. 기본값 `pending/member`와 가입 트리거가 유지되어야 한다. 예상하지 못한 차이는 원인을 확인하고 자동 초기화·복원으로 덮지 않는다.
4. 동작 검증은 운영 DB 사본이나 독립 테스트 DB에서 진행한다. **초기화 마이그레이션을 실행하지 않은 스키마**에서 컬럼 부재·회원 미승인/승인·50/20/2/1,000 경계·34원 예약/중복/예산상한을 시험한다. 오래된 작업·결과를 미리 넣고 보존 여부도 확인한다. 함수 호출 자체가 작업/비용 원장에 쓰므로 운영 DB에서는 임의의 예약 RPC를 호출하지 않는다. 실제 OpenAI 생성은 필요 없다.

### 이번 수정의 검증 범위

수정 SQL의 20개 최상위 문장과 읽기 전용 검증 SQL의 11개 문장을 오프라인 PostgreSQL 구문 파서로 파싱했다. PL/pgSQL 구문도 검사했으며 오프라인 파서가 private 스키마 복합 타입을 해석하지 못하는 두 함수는 **검사용 입력에서만** 해당 선언을 RECORD로 바꿔 구문을 확인했다. 실제 파일의 타입 선언은 바꾸지 않았다. 승인 조건·네 제한·삭제/초기화 부재·34원 함수 본문과 GRANT/REVOKE 동일성도 정적으로 대조했다.

이 검사는 실제 DB 컬럼·타입 해석이나 실행 성공을 보증하지 않는다. 수정한 마이그레이션, 읽기 전용 확인 SQL, 기존 테스트의 초기화 SQL을 포함하여 **이번 후속 작업에서는 SQL을 DB에서 실행하지 않았다.** 운영 DB·데이터·서비스도 변경하지 않았다. 앞서 통과했던 548개 테스트는 이번 수정 전 버전에 대한 결과이며 새 SQL의 실행 검증 결과로 재사용하지 않는다.
