const SETTING_LABELS = {
  language: "Language",
  instrumentType: "Instrument",
  region: "Region",
  universe: "Universe",
  delay: "Delay",
  neutralization: "Neutralization",
  decay: "Decay",
  truncation: "Truncation",
  pasteurization: "Pasteurization",
  unitHandling: "Unit Handling",
  nanHandling: "NaN Handling",
  testPeriod: "Test Period",
};

const VALIDATION_LABELS = {
  jsonValid: "JSON 형식",
  schemaValid: "Strategy IR 스키마",
  sourceRequirementsPreserved: "명시 조건 검사",
  compilePassed: "표현식 구문 검사",
  intentPlanChecked: "선호 방향·원문 근거 검사",
  catalogFieldsChecked: "BRAIN 필드 카탈로그 검사",
  fieldTypesChecked: "필드 자료형 검사",
  brainExecutionChecked: "BRAIN 실행 확인",
};

export class DashboardView {
  constructor(root = document) {
    this.root = root;
    this.empty = root.querySelector("#result-empty");
    this.loading = root.querySelector("#result-loading");
    this.content = root.querySelector("#result-content");
    this.error = root.querySelector("#result-error");
    this.status = root.querySelector("#result-status");
    this.bindCopyButtons();
  }

  showLoading(progress = {}) {
    this.setState("loading");
    const queued = progress.status === "queued";
    this.status.textContent = queued ? "대기열에서 대기 중" : "해석 중";
    this.root.querySelector("#loading-title").textContent = queued
      ? "처리 순서를 기다리는 중입니다"
      : "전략을 해석하고 코드를 만들고 있습니다";
    this.root.querySelector("#loading-description").textContent = queued
      ? `대기 순서 ${progress.queuePosition || 1}번 · 빈자리가 생기면 자동으로 시작합니다. 이 화면을 열어 두세요.`
      : "실제 AI 응답에는 최대 1분 정도 걸릴 수 있습니다.";
  }

  clear() {
    for (const selector of ["#expression-output", "#settings-copy", "#error-message",
      "#result-mode-note", "#metric-status", "#metric-confidence", "#loading-description"]) {
      this.root.querySelector(selector).textContent = "";
    }
    this.clearGuidance();
    for (const selector of ["#settings-grid", "#intent-mapping", "#validation-list", "#warnings-list"]) {
      this.root.querySelector(selector).replaceChildren();
    }
    this.root.querySelector("#warnings-block").hidden = true;
    for (const id of ["expression-output", "settings-copy"]) {
      this.root.querySelector(`[data-copy-target='${id}']`).disabled = true;
    }
    this.setState("empty");
  }

  showError(message) {
    this.root.querySelector("#error-message").textContent = message;
    this.setState("error");
  }

  render(result) {
    const passed = result.status === "PASS";
    const mock = result.provider === "mock";
    const label = passed ? (mock ? "모의 변환 완료" : "변환 완료") : "변환 보류";
    this.root.querySelector("#result-mode-note").textContent = mock
      ? "모의 변환 결과입니다. 실제 AI를 사용하지 않았습니다. BRAIN 시뮬레이션은 수행하지 않습니다."
      : "AI가 해석한 코드 초안입니다. BRAIN에서 직접 시뮬레이션하세요. 실행 성공이나 수익성을 확인한 결과가 아닙니다.";
    this.root.querySelector("#expression-output").textContent = result.fastExpression ||
      ["코드를 생성하지 못했습니다.", ...(result.warnings || [])].join("\n");
    this.root.querySelector("[data-copy-target='expression-output']").disabled = !passed;
    this.root.querySelector("#settings-copy").textContent = JSON.stringify(result.simulationSettings, null, 2);
    this.root.querySelector("[data-copy-target='settings-copy']").disabled = false;
    this.root.querySelector("#metric-status").textContent = label;
    this.root.querySelector("#metric-confidence").textContent = mock ? "모의 해석" : "AI 1회 해석";
    this.renderSettings(result.simulationSettings, result.settingsSource);
    this.renderValidation(result.validation);
    this.renderWarnings(result.warnings, result.unresolvedSettings);
    this.renderGuidance(result);
    const mapping = this.root.querySelector("#intent-mapping");
    mapping.replaceChildren();
    for (const item of result.intentMapping || []) {
      const row = document.createElement("li");
      row.textContent = `${item.requirement}: ${item.expression}`;
      mapping.append(row);
    }
    this.setState("content");
    this.status.textContent = label;
    if (!passed) {
      this.status.className = "result-status error";
    }
  }

  onRefine(handler) {
    this.refineHandler = handler;
  }

  clearGuidance() {
    for (const selector of ["#strategy-explanation", "#refinement-feedback"]) {
      this.root.querySelector(selector).textContent = "";
    }
    for (const selector of ["#strategy-assumptions", "#improvement-suggestions", "#refinement-options"]) {
      this.root.querySelector(selector).replaceChildren();
    }
    for (const selector of ["#strategy-explanation-block", "#refinement-block", "#improvements-block"]) {
      this.root.querySelector(selector).hidden = true;
    }
  }

  renderGuidance(result) {
    this.clearGuidance();
    if (result.status !== "PASS") return;
    const explanation = result.strategyExplanation;
    this.root.querySelector("#strategy-explanation-block").hidden = !explanation;
    this.root.querySelector("#strategy-explanation").textContent = explanation || "";
    for (const assumption of result.assumptions || []) {
      const row = document.createElement("li");
      row.textContent = assumption;
      this.root.querySelector("#strategy-assumptions").append(row);
    }
    const suggestions = result.improvementSuggestions || [];
    this.root.querySelector("#improvements-block").hidden = !suggestions.length;
    for (const suggestion of suggestions) {
      const row = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = suggestion.title;
      const detail = document.createElement("p");
      detail.textContent = `${suggestion.rationale} ${suggestion.experiment}`;
      row.append(title, detail);
      this.root.querySelector("#improvement-suggestions").append(row);
    }
    const options = result.refinementOptions || [];
    this.root.querySelector("#refinement-block").hidden = !options.length;
    for (const option of options) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "refinement-option";
      const label = document.createElement("strong");
      label.textContent = option.label;
      const description = document.createElement("span");
      description.textContent = option.description;
      button.append(label, description);
      button.addEventListener("click", () => {
        this.refineHandler?.(option, result.simulationSettings);
        this.root.querySelector("#refinement-feedback").textContent =
          `‘${option.label}’을 입력에 반영했습니다. 다시 변환하면 코드가 갱신됩니다. 현재 결과는 변경 전 전략입니다.`;
      });
      this.root.querySelector("#refinement-options").append(button);
    }
  }

  setState(state) {
    this.empty.hidden = state !== "empty";
    this.loading.hidden = state !== "loading";
    this.content.hidden = state !== "content";
    this.error.hidden = state !== "error";
    const className = state === "content" ? "pass" : state === "error" ? "error" : "waiting";
    const label = state === "loading" ? "해석 중" : state === "content" ? "변환 완료" : state === "error" ? "오류" : "대기";
    this.status.className = `result-status ${className}`;
    this.status.textContent = label;
  }

  renderSettings(settings, sources) {
    const grid = this.root.querySelector("#settings-grid");
    grid.replaceChildren();
    for (const [key, value] of Object.entries(settings)) {
      const source = sources[key] || "default";
      const displayValue = typeof value === "object" ? `${value.years}Y ${value.months}M` : value;
      const item = document.createElement("div");
      item.className = "setting-item";
      const label = document.createElement("small");
      label.textContent = SETTING_LABELS[key] || key;
      const output = document.createElement("b");
      output.textContent = displayValue;
      const badge = document.createElement("em");
      badge.className = source;
      badge.textContent = source === "default" ? "기본값" : "사용자 지정";
      item.append(label, output, badge);
      grid.append(item);
    }
  }

  renderValidation(validation) {
    const list = this.root.querySelector("#validation-list");
    list.replaceChildren();
    for (const [key, passed] of Object.entries(validation)) {
      if (key === "brainExecutionChecked" && passed == null) {
        const item = document.createElement("li");
        item.className = "unchecked";
        item.textContent = "BRAIN 실행: 미확인";
        list.append(item);
        continue;
      }
      if (passed == null) continue;
      const item = document.createElement("li");
      if (!passed) item.className = "failed";
      item.textContent = VALIDATION_LABELS[key] || key;
      list.append(item);
    }
  }

  renderWarnings(warnings = [], unresolved = []) {
    const combined = [...warnings, ...unresolved.map(value => `미해결 설정: ${value}`)];
    const block = this.root.querySelector("#warnings-block");
    const list = this.root.querySelector("#warnings-list");
    list.replaceChildren();
    block.hidden = combined.length === 0;
    for (const warning of combined) {
      const item = document.createElement("li");
      item.textContent = warning;
      list.append(item);
    }
  }

  bindCopyButtons() {
    this.root.addEventListener("click", async event => {
      const button = event.target.closest("[data-copy-target]");
      if (!button) return;
      const target = this.root.querySelector(`#${button.dataset.copyTarget}`);
      const original = button.textContent;
      try {
        await navigator.clipboard.writeText(target.textContent);
        button.textContent = "복사됨";
      } catch { button.textContent = "복사 권한을 확인하세요"; }
      setTimeout(() => { button.textContent = original; }, 1400);
    });
  }
}
