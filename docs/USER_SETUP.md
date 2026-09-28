# 키 연결과 실행

새 배포 구성은 Vercel·Supabase와 OpenAI GPT-5.4 mini입니다. 기존 운영 사이트는 아직 Meta 배포본이며, 전환은 새 키를 입력하고 배포한 뒤 적용됩니다.

- 새 OpenAI 키 입력·배포: [OPENAI_DEPLOYMENT.md](OPENAI_DEPLOYMENT.md).

- 로컬 실행과 키 연결은 [LOCAL_TEST.md](LOCAL_TEST.md)를 따릅니다.
- 서버 환경변수와 회원 DB 설정은 [VERCEL_SUPABASE_SETUP.md](VERCEL_SUPABASE_SETUP.md)를 따릅니다.
- 운영·사용량·비용 확인은 [OPERATIONS.md](OPERATIONS.md)를 참고합니다.

로컬 템플릿은 `.env.local.example`, 운영 템플릿은 `.env.vercel.example`입니다. 추론 수준은 `openai_policy.py`에서 `none`로 고정하며 환경변수나 설정 화면에서 바꾸지 않습니다.

```bash
make install
make dev       # 회원 화면·모의 모델
make dev-mock  # 로그인 없이 로컬 화면·모의 모델
make dev-ai    # 서버에 설정한 키로 실제 OpenAI 호출
make preflight-openai  # 유료 생성 없이 연결·예산 정책 조회
make deploy-openai     # 검증과 Vercel 운영 배포
```

이전 Cloudflare·Cloud Run 배포 코드는 2026-09-28 정리하면서 제거했습니다. 과거 절차는 Git 이력에 남아 있습니다.
