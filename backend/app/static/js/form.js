const NUMERIC_FIELDS = new Set(["delay", "decay", "truncation"]);
const SETTINGS_FIELDS = [
  "region",
  "universe",
  "delay",
  "neutralization",
  "decay",
  "truncation",
];

export class StrategyForm {
  constructor(form, strategyInput, charCount, submitButton) {
    this.form = form;
    this.strategyInput = strategyInput;
    this.charCount = charCount;
    this.submitButton = submitButton;
    this.refinementSettings = null;
    this.strategyInput.addEventListener("input", () => this.updateCount());
    this.updateCount();
  }

  onSubmit(handler) {
    this.form.addEventListener("submit", async event => {
      event.preventDefault();
      await handler(this.payload());
    });
  }

  payload() {
    const formData = new FormData(this.form);
    const settings = {...(this.refinementSettings || {})};
    for (const key of SETTINGS_FIELDS) {
      const value = formData.get(key);
      if (value === "" || value == null) {
        delete settings[key];
        continue;
      }
      settings[key] = NUMERIC_FIELDS.has(key) ? Number(value) : value;
    }
    return {
      strategy: this.strategyInput.value.trim(),
      settings: Object.keys(settings).length ? settings : null,
    };
  }

  setStrategy(strategy) {
    this.strategyInput.value = strategy.trim();
    this.updateCount();
  }

  clear() {
    this.refinementSettings = null;
    this.form.reset();
    this.setStrategy("");
    for (const name of SETTINGS_FIELDS) this.form.querySelector(`[name="${name}"]`).value = "";
  }

  applyRefinement(option, settings) {
    this.refinementSettings = {...settings};
    this.setStrategy(option.strategy);
    for (const name of SETTINGS_FIELDS) {
      this.form.querySelector(`[name="${name}"]`).value = settings[name] ?? "";
    }
    this.strategyInput.focus();
  }

  setBusy(isBusy) {
    this.submitButton.disabled = isBusy;
  }

  updateCount() {
    this.charCount.textContent = `${this.strategyInput.value.length.toLocaleString()} / 2,000`;
  }
}
