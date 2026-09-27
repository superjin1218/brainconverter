export class LocalProviderPanel {
  constructor(api, onChange) {
    this.api = api;
    this.onChange = onChange;
    this.state = null;
    this.accessAllowed = false;
    this.settingsAllowed = false;
    this.allowLocalEntry = false;
    this.panel = document.querySelector("#local-provider-panel");
    this.dialog = document.querySelector("#provider-dialog");
    this.settingsButton = document.querySelector("#open-settings");
    this.form = document.querySelector("#provider-form");
    this.input = document.querySelector("#openai-api-key");
    this.feedback = document.querySelector("#provider-feedback");
    this.connectButton = document.querySelector("#connect-provider");
    this.disconnectButton = document.querySelector("#disconnect-provider");
    this.settingsButton.addEventListener("click", async () => {
      if (!this.settingsAllowed) return;
      this.feedback.textContent = "";
      this.feedback.classList.remove("failed");
      this.dialog.showModal();
      document.body.classList.add("settings-open");
      try {
        await this.refresh();
        if (!this.form.hidden && !this.input.disabled) this.input.focus();
      } catch (error) {
        this.feedback.classList.add("failed");
        this.feedback.textContent = error.message;
      }
    });
    for (const id of ["#close-settings", "#done-settings"]) {
      document.querySelector(id).addEventListener("click", () => this.dialog.close());
    }
    this.dialog.addEventListener("click", event => {
      if (event.target !== this.dialog) return;
      const bounds = this.dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) this.dialog.close();
    });
    this.dialog.addEventListener("close", () => {
      this.input.value = "";
      this.feedback.textContent = "";
      document.body.classList.remove("settings-open");
      this.settingsButton.focus();
    });
    this.form.addEventListener("submit", event => {
      event.preventDefault();
      this.change(false);
    });
    this.disconnectButton.addEventListener("click", () => this.change(true));
  }

  async start() {
    try {
      await this.refresh();
    } catch { /* The state chip shows the failure; every conversion checks again. */ }
  }

  async refresh() {
    const generation = this.api.generation;
    try {
      const local = await this.api.localProvider();
      if (generation !== this.api.generation) return null;
      if (!local && !this.accessAllowed) return null;
      const state = local ? {...local, localKeyEntry: true} : await this.api.provider();
      if (generation !== this.api.generation) return null;
      if (state) this.render(state);
      return state;
    } catch (error) {
      if (generation !== this.api.generation) return null;
      document.querySelector("#provider-chip").textContent = "연결 상태 확인 실패";
      throw error;
    }
  }

  async prepareConversion() {
    const wasConnected = this.state?.provider === "muse" && this.state.keyConfigured;
    const state = await this.refresh();
    if (!state) throw new Error("AI 연결 상태를 확인하지 못했습니다. 새로고침해 주세요.");
    const connected = state.provider === "muse" && state.keyConfigured;
    if (wasConnected && !connected) {
      this.api.pending = null;
      throw new Error("서버 재시작 또는 연결 해제로 API 키가 해제됐습니다. 운영자에게 연결 상태를 확인해 주세요. 실제 AI 변환은 실행하지 않았습니다.");
    }
    if (state.provider === "muse" && !connected) {
      throw new Error("서버에 AI 키가 설정되지 않았습니다. 운영자에게 문의하세요.");
    }
    return state.provider;
  }

  render(state) {
    this.state = state;
    this.panel.hidden = !this.settingsAllowed;
    this.settingsButton.hidden = !this.settingsAllowed;
    document.querySelector("#provider-chip").hidden = !this.accessAllowed;
    const connected = state.provider === "muse" && state.keyConfigured;
    const mock = state.provider === "mock";
    this.panel.classList.toggle("connected", connected);
    const local = state.localKeyEntry === true;
    const canEdit = local && this.allowLocalEntry;
    document.querySelector("#provider-title").textContent = local ? "로컬 AI 연결" : "AI 연결";
    document.querySelector("#provider-mode").textContent = connected ? "실제 AI · 키 설정됨" : "AI 미연결";
    document.querySelector("#provider-chip").textContent = connected ? "실제 AI 모드" : mock ? "모의 모드 · AI 미사용" : "API 키 필요";
    document.querySelector("#provider-description").textContent = local
      ? connected
        ? "이 로컬 서버에 키가 등록되어 있습니다. 키의 유효성은 실제 변환에서 확인합니다."
        : "현재 로컬 테스트 화면입니다. Vercel에 등록한 공용 키는 배포 사이트에서 자동 적용됩니다."
      : connected
        ? "서버에 등록된 공용 키를 자동으로 사용합니다. 키의 유효성은 실제 변환에서 확인합니다."
        : "서버의 AI 키 설정을 확인하세요. 저장한 환경변수는 다음 배포부터 적용됩니다.";
    document.querySelector("#submit-button span").textContent = connected ? "AI로 코드 변환" : mock ? "모의 변환해 보기" : "전략 변환하기";
    this.form.hidden = !canEdit || connected;
    this.disconnectButton.hidden = !canEdit || !connected;
    document.querySelector("#provider-key-note").hidden = !canEdit;
    document.querySelector("#training-notice").hidden = mock;
    document.querySelector("#training-consent").required = !mock;
  }

  setBusy(busy) {
    this.connectButton.disabled = busy;
    this.disconnectButton.disabled = busy;
    this.input.disabled = busy;
  }

  setAccessAllowed(allowed, settingsAllowed, allowLocalEntry = false) {
    this.accessAllowed = allowed;
    this.settingsAllowed = allowed && settingsAllowed;
    this.allowLocalEntry = allowLocalEntry;
    this.settingsButton.hidden = !this.settingsAllowed;
    this.panel.hidden = !this.settingsAllowed || !this.state;
    document.querySelector("#provider-chip").hidden = !allowed;
    if (!this.settingsAllowed && this.dialog.open) this.dialog.close();
    if (this.state) this.render(this.state);
    else if (allowed) this.refresh().catch(() => undefined);
  }

  async change(disconnect) {
    if (!this.settingsAllowed || !this.allowLocalEntry || !this.state?.localKeyEntry || this.connectButton.disabled) return;
    this.setBusy(true);
    const generation = this.api.generation;
    this.feedback.textContent = disconnect ? "연결 해제 중…" : "키 설정 중…";
    this.feedback.classList.remove("failed");
    try {
      // Clear the visible input immediately; never persist the key in browser storage.
      const pending = this.api.setLocalProvider(disconnect ? null : this.input.value.trim());
      this.input.value = "";
      const state = await pending;
      if (generation !== this.api.generation) return;
      this.api.pending = null;
      this.render({...state, localKeyEntry: true});
      this.feedback.textContent = disconnect ? "입력한 키를 해제했습니다. 현재 모의 모드입니다." : "키를 설정했습니다. 설정을 닫고 전략을 변환해 보세요.";
      this.onChange();
    } catch (error) {
      if (generation !== this.api.generation) return;
      this.feedback.classList.add("failed");
      this.feedback.textContent = error.message;
    } finally {
      if (generation === this.api.generation) {
        this.input.value = "";
        this.setBusy(false);
      }
    }
  }
}
