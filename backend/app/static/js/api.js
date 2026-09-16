export class HarnessApi {
  constructor(endpoint = "/api/convert") {
    this.endpoint = endpoint;
  }

  async convert(strategy, settings = null) {
    const response = await fetch(this.endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({strategy, settings}),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "서버 응답을 확인할 수 없습니다.");
    }
    if (result.status !== "PASS") {
      throw new Error((result.warnings || []).join(" ") || "검증을 통과하지 못했습니다.");
    }
    return result;
  }
}

