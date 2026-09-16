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
  consensusPassed: "Agent 합의",
  sourceRequirementsPreserved: "원문 요구 보존",
  compilePassed: "FASTEXPR 컴파일",
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

  showLoading() {
    this.setState("loading");
  }

  showError(message) {
    this.root.querySelector("#error-message").textContent = message;
    this.setState("error");
  }

  render(result) {
    this.root.querySelector("#expression-output").textContent = result.fastExpression;
    this.root.querySelector("#metric-status").textContent = result.status;
    this.root.querySelector("#metric-confidence").textContent = `${Math.round(result.confidence * 100)}%`;
    this.renderSettings(result.simulationSettings, result.settingsSource);
    this.renderValidation(result.validation);
    this.renderWarnings(result.warnings, result.unresolvedSettings);
    this.setState("content");
  }

  setState(state) {
    this.empty.hidden = state !== "empty";
    this.loading.hidden = state !== "loading";
    this.content.hidden = state !== "content";
    this.error.hidden = state !== "error";
    const className = state === "content" ? "pass" : state === "error" ? "error" : "waiting";
    const label = state === "loading" ? "해석 중" : state === "content" ? "PASS" : state === "error" ? "ERROR" : "대기";
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
      if (!passed) continue;
      const item = document.createElement("li");
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
      await navigator.clipboard.writeText(target.textContent);
      const original = button.textContent;
      button.textContent = "복사됨";
      setTimeout(() => { button.textContent = original; }, 1400);
    });
  }
}

