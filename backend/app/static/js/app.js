import {HarnessApi} from "./api.js";
import {StrategyForm} from "./form.js";
import {DashboardView} from "./view.js";
import {registerConversionTool} from "./webmcp.js";
import {LocalProviderPanel} from "./provider.js?v=membership-access-1";
import {MembershipPanel} from "./membership.js";

class HarnessDashboard {
  constructor() {
    this.api = new HarnessApi();
    this.view = new DashboardView();
    this.membership = new MembershipPanel(this.api, () => {
      this.view.setState("empty");
      this.api.pending = null;
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
        this.membership.loadMembers().catch(error => this.membership.adminMessage(error.message));
      }
    });
    Promise.all([this.providerReady, this.authReady]).then(() => this.refreshUsage());
    document.querySelector("#refresh-usage").addEventListener("click", () => this.refreshUsage());
    document.querySelector("#refresh-admin").addEventListener("click", () => this.refreshAdmin());
  }

  async refreshUsage() {
    if (this.membership.enabled && this.membership.member?.status !== "approved") return;
    try {
      const usage = await this.api.usage();
      document.querySelector("#quota-status").textContent = usage
        ? `이번 달 ${usage.monthlyRemaining} / ${usage.monthlyLimit}회 남음 · 오늘 ${usage.dailyUsed} / ${usage.dailyLimit}회 사용`
        : this.localProvider.state?.provider === "mock"
          ? "모의 모드 · 실제 AI 호출 및 비용 없음"
          : this.localProvider.state?.keyConfigured
            ? "실제 AI 모드 · 변환 시 API 비용 발생 · 회원 한도는 배포 후 적용"
            : "API 연결 상태를 확인하세요.";
      if (usage?.admin) {
        document.querySelector("#admin-panel").hidden = false;
        await this.refreshAdmin();
      }
    } catch { document.querySelector("#quota-status").textContent = "사용량을 확인하지 못했습니다."; }
  }

  async refreshAdmin() {
    try {
      const usage = await this.api.usage(true);
      if (usage) document.querySelector("#admin-usage").textContent =
        `이번 달 ${usage.requests}회 · 통과 ${usage.passed} · 거부 ${usage.rejected} · 오류 ${usage.errors}\n` +
        `모델 비용(예약 포함) $${(usage.costMicrousd / 1000000).toFixed(3)} · p95 ${(usage.p95Ms / 1000).toFixed(1)}초\n` +
        usage.members.map(member => `${member.email}: ${member.used}회`).join("\n");
    } catch { document.querySelector("#admin-usage").textContent = "운영 현황을 불러오지 못했습니다."; }
  }

  async convert({strategy, settings}) {
    if (this.busy) throw new Error("이미 변환 중입니다.");
    this.busy = true;
    this.form.setBusy(true);
    this.localProvider.setBusy(true);
    document.querySelector("#auth-logout").disabled = true;
    this.view.showLoading();
    try {
      await this.authReady;
      this.membership.ensureApproved();
      await this.providerReady;
      const expectedProvider = await this.localProvider.prepareConversion();
      const trainingConsent = document.querySelector("#training-consent").checked;
      if (expectedProvider !== "mock" && !trainingConsent) {
        throw new Error("Contributor 모델의 학습 활용 안내에 동의해 주세요.");
      }
      const result = await this.api.convert(
        strategy, settings, expectedProvider, trainingConsent,
        progress => this.view.showLoading(progress),
      );
      if (expectedProvider && result.provider !== expectedProvider) {
        await this.localProvider.refresh();
        throw new Error("변환 중 AI 연결 상태가 변경됐습니다. 설정에서 연결 상태를 확인한 뒤 다시 시도하세요.");
      }
      this.view.render(result);
      return result;
    } catch (error) {
      if (this.membership.enabled && [401, 403].includes(error.status)) {
        await this.membership.refresh().catch(() => undefined);
      }
      this.view.showError(error.message);
      throw error;
    } finally {
      this.busy = false;
      this.form.setBusy(false);
      this.localProvider.setBusy(false);
      document.querySelector("#auth-logout").disabled = false;
      this.refreshUsage();
    }
  }
}

new HarnessDashboard().start();
