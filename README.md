# 자연어 BRAIN Alpha 변환 하네스

한국어 자연어 퀀트 전략을 WorldQuant BRAIN FASTEXPR 후보와 전체 시뮬레이션 설정으로 변환하는 검증형 웹 서비스입니다.

## 핵심 원칙

- LLM은 자연어 전략을 구조화된 Strategy IR로 해석합니다.
- Python이 합의·검증·FASTEXPR 컴파일을 결정론적으로 수행합니다.
- 사용자가 설정을 생략해도 BRAIN의 12개 시뮬레이션 설정을 모두 반환합니다.
- 브라우저에는 모델 API 키를 전달하지 않습니다.
- BRAIN 이메일·비밀번호·쿠키를 수집하거나 저장하지 않습니다.

## 기본 설정

`USA · TOP3000 · Delay 1 · Subindustry · Decay 4 · Truncation 0.08 · Pasteurization On · Unit Handling Verify · NaN Handling Off`

Language, Instrument Type, Test Period를 포함한 전체 12개 설정과 각 값의 `사용자 지정/기본값` 출처를 결과에 포함합니다.

## 로컬 실행

API 키 없이 화면과 전체 흐름을 확인하려면 모의 공급자를 사용합니다.

```bash
make install
make dev
```

브라우저에서 `http://localhost:8080`을 엽니다.

실제 모델을 연결할 때는 `.env.example`을 참고해 배포 환경에 `OPENAI_API_KEY`를 Secret으로 등록하고 `HARNESS_PROVIDER=openai`를 사용합니다. 키를 파일이나 Git 저장소에 커밋하지 마세요.

## 테스트

```bash
make test
make lint
```

테스트는 외부 모델을 호출하지 않습니다.

## 배포

- 애플리케이션: Google Cloud Run
- 접근 제어·쿼터: Cloudflare Worker + Access
- CI: GitHub Actions

사용자가 마지막에 설정해야 하는 값은 [배포 체크리스트](docs/USER_SETUP.md)에 정리되어 있습니다.

## 프로젝트 구조

```text
backend/app/       FastAPI, 하네스, 정적 대시보드
backend/tests/     결정론적 컴파일·설정·API 테스트
gateway/           Cloudflare Access/KV 기반 Gateway
docs/              아키텍처, 운영, 사용자 설정 문서
.github/workflows/ CI 및 수동 Cloud Run 배포
```

## 범위

이 서비스는 코드와 설정 초안을 생성합니다. 수익률을 보장하지 않으며 BRAIN 로그인, 자동 시뮬레이션, 자동 제출은 수행하지 않습니다.

