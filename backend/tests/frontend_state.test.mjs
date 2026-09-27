import assert from "node:assert/strict";
import test from "node:test";
import {webcrypto} from "node:crypto";

// Exercise the actual dashboard modules without a browser, network, or API key.
class Element {
  constructor() {
    this.value = "최근 5일 수익률이 낮은 종목을 매수한다.";
    this.hidden = false;
    this.disabled = false;
    this.checked = true;
    this.children = [];
    this.textContent = "";
    this.events = new Map();
    this.classList = {add() {}, remove() {}, toggle() {}};
  }
  addEventListener(name, handler) {
    this.events.set(name, [...(this.events.get(name) || []), handler]);
  }
  async emit(name) {
    for (const handler of this.events.get(name) || []) {
      await handler({preventDefault() {}, target: this});
    }
  }
  replaceChildren() { this.children = []; }
  append(...children) { this.children.push(...children); }
  setAttribute() {}
  focus() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
}

let instance = 0;
const realState = {provider: "muse", keyConfigured: true, model: "meta/muse-spark-1.3-contributor"};
const mockState = {provider: "mock", keyConfigured: false, model: realState.model};
const response = (body, status = 200) => new Response(JSON.stringify(body), {status});

async function dashboard(t, state = realState, member = undefined, localAvailable = true) {
  const elements = new Map();
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const control = {
    state, calls: [], authCalls: [], jobCalls: [], convertResponses: [], jobResponses: [],
    member, localAvailable, stateError: null, conversionError: null,
    result: {
      status: "PASS", provider: state.provider, fastExpression: "-rank(returns)",
      confidence: null, simulationSettings: {}, settingsSource: {}, validation: {}, warnings: [],
    },
  };
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    if (url === "/api/auth/config") return response({enabled: member !== undefined, configured: true});
    if (url === "/api/auth/me") return response(control.member || {detail: "로그인하세요."}, control.member ? 200 : 401);
    if (url === "/api/admin/members") return response([{id: "member-id", email: "member@example.test", displayName: "신청자", status: "pending", role: "member"}]);
    if (url === "/api/admin/budget") return response({limitKrw: 20000, accountedKrw: 40, stopped: false});
    if (url.startsWith("/api/admin/members/")) {
      control.authCalls.push({url, options});
      return response({status: JSON.parse(options.body).status});
    }
    if (url.startsWith("/api/auth/")) {
      control.authCalls.push({url, options});
      if (url.endsWith("refresh")) return response({detail: "로그인하세요."}, 401);
      if (url.endsWith("logout")) control.member = null;
      return response({message: "이메일 인증 후 승인 대기"});
    }
    if (url === "/api/local/provider") {
      if (control.stateError) throw control.stateError;
      if (!control.localAvailable) return response({}, 404);
      return response(control.state);
    }
    if (url === "/api/provider") {
      if (control.stateError) throw control.stateError;
      return response({...control.state, localKeyEntry: false});
    }
    if (url === "/api/usage") return response({}, 404);
    if (url === "/api/convert") {
      control.calls.push(options);
      if (control.conversionError) throw control.conversionError;
      control.onConvert?.();
      if (control.convertResponses.length) {
        const [body, status] = control.convertResponses.shift();
        return response(body, status);
      }
      return response(control.result, control.status || 200);
    }
    if (url.startsWith("/api/jobs/")) {
      control.jobCalls.push({url, options});
      const [body, status] = control.jobResponses.shift();
      return response(body, status);
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  const previousDocument = globalThis.document;
  const previousFormData = globalThis.FormData;
  const previousCrypto = globalThis.crypto;
  globalThis.document = {
    querySelector: element, createElement: () => new Element(),
    body: new Element(), addEventListener() {},
  };
  globalThis.FormData = class { get() { return ""; } };
  if (!previousCrypto) globalThis.crypto = webcrypto;
  t.after(() => {
    globalThis.document = previousDocument;
    globalThis.FormData = previousFormData;
    if (!previousCrypto) delete globalThis.crypto;
  });
  await import(`../app/static/js/app.js?test=${++instance}`);
  await new Promise(resolve => setImmediate(resolve));
  return {...control, control, element, submit: () => element("#strategy-form").emit("submit")};
}

test("a restarted local server cannot silently turn an AI request into mock output", async t => {
  const ui = await dashboard(t);
  ui.control.state = mockState;
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
  assert.match(ui.element("#error-message").textContent, /API 키가 해제/);
  assert.match(ui.element("#provider-chip").textContent, /모의 모드/);
  assert.equal(ui.element("#result-error").hidden, false);
  assert.equal(ui.element("#submit-button").disabled, false);
});

test("an unavailable connection-state endpoint prevents a paid conversion request", async t => {
  const ui = await dashboard(t);
  ui.control.stateError = new TypeError("Failed to fetch");
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
  assert.match(ui.element("#error-message").textContent, /서버에 연결하지 못했습니다/);
});

test("a safe provider failure is displayed with no automatic conversion retry", async t => {
  const ui = await dashboard(t);
  const detail = "OpenAI API 잔액 또는 사용 한도가 부족합니다. API 결제·한도를 확인하세요.";
  ui.control.result = {detail};
  ui.control.status = 503;
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "muse");
  assert.equal(ui.element("#error-message").textContent, detail);
});

test("a successful AI result is rendered with the expected provider guard", async t => {
  const ui = await dashboard(t);
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "muse");
  assert.equal(ui.element("#expression-output").textContent, "-rank(returns)");
  assert.equal(ui.element("#result-content").hidden, false);
  assert.equal(ui.element("#result-status").textContent, "변환 완료");
});

test("an explicit mock request is guarded and labelled as mock", async t => {
  const ui = await dashboard(t, mockState);
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "mock");
  assert.equal(ui.element("#result-status").textContent, "모의 변환 완료");
});

test("a response with the wrong provider cannot appear as a successful AI result", async t => {
  const ui = await dashboard(t);
  ui.control.result = {...ui.control.result, provider: "mock"};
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.element("#result-content").hidden, true);
  assert.match(ui.element("#error-message").textContent, /AI 연결 상태가 변경/);
});

test("a conversion timeout does not immediately retry a potentially billable request", async t => {
  const ui = await dashboard(t);
  ui.control.conversionError = new DOMException("expired", "TimeoutError");
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.match(ui.element("#error-message").textContent, /계속 처리 중일 수/);
  assert.equal(ui.element("#submit-button").disabled, false);
});

test("Contributor consent is required before any paid request", async t => {
  const ui = await dashboard(t);
  ui.element("#training-consent").checked = false;
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
  assert.match(ui.element("#error-message").textContent, /학습 활용 안내/);
});

for (const status of [null, "pending", "rejected", "suspended"]) {
  test(`the dashboard and conversion are inaccessible for ${status || "anonymous"} users`, async t => {
    const member = status ? {status, role: "member", email: "member@example.test"} : null;
    const ui = await dashboard(t, realState, member);
    assert.equal(ui.element("#dashboard").hidden, true);
    assert.equal(ui.element("#auth-panel").hidden, false);
    assert.equal(ui.element("#member-admin-panel").hidden, true);
    assert.equal(ui.element("#open-settings").hidden, true);
    assert.equal(ui.element("#provider-chip").hidden, true);
    await ui.submit();
    assert.equal(ui.control.calls.length, 0);
  });
}

test("approved members can convert but cannot see member administration", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "member", email: "member@example.test"});
  assert.equal(ui.element("#dashboard").hidden, false);
  assert.equal(ui.element("#member-admin-panel").hidden, true);
  assert.equal(ui.element("#open-settings").hidden, true);
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(JSON.parse(ui.control.calls[0].body).trainingConsent, true);
  assert.equal(ui.element("#metric-confidence").textContent, "AI 1회 해석");
});

test("signup sends credentials once and clears the visible password", async t => {
  const ui = await dashboard(t, realState, null);
  await ui.element("#auth-signup-tab").emit("click");
  ui.element("#auth-email").value = "member@example.test";
  ui.element("#auth-password").value = "123456";
  ui.element("#auth-name").value = "신청자";
  await ui.element("#auth-form").emit("submit");
  const call = ui.control.authCalls.find(call => call.url.endsWith("signup"));
  assert.deepEqual(JSON.parse(call.options.body), {email: "member@example.test", password: "123456", displayName: "신청자"});
  assert.equal(ui.element("#auth-password").value, "");
  assert.equal(ui.element("#dashboard").hidden, true);
  assert.match(ui.element("#auth-feedback").textContent, /이메일 인증/);
});

test("an approved operator can send an explicit approval from member administration", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "admin", email: "admin@example.test"});
  assert.equal(ui.element("#member-admin-panel").hidden, false);
  assert.equal(ui.element("#open-settings").hidden, false);
  await ui.element("#open-settings").emit("click");
  assert.equal(ui.element("#provider-dialog").open, true);
  assert.equal(ui.element("#provider-form").hidden, true);
  const row = ui.element("#members-list").children[0];
  const button = row.children[1].children.find(button => button.textContent === "승인");
  await button.emit("click");
  const call = ui.control.authCalls.find(call => call.url === "/api/admin/members/member-id");
  assert.equal(JSON.parse(call.options.body).status, "approved");
  assert.equal(ui.control.calls.length, 0);
});

test("a deployed operator can manage members in settings without a local key endpoint", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "admin"}, false);
  assert.equal(ui.element("#open-settings").hidden, false);
  await ui.element("#open-settings").emit("click");
  assert.equal(ui.element("#provider-dialog").open, true);
  assert.equal(ui.element("#member-admin-panel").hidden, false);
  assert.equal(ui.element("#provider-form").hidden, true);
  assert.equal(ui.element("#disconnect-provider").hidden, true);
  assert.match(ui.element("#provider-description").textContent, /공용 키를 자동/);
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "muse");
});

test("operator settings display the cumulative budget without making a conversion", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "admin"}, false);
  await ui.element("#open-settings").emit("click");
  assert.match(ui.element("#ai-budget-status").textContent, /누적 40 \/ 20,000원/);
  assert.match(ui.element("#ai-budget-status").textContent, /보수적 계산/);
  assert.equal(ui.control.calls.length, 0);
});

test("an exhausted budget displays the stop message without automatically retrying", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "member"}, false);
  const detail = "누적 AI 비용 한도(20,000원)에 도달해 변환이 중지됐습니다.";
  ui.control.convertResponses = [[{detail}, 402]];
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.element("#error-message").textContent, detail);
  assert.equal(ui.element("#result-content").hidden, true);
  assert.equal(ui.element("#submit-button").disabled, false);
});

test("deployed members use the shared key automatically and cannot open settings", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "member"}, false);
  assert.equal(ui.element("#open-settings").hidden, true);
  assert.equal(ui.element("#member-admin-panel").hidden, true);
  await ui.element("#open-settings").emit("click");
  assert.notEqual(ui.element("#provider-dialog").open, true);
  assert.equal(ui.element("#provider-form").hidden, true);
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.element("#result-status").textContent, "변환 완료");
});

test("a deployed missing shared key prevents any conversion call", async t => {
  const ui = await dashboard(t, {...realState, keyConfigured: false}, {status: "approved", role: "member"}, false);
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
  assert.match(ui.element("#error-message").textContent, /운영자/);
  assert.equal(ui.element("#open-settings").hidden, true);
});

test("logout hides the dashboard and resets training consent", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "member", email: "member@example.test"});
  await ui.element("#auth-logout").emit("click");
  assert.equal(ui.element("#dashboard").hidden, true);
  assert.equal(ui.element("#training-consent").checked, false);
  assert.equal(ui.element("#open-settings").hidden, true);
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
});

test("queued requests show a loading screen and claim with the same ID and body", async t => {
  const realTimeout = globalThis.setTimeout;
  t.mock.method(globalThis, "setTimeout", (callback, ms, ...args) => realTimeout(callback, ms === 5000 ? 0 : ms, ...args));
  const ui = await dashboard(t, realState, {status: "approved", role: "member"});
  ui.control.convertResponses = [[{status: "queued", queuePosition: 4}, 202]];
  ui.control.onConvert = () => {
    if (ui.control.calls.length < 2) return;
    assert.equal(ui.element("#result-loading").hidden, false);
    assert.match(ui.element("#result-status").textContent, /대기열/);
    assert.match(ui.element("#loading-description").textContent, /대기 순서 4번/);
    assert.equal(ui.element("#submit-button").disabled, true);
  };
  await ui.submit();
  assert.equal(ui.control.calls.length, 2);
  assert.equal(ui.control.calls[0].body, ui.control.calls[1].body);
  assert.equal(ui.control.calls[0].headers["Idempotency-Key"], ui.control.calls[1].headers["Idempotency-Key"]);
  assert.equal(ui.control.jobCalls.length, 0);
  assert.equal(ui.element("#result-status").textContent, "변환 완료");
  assert.equal(ui.element("#submit-button").disabled, false);
});

test("a running job is only read, and a terminal error is never retried automatically", async t => {
  const realTimeout = globalThis.setTimeout;
  t.mock.method(globalThis, "setTimeout", (callback, ms, ...args) => realTimeout(callback, ms === 5000 ? 0 : ms, ...args));
  const ui = await dashboard(t, realState, {status: "approved", role: "member"});
  ui.control.convertResponses = [[{status: "queued", queuePosition: 1}, 202], [{status: "processing"}, 202]];
  ui.control.jobResponses = [[{status: "processing"}, 202], [{detail: "이전 요청이 실패했거나 만료됐습니다."}, 409]];
  await ui.submit();
  assert.equal(ui.control.calls.length, 2);
  assert.equal(ui.control.jobCalls.length, 2);
  assert.equal(ui.control.jobCalls[0].options.method, undefined);
  assert.match(ui.element("#error-message").textContent, /실패했거나 만료/);
  assert.equal(ui.element("#result-error").hidden, false);
});
