export class HarnessApi {
  constructor(endpoint = "/api/convert") {
    this.endpoint = endpoint;
    this.pending = null;
  }

  async convert(strategy, settings = null, expectedProvider = null, trainingConsent = false) {
    const body = JSON.stringify({strategy, settings, trainingConsent});
    if (this.pending?.body !== body) this.pending = {body, id: crypto.randomUUID()};
    const requestId = this.pending.id;
    const response = await this.request(this.endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": requestId,
        "X-Requested-With": "brain-site",
        ...(expectedProvider ? {"X-Expected-Provider": expectedProvider} : {}),
      },
      body,
      signal: AbortSignal.timeout(65000),
    });
    if (response.status === 202) {
      const deadline = Date.now() + 65000;
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 1500));
        const poll = await this.request(`/api/jobs/${requestId}`, {signal: AbortSignal.timeout(10000)});
        if (poll.status === 202) continue;
        const result = await this.read(poll, true);
        this.pending = null;
        return result;
      }
      throw new Error("아직 처리 중입니다. 같은 입력으로 다시 누르면 기존 요청을 확인합니다.");
    }
    const result = await this.read(response, true);
    this.pending = null;
    return result;
  }

  async read(response, conversion = false) {
    let result;
    try { result = await response.json(); } catch {
      throw new Error("로그인이 만료되었거나 서버에 연결할 수 없습니다. 새로고침해 주세요.");
    }
    if (!response.ok) {
      // A terminal job failure must permit a new explicit attempt; network errors keep the ID.
      if (conversion) this.pending = null;
      const error = new Error(typeof result.detail === "string" ? result.detail : "입력과 설정을 확인하세요.");
      error.status = response.status;
      throw error;
    }
    return result;
  }

  async request(url, options) {
    try {
      return await fetch(url, options);
    } catch (error) {
      if (error.name === "TimeoutError" || error.name === "AbortError") {
        throw new Error("서버 응답 대기시간을 초과했습니다. 요청이 계속 처리 중일 수 있으므로 잠시 기다린 뒤 연결 상태를 확인하세요.");
      }
      throw new Error("서버에 연결하지 못했습니다. 서버 실행 상태와 네트워크를 확인하세요.");
    }
  }

  async usage(admin = false) {
    const response = await fetch(admin ? "/api/admin/usage" : "/api/usage");
    if (!response.ok) return null;
    return response.json();
  }

  async localProvider() {
    const response = await this.request("/api/local/provider", {signal: AbortSignal.timeout(5000)});
    if (response.status === 404 || response.status === 403) return null;
    return this.read(response);
  }

  async setLocalProvider(apiKey = null) {
    const response = await this.request("/api/local/provider", {
      method: apiKey === null ? "DELETE" : "POST",
      headers: {"Content-Type": "application/json", "X-Local-Setup": "1"},
      ...(apiKey === null ? {} : {body: JSON.stringify({apiKey})}),
      signal: AbortSignal.timeout(10000),
    });
    return this.read(response);
  }

  async auth(action, body = null) {
    return this.read(await this.request(`/api/auth/${action}`, {
      ...(body ? {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "brain-site"}, body: JSON.stringify(body)} : {}),
      signal: AbortSignal.timeout(12000),
    }));
  }

  async me() {
    try { return await this.auth("me"); } catch (error) {
      if (error.status !== 401) throw error;
      await this.auth("refresh", {});
      return this.auth("me");
    }
  }

  async members() {
    return this.read(await this.request("/api/admin/members", {signal: AbortSignal.timeout(12000)}));
  }

  async updateMember(id, status) {
    return this.read(await this.request(`/api/admin/members/${id}`, {
      method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "brain-site"},
      body: JSON.stringify({status}), signal: AbortSignal.timeout(12000),
    }));
  }
}
