export function registerConversionTool({form, convert}) {
  if (!document.modelContext?.registerTool) return;
  const lifecycle = new AbortController();
  Promise.resolve(document.modelContext.registerTool({
    name: "convert_brain_alpha_strategy",
    title: "BRAIN Alpha 전략 변환",
    description: "자연어 퀀트 전략을 검증된 FASTEXPR과 전체 BRAIN 시뮬레이션 설정으로 변환합니다.",
    inputSchema: {
      type: "object",
      properties: {strategy: {type: "string", minLength: 3, maxLength: 2000}},
      required: ["strategy"],
      additionalProperties: false,
    },
    annotations: {readOnlyHint: false, untrustedContentHint: true},
    async execute(input) {
      if (!input || typeof input.strategy !== "string" || input.strategy.trim().length < 3) {
        throw new Error("3자 이상의 자연어 전략이 필요합니다.");
      }
      form.setStrategy(input.strategy);
      const result = await convert(form.payload());
      return {
        status: result.status,
        fastExpression: result.fastExpression,
        simulationSettings: result.simulationSettings,
        warnings: result.warnings,
        strategyExplanation: result.strategyExplanation,
        assumptions: result.assumptions,
        improvementSuggestions: result.improvementSuggestions,
        refinementOptions: result.refinementOptions,
      };
    },
  }, {signal: lifecycle.signal})).catch(() => {});
}
