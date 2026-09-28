import {HarnessApi} from "./api.js";
import {StrategyForm} from "./form.js";
import {DashboardView} from "./view.js";
import {registerConversionTool} from "./webmcp.js";
import {LocalProviderPanel} from "./provider.js?v=policy-1";
import {MembershipPanel} from "./membership.js?v=gpt-accounting-1";

class HarnessDashboard {
  constructor() {
    this.api = new HarnessApi();
    this.view = new DashboardView();
    this.conversionSequence = 0;
    this.membership = new MembershipPanel(this.api, changed => {
      if (changed) {
        this.conversionSequence += 1;
        this.busy = false;
        this.form.clear();
        this.form.setBusy(false);
        this.view.clear();
        this.localProvider.setBusy(false);
        this.localProvider.clearFeedback();
        document.querySelector("#auth-logout").disabled = false;
      }
      const approved = !this.membership.enabled || this.membership.member?.status === "approved";
      this.localProvider.setAccessAllowed(
        approved,
        approved && (!this.membership.enabled || this.membership.member?.role === "admin"),
        !this.membership.enabled,
      );
      this.refreshUsage();
    });
    this.localProvider = new LocalProviderPanel(this.api, () => {
      this.view.setState("empty");
      this.refreshUsage();
    });
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
    this.providerReady = this.localProvider.start();
    this.authReady = this.membership.start();
    document.querySelector("#open-settings").addEventListener("click", () => {
      if (this.membership.member?.role === "admin" && this.membership.member.status === "approved") {
        return this.membership.loadMembers().catch(error => this.membership.adminMessage(error.message));
      }
    });
    Promise.all([this.providerReady, this.authReady]).then(() => this.refreshUsage());
    document.querySelector("#refresh-usage").addEventListener("click", () => this.refreshUsage());
  }

  async refreshUsage() {
    const revision = this.membership.revision;
    const admin = this.membership.member?.status === "approved" && this.membership.member.role === "admin";
    const showUsage = !this.membership.enabled || admin;
    document.querySelector("#quota-status").hidden = !showUsage;
    document.querySelector("#refresh-usage").hidden = !this.membership.enabled || !admin;
    if (!showUsage) {
      document.querySelector("#quota-status").textContent = "";
      return;
    }
    try {
      const usage = await this.api.usage();
      if (revision !== this.membership.revision) return;
      document.querySelector("#quota-status").textContent = usage
        ? `이번 달 ${usage.monthlyRemaining} / ${usage.monthlyLimit}회 남음 · 오늘 ${usage.dailyUsed} / ${usage.dailyLimit}회 사용`
        : this.localProvider.state?.provider === "mock"
          ? "모의 모드 · 실제 AI 호출 및 비용 없음"
          : this.localProvider.state?.keyConfigured
            ? "실제 AI 모드 · 변환 시 API 비용 발생 · 회원 한도는 배포 후 적용"
            : "API 연결 상태를 확인하세요.";
    } catch {
      if (revision === this.membership.revision) document.querySelector("#quota-status").textContent = "사용량을 확인하지 못했습니다.";
    }
  }

  async convert({strategy, settings}) {
    if (this.busy) throw new Error("이미 변환 중입니다.");
    const sequence = ++this.conversionSequence;
    const generation = this.api.generation;
    this.busy = true;
    this.form.setBusy(true);
    this.localProvider.setBusy(true);
    document.querySelector("#auth-logout").disabled = true;
    this.view.showLoading();
    try {
      await this.authReady;
      this.api.assertSession(generation);
      this.membership.ensureApproved();
      await this.providerReady;
      this.api.assertSession(generation);
      const expectedProvider = await this.localProvider.prepareConversion();
      this.api.assertSession(generation);
      const result = await this.api.convert(
        strategy, settings, expectedProvider,
        progress => { if (generation === this.api.generation) this.view.showLoading(progress); },
      );
      this.api.assertSession(generation);
      if (expectedProvider && result.provider !== expectedProvider) {
        await this.localProvider.refresh();
        throw new Error("변환 중 AI 연결 상태가 변경됐습니다. 설정에서 연결 상태를 확인한 뒤 다시 시도하세요.");
      }
      this.view.render(result);
      return result;
    } catch (error) {
      if (generation === this.api.generation && this.membership.enabled && [401, 403].includes(error.status)) {
        await this.membership.refresh().catch(() => undefined);
      }
      if (generation === this.api.generation) this.view.showError(error.message);
      throw error;
    } finally {
      if (sequence === this.conversionSequence) {
        this.busy = false;
        this.form.setBusy(false);
        this.localProvider.setBusy(false);
        document.querySelector("#auth-logout").disabled = false;
        this.refreshUsage();
      }
    }
  }
}

new HarnessDashboard().start();
