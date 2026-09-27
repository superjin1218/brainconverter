# 현재 구조 (2026-09-27)

브라우저 → Vercel FastAPI → Supabase Auth 신원 확인 → DB 승인·쿼터 확인 → Muse Spark 1.3 Contributor 1회 → Python 검사·컴파일 → FASTEXPR + 12개 설정.

## 해석과 생성

`backend/app/skills/brain-strategy/SKILL.md`의 본문이 모델 시스템 지침입니다. 모델은 StrategyIR JSON을 반환하며 최종 코드는 Python 컴파일러가 생성합니다. 기존 숫자·방향·필터·원문 보존 검사는 유지합니다. 다수결·합의율·병렬 에이전트 호출은 실행하지 않습니다. confidence는 호환 필드로 null이며 모델 품질 점수가 아닙니다.

Gateway Chat Completions에 모델과 Meta 제공자를 고정합니다. `OPENAI_API_KEY`는 읽지 않습니다. 출력 최대 1,024토큰, 요청 1회, 자동 재시도 없음, 모델 타임아웃 최대 35초입니다.

## 인증과 권한

FastAPI가 Supabase password Auth를 중계하고 access/refresh 토큰을 HttpOnly 쿠키에만 담습니다. 클라이언트에는 사용자 이메일·이름·승인 상태·역할만 반환합니다. 변환 및 운영자 API마다 원격 getUser로 신원을 확인하고 DB 함수로 상태·역할을 조회합니다. 회원가입 metadata는 이름만 저장하며 권한으로 신뢰하지 않습니다.

가입자는 이메일 인증 후에도 pending입니다. approved만 변환하며 approved/admin만 회원 관리가 가능합니다. 쿠키 변경·변환·회원 변경에는 동일 Origin과 고정 요청 헤더를 요구합니다. 운영자 본인·다른 운영자의 상태는 회원 화면에서 변경할 수 없습니다.

## DB 사용량과 중복 요청

private 스키마 테이블은 RLS를 켜고 anon/authenticated의 직접 접근을 철회합니다. 고정 search_path의 SECURITY DEFINER 함수는 명시적으로 자신의 신원·승인·운영자 여부를 검사합니다. 서버 전용 함수는 service_role만 실행합니다.

서버는 검증한 사용자 ID와 요청 해시를 예약 함수에 전달합니다. 전역 advisory transaction lock으로 쿼터 확인과 삽입을 직렬화합니다. UUID 요청 ID 재사용은 본인·동일 입력에만 가능하며 진행 조회 또는 24시간 내 완료 결과를 반환합니다. 다른 입력·사용자의 ID는 충돌 처리합니다. 실패·만료 요청은 자동 새 호출하지 않습니다.

실행 슬롯은 전체 20개입니다. 초과 요청은 `queued` 상태로 같은 잠금 안에서 순서를 배정합니다. 브라우저가 5초마다 동일 입력·ID로 `brain_reserve`를 확인하고 빈 슬롯을 확보한 한 요청만 `reserved`를 받아 AI를 호출합니다. 실행 중인 요청의 중복 확인은 `running`으로 반환하고 결과만 조회합니다. 서버 함수는 대기 동안 계속 실행되지 않으며 별도 워커가 없습니다. 화면을 닫으면 2분 후 대기가 만료되고 전체 대기는 최대 10분입니다. 실행 제한 시간은 대기 시작과 분리한 `running_at`부터 계산합니다.

설정 파일·모델 키는 서버에서만 읽습니다. 과거 Cloudflare HMAC·Gateway 코드는 기록으로 남아 있지만 현재 회원 화면과 연결된 지원 배포 방식이 아닙니다. 이전 클라우드 배포 workflow도 비활성화했으며 Vercel/Supabase 운영 구성에는 사용하지 않습니다.
