import {HarnessApi} from "./api.js";
import {StrategyForm} from "./form.js";
import {DashboardView} from "./view.js";
import {registerConversionTool} from "./webmcp.js";

class HarnessDashboard {
  constructor() {
    this.api = new HarnessApi();
    this.view = new DashboardView();
    this.form = new StrategyForm(
      document.querySelector("#strategy-form"),
      document.querySelector("#strategy"),
      document.querySelector("#char-count"),
      document.querySelector("#submit-button"),
    );
  }

  start() {
    this.form.onSubmit(payload => this.convert(payload).catch(() => undefined));
    registerConversionTool({form: this.form, convert: payload => this.convert(payload)});
  }

  async convert({strategy, settings}) {
    this.form.setBusy(true);
    this.view.showLoading();
    try {
      const result = await this.api.convert(strategy, settings);
      this.view.render(result);
      return result;
    } catch (error) {
      this.view.showError(error.message);
      throw error;
    } finally {
      this.form.setBusy(false);
    }
  }
}

new HarnessDashboard().start();
