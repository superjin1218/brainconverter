// Amounts are estimates from recorded OpenAI usage, separate from the budget reserve.
export function budgetSummary(budget) {
  const reserve = `${budget.stopped ? "AI 변환 중지" : "예산 예약"} · ${budget.accountedKrw.toLocaleString()} / ${budget.limitKrw.toLocaleString()}원 · 시도당 ${budget.allowancePerAttemptKrw}원 확보`;
  if (!Number.isSafeInteger(budget.estimatedCostMicrousd) || !Number.isSafeInteger(budget.attempts)) {
    return `GPT 사용량 집계 업데이트가 필요합니다.\n${reserve}`;
  }
  const cost = (budget.estimatedCostMicrousd / 1_000_000).toFixed(6);
  const missing = budget.unconfirmedAttempts > 0
    ? ` · 비용 미확인 ${budget.unconfirmedAttempts.toLocaleString()}회 별도` : "";
  const since = new Date(budget.since).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  return [
    `사이트 전체 GPT-5.4 mini · 변환 시도 ${budget.attempts.toLocaleString()}회`,
    `토큰 기준 예상 비용 $${cost}${missing}`,
    `입력 ${budget.inputTokens.toLocaleString()} · 출력 ${budget.outputTokens.toLocaleString()}토큰`,
    reserve,
    `${since} (한국 시간) 초기화 이후 집계 · 실제 청구액은 OpenAI에서 확인`,
  ].join("\n");
}
