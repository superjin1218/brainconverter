export class MembershipPanel {
  constructor(api, onChange) {
    this.api = api;
    this.onChange = onChange;
    this.enabled = true;
    this.member = null;
    this.consentMemberKey = null;
    this.revision = 0;
    this.refreshSequence = 0;
    this.memberListSequence = 0;
    this.nextCursor = null;
    this.mode = "login";
    this.panel = document.querySelector("#auth-panel");
    this.form = document.querySelector("#auth-form");
    this.feedback = document.querySelector("#auth-feedback");
    this.submit = document.querySelector("#auth-submit");
    this.form.addEventListener("submit", event => {
      event.preventDefault();
      return this.authenticate();
    });
    for (const mode of ["login", "signup"]) {
      document.querySelector(`#auth-${mode}-tab`).addEventListener("click", () => this.setMode(mode));
    }
    document.querySelector("#auth-logout").addEventListener("click", () => this.logout());
    document.querySelector("#auth-refresh").addEventListener("click", () => this.refresh().catch(error => this.message(error.message)));
    document.querySelector("#members-refresh").addEventListener("click", () => this.loadMembers().catch(error => this.adminMessage(error.message)));
    document.querySelector("#members-next").addEventListener("click", () => this.loadMembers(true).catch(error => this.adminMessage(error.message)));
    document.querySelector("#members-status").addEventListener("change", () => this.loadMembers().catch(error => this.adminMessage(error.message)));
    if (typeof window !== "undefined") {
      this.sessionStamp = this.readSessionStamp();
      this.api.onSessionCheck = () => this.checkSessionStamp();
      window.addEventListener("storage", event => {
        if (event.key === "brain-session-change") this.checkSessionStamp();
      });
      if (typeof window.BroadcastChannel === "function") {
        this.sessionChannel = new window.BroadcastChannel("brain-session-change");
        this.sessionChannel.onmessage = () => this.externalSessionChange();
      }
      const resume = () => {
        if (!this.enabled) return;
        this.checkSessionStamp();
        return this.refresh().catch(error => this.message(error.message));
      };
      window.addEventListener("focus", resume);
      window.addEventListener("pageshow", event => { if (event.persisted) return resume(); });
      document.addEventListener("visibilitychange", () => { if (!document.hidden) return resume(); });
    }
  }

  readSessionStamp() {
    try { return window.localStorage.getItem("brain-session-change"); } catch { return null; }
  }

  checkSessionStamp() {
    if (this.readSessionStamp() !== this.sessionStamp) this.externalSessionChange();
  }

  externalSessionChange() {
    if (!this.enabled) return;
    this.sessionStamp = this.readSessionStamp();
    this.refreshSequence += 1;
    this.setMember(null, true);
    this.message("다른 창에서 로그인 상태가 변경됐습니다. 다시 로그인해 주세요.");
  }

  broadcastSessionChange() {
    if (typeof window === "undefined") return;
    // Only an opaque change marker is shared; no credentials or member data.
    try {
      this.sessionStamp = crypto.randomUUID();
      window.localStorage.setItem("brain-session-change", this.sessionStamp);
    } catch { this.sessionStamp = null; }
    this.sessionChannel?.postMessage("changed");
  }

  async start() {
    const revision = this.revision;
    try {
      const config = await this.api.auth("config");
      if (revision !== this.revision) return;
      this.enabled = config.enabled;
      if (!this.enabled) {
        this.panel.hidden = true;
        document.querySelector("#dashboard").hidden = false;
        this.onChange();
        return;
      }
      if (!config.configured) this.message("회원 시스템 설정이 아직 완료되지 않았습니다. 운영자에게 문의하세요.");
      await this.refresh();
    } catch (error) {
      if (revision !== this.revision) return;
      this.render();
      this.onChange();
      this.message(error.message);
    }
  }

  async refresh() {
    const sequence = ++this.refreshSequence;
    const revision = this.revision;
    let member = null;
    try {
      member = await this.api.me();
    } catch (error) {
      if (sequence !== this.refreshSequence || revision !== this.revision) return;
      if (error.status !== 401) {
        this.setMember(null);
        throw error;
      }
    }
    if (sequence !== this.refreshSequence || revision !== this.revision) return;
    this.setMember(member);
    if (this.member?.role === "admin" && this.member.status === "approved") await this.loadMembers();
  }

  setMember(member, force = false) {
    const key = value => value ? [value.id || value.email || "member", value.status, value.role].join(":") : "";
    const changed = force || key(member) !== key(this.member);
    this.member = member;
    if (changed) {
      this.revision += 1;
      this.api.clearSession();
      this.nextCursor = null;
      document.querySelector("#members-list").replaceChildren();
      document.querySelector("#members-next").disabled = true;
      document.querySelector("#members-status").value = "";
      document.querySelector("#members-query").value = "";
      for (const id of ["#members-feedback", "#ai-budget-status", "#admin-usage", "#quota-status"]) {
        document.querySelector(id).textContent = "";
      }
    }
    this.onChange(changed);
    this.render();
  }

  ensureApproved() {
    if (!this.enabled) return;
    if (!this.member) throw new Error("로그인한 뒤 이용하세요.");
    if (this.member.status !== "approved") throw new Error("운영자 승인 후 이용할 수 있습니다.");
  }

  setMode(mode) {
    this.mode = mode;
    document.querySelector("#auth-name-row").hidden = mode !== "signup";
    document.querySelector("#auth-name").required = mode === "signup";
    document.querySelector("#auth-password").autocomplete = mode === "signup" ? "new-password" : "current-password";
    this.submit.textContent = mode === "signup" ? "회원가입 신청" : "로그인";
    for (const value of ["login", "signup"]) {
      document.querySelector(`#auth-${value}-tab`).setAttribute("aria-pressed", String(value === mode));
    }
    this.message("");
  }

  async authenticate() {
    if (this.submit.disabled) return;
    this.submit.disabled = true;
    const mode = this.mode;
    const revision = this.revision;
    this.message(this.mode === "signup" ? "가입 신청 중…" : "로그인 중…");
    try {
      const payload = {
        email: document.querySelector("#auth-email").value.trim(),
        password: document.querySelector("#auth-password").value,
        ...(mode === "signup" ? {displayName: document.querySelector("#auth-name").value.trim()} : {}),
      };
      const result = await this.api.auth(mode, payload);
      if (revision !== this.revision) return;
      document.querySelector("#auth-password").value = "";
      if (mode === "signup") {
        this.setMode("login");
        this.message(result.message);
      } else {
        this.broadcastSessionChange();
        await this.refresh();
        this.message("");
      }
    } catch (error) {
      if (revision === this.revision) this.message(error.message);
    } finally {
      document.querySelector("#auth-password").value = "";
      this.submit.disabled = false;
    }
  }

  render() {
    const approved = this.member?.status === "approved";
    const consentMemberKey = approved && this.member.role === "member"
      ? this.member.id || this.member.email || "member"
      : null;
    // Set the member default once; keep a user's opt-out during status refreshes.
    if (consentMemberKey && consentMemberKey !== this.consentMemberKey) {
      document.querySelector("#training-consent").checked = true;
    }
    this.consentMemberKey = consentMemberKey;
    this.panel.hidden = approved;
    document.querySelector("#dashboard").hidden = !approved;
    document.querySelector("#auth-login-card").hidden = !!this.member;
    document.querySelector("#auth-waiting-card").hidden = !this.member;
    document.querySelector("#auth-logout").hidden = !this.member && !this.logoutUnconfirmed;
    document.querySelector("#account-label").textContent = this.member ? `${this.member.displayName || this.member.email} 님` : "";
    document.querySelector("#member-admin-panel").hidden = !(approved && this.member.role === "admin");
    const statuses = {pending: "운영자 승인을 기다리고 있습니다", rejected: "가입 신청이 승인되지 않았습니다", suspended: "이용이 일시 중지됐습니다"};
    document.querySelector("#auth-member-status").textContent = statuses[this.member?.status] || "운영자 승인이 필요합니다";
    document.querySelector("#auth-member-email").textContent = this.member?.email || "";
  }

  message(value) { this.feedback.textContent = value; }
  adminMessage(value) { document.querySelector("#members-feedback").textContent = value; }

  async logout() {
    this.logoutUnconfirmed = false;
    const pending = this.api.auth("logout", {});
    this.refreshSequence += 1;
    this.setMember(null, true);
    this.broadcastSessionChange();
    const revision = this.revision;
    document.querySelector("#training-consent").checked = false;
    for (const id of ["#auth-email", "#auth-name", "#auth-password"]) document.querySelector(id).value = "";
    try {
      const result = await pending;
      this.broadcastSessionChange();
      if (revision === this.revision) this.message(result.message);
    } catch {
      if (revision === this.revision) {
        this.logoutUnconfirmed = true;
        this.render();
        this.message("화면의 데이터를 지웠지만 서버 로그아웃을 확인하지 못했습니다. 다시 로그아웃을 시도하세요.");
      }
    }
  }

  async loadMembers(next = false) {
    if (this.member?.role !== "admin" || this.member.status !== "approved") return;
    const revision = this.revision;
    const sequence = ++this.memberListSequence;
    const current = () => revision === this.revision && sequence === this.memberListSequence;
    const status = document.querySelector("#members-status").value;
    const query = document.querySelector("#members-query").value;
    const filter = JSON.stringify([status, query]);
    const cursor = next && filter === this.memberFilter ? this.nextCursor : null;
    document.querySelector("#members-next").disabled = true;
    const budgetLabel = document.querySelector("#ai-budget-status");
    try {
      const budget = await this.api.budget();
      if (!current()) return;
      budgetLabel.textContent = `${budget.stopped ? "AI 변환 중지" : "AI 비용 한도"} · 누적 ${budget.accountedKrw.toLocaleString()} / ${budget.limitKrw.toLocaleString()}원 (보수적 계산)`;
    } catch {
      if (!current()) return;
      budgetLabel.textContent = "AI 비용 한도를 확인하지 못했습니다. 운영 설정을 확인하세요.";
    }
    let page;
    try { page = await this.api.members(status, query, cursor); }
    catch (error) {
      if (current()) {
        document.querySelector("#members-list").replaceChildren();
        this.adminMessage(`${error.message} 새로고침으로 다시 조회하세요.`);
      }
      return;
    }
    if (!current()) return;
    const members = page.members;
    this.memberFilter = filter;
    this.nextCursor = page.nextCursor;
    document.querySelector("#members-next").disabled = !this.nextCursor;
    const list = document.querySelector("#members-list");
    list.replaceChildren();
    this.adminMessage("");
    if (!members.length) this.adminMessage("가입 신청이 없습니다.");
    if (page.limited) this.adminMessage("현재 목록은 최근 200명 범위입니다. 오래된 회원까지 조회하려면 전체 회원 조회 업데이트가 필요합니다.");
    const labels = {pending: "승인 대기", approved: "승인됨", rejected: "거절됨", suspended: "이용 중지"};
    for (const member of members) {
      const row = document.createElement("article");
      row.className = "member-row";
      const info = document.createElement("div");
      const name = document.createElement("b");
      name.textContent = `${member.displayName || "회원"} · ${labels[member.status] || member.status}${member.emailConfirmed === false ? " · 이메일 미인증" : ""}`;
      const email = document.createElement("small");
      email.textContent = member.email;
      info.append(name, email);
      row.append(info);
      if (member.role !== "admin") {
        const actions = document.createElement("div");
        actions.className = "member-actions";
        for (const [status, label] of [["approved", "승인"], ["rejected", "거절"], ["suspended", "이용 중지"]]) {
          if (status === member.status) continue;
          const button = document.createElement("button");
          button.type = "button";
          button.className = "copy-button";
          button.textContent = label;
          button.disabled = status === "approved" && member.emailConfirmed === false;
          button.addEventListener("click", async () => {
            if (!current()) return;
            button.disabled = true;
            try {
              await this.api.updateMember(member.id, status);
              if (current()) await this.loadMembers();
            } catch (error) { if (current()) this.adminMessage(error.message); }
            finally { button.disabled = false; }
          });
          actions.append(button);
        }
        row.append(actions);
      }
      list.append(row);
    }
  }
}
