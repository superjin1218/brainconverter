export class MembershipPanel {
  constructor(api, onChange) {
    this.api = api;
    this.onChange = onChange;
    this.enabled = true;
    this.member = null;
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
  }

  async start() {
    try {
      const config = await this.api.auth("config");
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
      this.render();
      this.onChange();
      this.message(error.message);
    }
  }

  async refresh() {
    try {
      this.member = await this.api.me();
    } catch (error) {
      this.member = null;
      if (error.status !== 401) {
        this.render();
        this.onChange();
        throw error;
      }
    }
    this.render();
    this.onChange();
    if (this.member?.role === "admin" && this.member.status === "approved") await this.loadMembers();
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
    this.message(this.mode === "signup" ? "가입 신청 중…" : "로그인 중…");
    try {
      const payload = {
        email: document.querySelector("#auth-email").value.trim(),
        password: document.querySelector("#auth-password").value,
        ...(mode === "signup" ? {displayName: document.querySelector("#auth-name").value.trim()} : {}),
      };
      const result = await this.api.auth(mode, payload);
      document.querySelector("#auth-password").value = "";
      if (mode === "signup") {
        this.setMode("login");
        this.message(result.message);
      } else {
        await this.refresh();
        this.message("");
      }
    } catch (error) {
      this.message(error.message);
    } finally {
      document.querySelector("#auth-password").value = "";
      this.submit.disabled = false;
    }
  }

  render() {
    const approved = this.member?.status === "approved";
    this.panel.hidden = approved;
    document.querySelector("#dashboard").hidden = !approved;
    document.querySelector("#auth-login-card").hidden = !!this.member;
    document.querySelector("#auth-waiting-card").hidden = !this.member;
    document.querySelector("#auth-logout").hidden = !this.member;
    document.querySelector("#account-label").textContent = this.member ? `${this.member.displayName || this.member.email} 님` : "";
    document.querySelector("#member-admin-panel").hidden = !(approved && this.member.role === "admin");
    const statuses = {pending: "운영자 승인을 기다리고 있습니다", rejected: "가입 신청이 승인되지 않았습니다", suspended: "이용이 일시 중지됐습니다"};
    document.querySelector("#auth-member-status").textContent = statuses[this.member?.status] || "운영자 승인이 필요합니다";
    document.querySelector("#auth-member-email").textContent = this.member?.email || "";
  }

  message(value) { this.feedback.textContent = value; }
  adminMessage(value) { document.querySelector("#members-feedback").textContent = value; }

  async logout() {
    try {
      await this.api.auth("logout", {});
      this.member = null;
      this.api.pending = null;
      document.querySelector("#training-consent").checked = false;
      document.querySelector("#members-list").replaceChildren();
      this.render();
      this.onChange();
    } catch (error) { this.message(error.message); }
  }

  async loadMembers() {
    const members = await this.api.members();
    const list = document.querySelector("#members-list");
    list.replaceChildren();
    this.adminMessage("");
    if (!members.length) this.adminMessage("가입 신청이 없습니다.");
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
            button.disabled = true;
            try {
              await this.api.updateMember(member.id, status);
              await this.loadMembers();
            } catch (error) { this.adminMessage(error.message); }
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
