export class HarnessApi {
  constructor(endpoint = "/api/convert") {
    this.endpoint = endpoint;
    this.pending = null;
    this.generation = 0;
    this.authQueue = Promise.resolve();
  }

  clearSession() { this.generation += 1; this.pending = null; }

  assertSession(generation) {
    this.onSessionCheck?.();
    if (generation !== this.generation) throw new Error("로그인 상태가 변경됐습니다. 다시 시도하세요.");
  }

  async convert(strategy, settings = null, expectedProvider = null, trainingConsent = false, onProgress = () => {}) {
    const generation = this.generation;
    this.assertSession(generation);
    const body = JSON.stringify({strategy, settings, trainingConsent});
    if (this.pending?.body !== body) this.pending = {body, id: crypto.randomUUID()};
    const requestId = this.pending.id;
    const options = {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": requestId,
        "X-Requested-With": "brain-site",
        ...(expectedProvider ? {"X-Expected-Provider": expectedProvider} : {}),
      },
      body,
    };
    const deadline = Date.now() + 10 * 60000 + 65000;
    let response = await this.request(this.endpoint, {...options, signal: AbortSignal.timeout(65000)});
    this.assertSession(generation);
    while (response.status === 202) {
      const progress = await this.read(response);
      this.assertSession(generation);
      onProgress(progress);
      if (Date.now() >= deadline) {
        throw new Error("대기 시간이 길어졌습니다. 같은 입력으로 다시 누르면 기존 요청을 확인합니다.");
      }
      await new Promise(resolve => setTimeout(resolve, 5000));
      this.assertSession(generation);
      // Only queued jobs attempt an atomic claim. Running jobs are read-only polls.
      // Reuse the ID/body so admission and quota are never duplicated.
      response = progress.status === "queued"
        ? await this.request(this.endpoint, {...options, signal: AbortSignal.timeout(65000)})
        : await this.request(`/api/jobs/${requestId}`, {signal: AbortSignal.timeout(10000)});
      this.assertSession(generation);
    }
    let result;
    try { result = await this.read(response); }
    catch (error) {
      if (generation === this.generation && error.status) this.pending = null;
      throw error;
    }
    this.assertSession(generation);
    this.pending = null;
    return result;
  }

  async read(response) {
    let result;
    try { result = await response.json(); } catch {
      throw new Error("로그인이 만료되었거나 서버에 연결할 수 없습니다. 새로고침해 주세요.");
    }
    if (!response.ok) {
      // A terminal job failure must permit a new explicit attempt; network errors keep the ID.
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

  async provider() {
    return this.read(await this.request("/api/provider", {signal: AbortSignal.timeout(12000)}));
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
    const generation = this.generation;
    const send = async () => {
      if (body && action !== "logout") this.assertSession(generation);
      return this.read(await this.request(`/api/auth/${action}`, {
      ...(body ? {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "brain-site"}, body: JSON.stringify(body)} : {}),
      signal: AbortSignal.timeout(12000),
      }));
    };
    if (!body) return send();
    // Serialize cookie-changing requests so a late refresh cannot undo logout.
    const pending = this.authQueue.then(send);
    this.authQueue = pending.catch(() => undefined);
    return pending;
  }

  async me() {
    const generation = this.generation;
    try { return await this.auth("me"); } catch (error) {
      if (error.status !== 401) throw error;
      this.assertSession(generation);
      await this.auth("refresh", {});
      this.assertSession(generation);
      return this.auth("me");
    }
  }

  async members(status = "", query = "", cursor = null) {
    const params = new URLSearchParams({status, q: query});
    if (cursor) { params.set("before", cursor.createdAt); params.set("before_id", cursor.id); }
    return this.read(await this.request(`/api/admin/members?${params}`, {signal: AbortSignal.timeout(12000)}));
  }

  async budget() {
    return this.read(await this.request("/api/admin/budget", {signal: AbortSignal.timeout(12000)}));
  }

  async updateMember(id, status) {
    return this.read(await this.request(`/api/admin/members/${id}`, {
      method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "brain-site"},
      body: JSON.stringify({status}), signal: AbortSignal.timeout(12000),
    }));
  }
}
