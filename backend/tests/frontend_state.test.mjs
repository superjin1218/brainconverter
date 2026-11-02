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
  reset() {}
  querySelector(selector) { return globalThis.document.querySelector(selector); }
}

let instance = 0;
const realState = {provider: "openai", keyConfigured: true, model: "gpt-5.4-mini"};
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
    const intercepted = await control.intercept?.(url, options);
    if (intercepted) return intercepted;
    if (url === "/api/auth/config") return response({enabled: member !== undefined, configured: true});
    if (url === "/api/auth/me") return response(control.member || {detail: "로그인하세요."}, control.member ? 200 : 401);
    if (url.startsWith("/api/admin/members?") || url === "/api/admin/members") return response({members: [{id: "member-id", email: "member@example.test", displayName: "신청자", status: "pending", role: "member", emailConfirmed: false}], nextCursor: null});
    if (url === "/api/admin/budget") return response({
      limitKrw: 20000, accountedKrw: 34, stopped: false, allowancePerAttemptKrw: 34,
      estimatedCostMicrousd: 954, attempts: 1, unconfirmedAttempts: 0,
      inputTokens: 828, outputTokens: 74, since: "2026-09-28T07:00:00Z",
    });
    if (url.startsWith("/api/admin/members/")) {
      control.authCalls.push({url, options});
      return response({status: JSON.parse(options.body).status});
    }
    if (url.startsWith("/api/auth/")) {
      control.authCalls.push({url, options});
      if (url.endsWith("refresh")) return response({detail: "로그인하세요."}, 401);
      if (url.endsWith("logout")) control.member = null;
      return response({message: "회원가입이 완료되었습니다. 바로 로그인할 수 있습니다. 운영자 승인 후 이용할 수 있습니다."});
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
  globalThis.FormData = class { get(key) { return elements.get(`[name="${key}"]`)?.value || ""; } };
  if (!previousCrypto) globalThis.crypto = webcrypto;
  t.after(() => {
    globalThis.document = previousDocument;
    globalThis.FormData = previousFormData;
    if (!previousCrypto) delete globalThis.crypto;
  });
  await import(`../app/static/js/app.js?test=${++instance}`);
  await new Promise(resolve => setImmediate(resolve));
  element("#strategy").value = "최근 5일 수익률이 낮은 종목을 매수한다.";
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
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "openai");
  assert.equal(ui.element("#error-message").textContent, detail);
});

test("a successful AI result is rendered with the expected provider guard", async t => {
  const ui = await dashboard(t);
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "openai");
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

test("catalog checks do not claim an unperformed BRAIN execution succeeded", async t => {
  const ui = await dashboard(t);
  ui.control.result.validation = {
    catalogFieldsChecked: true, fieldTypesChecked: true, brainExecutionChecked: null,
  };
  await ui.submit();
  const rows = ui.element("#validation-list").children;
  assert.match(rows[0].textContent, /필드 카탈로그 검사/);
  assert.match(rows[1].textContent, /자료형 검사/);
  assert.equal(rows[2].textContent, "BRAIN 실행: 미확인");
  assert.equal(rows[2].className, "unchecked");
});

test("draft explanations render as text and choices require a new explicit conversion", async t => {
  const ui = await dashboard(t);
  const settings = {region: "USA", universe: "TOP500", delay: 1, neutralization: "SECTOR",
    decay: 8, truncation: 0.04, nanHandling: "ON", testPeriod: {years: 2, months: 3}};
  ui.control.result = {...ui.control.result, simulationSettings: settings,
    strategyExplanation: "<script>안전한 텍스트</script> 21거래일 모멘텀 전략입니다.",
    assumptions: ["한 달을 21거래일로 해석했습니다."],
    improvementSuggestions: [{title: "기간 비교", rationale: "기간 민감도 확인", experiment: "5일과 21일 비교"}],
    refinementOptions: [{label: "반전 방향", description: "낮은 수익률을 선호합니다.", strategy: "최근 21일 수익률 기준 반전 전략."}],
  };
  await ui.submit();
  assert.match(ui.element("#strategy-explanation").textContent, /<script>/);
  assert.equal(ui.element("#strategy-assumptions").children.length, 1);
  assert.equal(ui.element("#improvement-suggestions").children.length, 1);
  const option = ui.element("#refinement-options").children[0];
  await option.emit("click");
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.element("#strategy").value, "최근 21일 수익률 기준 반전 전략.");
  assert.match(ui.element("#refinement-feedback").textContent, /변경 전 전략/);
  await ui.submit();
  assert.equal(ui.control.calls.length, 2);
  const payload = JSON.parse(ui.control.calls[1].body);
  assert.equal(payload.strategy, "최근 21일 수익률 기준 반전 전략.");
  assert.deepEqual(payload.settings, settings);
});

test("old cached and rejected results clear previous explanation and choices", async t => {
  const ui = await dashboard(t);
  ui.control.result = {...ui.control.result, strategyExplanation: "전략 설명",
    assumptions: ["기본 기간"],
    refinementOptions: [{label: "변경", description: "방향 변경", strategy: "반전 전략"}],
    improvementSuggestions: [{title: "검증", rationale: "기간 비교", experiment: "백테스트"}],
  };
  await ui.submit();
  assert.equal(ui.element("#refinement-block").hidden, false);
  ui.control.result = {status: "REJECTED", provider: "openai", simulationSettings: {},
    settingsSource: {}, validation: {}, warnings: []};
  await ui.submit();
  assert.equal(ui.element("#strategy-explanation").textContent, "");
  assert.equal(ui.element("#refinement-options").children.length, 0);
  assert.equal(ui.element("#improvement-suggestions").children.length, 0);
  assert.equal(ui.element("#refinement-block").hidden, true);
});

test("intent validation distinguishes checked plans from untested cached results", async t => {
  const ui = await dashboard(t);
  ui.control.result.validation = {compilePassed: true, intentPlanChecked: null};
  await ui.submit();
  assert.equal(ui.element("#validation-list").children.length, 1);
  ui.control.result.validation.intentPlanChecked = true;
  await ui.submit();
  let rows = ui.element("#validation-list").children;
  assert.equal(rows.length, 2);
  assert.equal(rows[1].textContent, "선호 방향·원문 근거 검사");
  assert.notEqual(rows[1].className, "failed");
  ui.control.result = {...ui.control.result, status: "REJECTED", fastExpression: null,
    validation: {compilePassed: false, intentPlanChecked: false},
    warnings: ["선호 방향과 코드의 점수 방향이 다릅니다."]};
  await ui.submit();
  rows = ui.element("#validation-list").children;
  assert.equal(rows[1].className, "failed");
  assert.match(ui.element("#expression-output").textContent, /선호 방향/);
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
  assert.deepEqual(Object.keys(JSON.parse(ui.control.calls[0].body)).sort(), ["settings", "strategy"]);
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
  assert.match(ui.element("#auth-feedback").textContent, /바로 로그인/);
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
  assert.equal(Boolean(button.disabled), false);
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
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "openai");
});

test("operator settings separate GPT token cost and reserve without making a conversion", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "admin"}, false);
  await ui.element("#open-settings").emit("click");
  assert.match(ui.element("#ai-budget-status").textContent, /예산 예약 · 34 \/ 20,000원/);
  assert.match(ui.element("#ai-budget-status").textContent, /예상 비용 \$0\.000954/);
  assert.match(ui.element("#ai-budget-status").textContent, /호출 시도 1회/);
  assert.match(ui.element("#ai-budget-status").textContent, /입력 828 · 출력 74토큰/);
  assert.equal(ui.control.calls.length, 0);
});

test("unreported GPT usage is shown separately from the known cost", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "admin"}, false);
  ui.control.intercept = async url => url === "/api/admin/budget" ? response({
    limitKrw: 20000, accountedKrw: 34, stopped: false, allowancePerAttemptKrw: 34,
    estimatedCostMicrousd: 0, attempts: 1, unconfirmedAttempts: 1,
    inputTokens: 0, outputTokens: 0, since: "2026-09-28T07:00:00Z",
  }) : undefined;
  await ui.element("#open-settings").emit("click");
  assert.match(ui.element("#ai-budget-status").textContent, /비용 미확인 1회 별도/);
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

test("logout hides the dashboard and blocks conversions", async t => {
  const ui = await dashboard(t, realState, {status: "approved", role: "member", email: "member@example.test"});
  await ui.element("#auth-logout").emit("click");
  assert.equal(ui.element("#dashboard").hidden, true);
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

test("logout erases private form, hidden results and administrator data", async t => {
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  ui.element('[name="region"]').value = "USA";
  ui.control.result.warnings = ["private warning"];
  ui.control.result.intentMapping = [{requirement: "private", expression: "secret"}];
  ui.control.result.strategyExplanation = "private explanation";
  ui.control.result.assumptions = ["private assumption"];
  ui.control.result.refinementOptions = [{label: "private choice", description: "private", strategy: "반전 전략"}];
  ui.control.result.improvementSuggestions = [{title: "private improvement", rationale: "private", experiment: "private"}];
  await ui.submit();
  await ui.element("#refinement-options").children[0].emit("click");
  ui.element("#ai-budget-status").textContent = "private budget status";
  await ui.element("#auth-logout").emit("click");
  for (const selector of ["#strategy", '[name="region"]']) assert.equal(ui.element(selector).value, "");
  for (const selector of ["#expression-output", "#settings-copy", "#error-message", "#ai-budget-status", "#strategy-explanation", "#refinement-feedback"])
    assert.equal(ui.element(selector).textContent, "");
  for (const selector of ["#intent-mapping", "#warnings-list", "#settings-grid", "#strategy-assumptions", "#refinement-options", "#improvement-suggestions"])
    assert.equal(ui.element(selector).children.length, 0);
  ui.control.member = {id: "b", status: "approved", role: "member"};
  await ui.element("#auth-refresh").emit("click");
  assert.equal(ui.element("#strategy").value, "");
  assert.equal(ui.element("#result-content").hidden, true);
});

test("same member refresh preserves draft while identity change clears it", async t => {
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  ui.element("#strategy").value = "private draft";
  await ui.element("#auth-refresh").emit("click");
  assert.equal(ui.element("#strategy").value, "private draft");
  ui.control.member = {id: "b", status: "approved", role: "member"};
  await ui.element("#auth-refresh").emit("click");
  assert.equal(ui.element("#strategy").value, "");
});

test("late conversion cannot restore private output after logout", async t => {
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  ui.control.intercept = async url => url === "/api/convert" ? gate : null;
  const pending = ui.submit();
  await new Promise(resolve => setImmediate(resolve));
  await ui.element("#auth-logout").emit("click");
  release(response(ui.control.result));
  await pending;
  assert.equal(ui.element("#expression-output").textContent, "");
  assert.equal(ui.element("#result-content").hidden, true);
});

test("session loss clears data and a late membership response cannot undo logout", async t => {
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  let release;
  ui.control.intercept = url => url === "/api/auth/me" ? new Promise(resolve => { release = resolve; }) : null;
  const refresh = ui.element("#auth-refresh").emit("click");
  await new Promise(resolve => setImmediate(resolve));
  await ui.element("#auth-logout").emit("click");
  release(response({id: "a", status: "approved", role: "member"}));
  await refresh;
  assert.equal(ui.element("#dashboard").hidden, true);
  assert.equal(ui.element("#strategy").value, "");
  ui.control.intercept = null;
  ui.control.member = {id: "b", status: "approved", role: "member"};
  await ui.element("#auth-refresh").emit("click");
  ui.element("#strategy").value = "private b";
  ui.control.member = null;
  await ui.element("#auth-refresh").emit("click");
  assert.equal(ui.element("#strategy").value, "");
});

test("queued strategy is never resubmitted after account switch", async t => {
  const realTimeout = globalThis.setTimeout;
  let wake;
  t.mock.method(globalThis, "setTimeout", (callback, ms, ...args) => {
    if (ms === 5000) { wake = callback; return 0; }
    return realTimeout(callback, ms, ...args);
  });
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  ui.control.convertResponses = [[{status: "queued", queuePosition: 1}, 202]];
  const conversion = ui.submit();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof wake, "function");
  ui.control.member = {id: "b", status: "approved", role: "member"};
  await ui.element("#auth-refresh").emit("click");
  wake();
  await conversion;
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.element("#result-content").hidden, true);
});

test("admin pagination uses cursor and resets it when search changes", async t => {
  const ui = await dashboard(t, realState, {id: "admin", status: "approved", role: "admin"});
  const urls = [];
  ui.control.intercept = url => {
    if (!url.startsWith("/api/admin/members?")) return null;
    urls.push(url);
    return response({members: [], nextCursor: {createdAt: "2026-09-27T00:00:00.123456Z", id: "old-member"}});
  };
  await ui.element("#members-refresh").emit("click");
  await ui.element("#members-next").emit("click");
  assert.equal(new URL(urls[1], "https://example.test").searchParams.get("before_id"), "old-member");
  ui.element("#members-query").value = "target";
  await ui.element("#members-next").emit("click");
  const query = new URL(urls[2], "https://example.test").searchParams;
  assert.equal(query.get("q"), "target");
  assert.equal(query.has("before_id"), false);
});

test("late administrator results cannot refill cleared member data", async t => {
  const ui = await dashboard(t, realState, {id: "admin", status: "approved", role: "admin"});
  let release;
  ui.control.intercept = url => url.startsWith("/api/admin/members?")
    ? new Promise(resolve => { release = resolve; }) : null;
  const loading = ui.element("#members-refresh").emit("click");
  await new Promise(resolve => setImmediate(resolve));
  await ui.element("#auth-logout").emit("click");
  release(response({members: [{email: "private@example.test"}], nextCursor: null}));
  await loading;
  assert.equal(ui.element("#members-list").children.length, 0);
  assert.equal(ui.element("#ai-budget-status").textContent, "");
});

test("an in-flight refresh finishes before logout and a stale 401 cannot launch a new refresh", async t => {
  const {HarnessApi} = await import("../app/static/js/api.js");
  const api = new HarnessApi();
  const calls = [];
  let release;
  t.mock.method(globalThis, "fetch", async url => {
    calls.push(url);
    if (url.endsWith("refresh")) return new Promise(resolve => { release = resolve; });
    return response({});
  });
  const refreshing = api.auth("refresh", {});
  await new Promise(resolve => setImmediate(resolve));
  const logout = api.auth("logout", {});
  api.clearSession();
  assert.equal(calls.length, 1);
  release(response({}));
  await Promise.all([refreshing, logout]);
  assert.deepEqual(calls, ["/api/auth/refresh", "/api/auth/logout"]);
  api.auth = async () => new Promise(resolve => { release = () => resolve(Promise.reject(Object.assign(new Error(), {status: 401}))); });
  const me = api.me();
  api.clearSession();
  release();
  await assert.rejects(me, /로그인 상태/);
});

function browserSession(t) {
  const previous = globalThis.window;
  const events = new Map();
  const values = new Map();
  globalThis.window = {
    location: {hash: "", search: "", pathname: "/"},
    history: {replaceState() {}},
    addEventListener: (name, callback) => events.set(name, callback),
    localStorage: {getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value)},
  };
  t.after(() => { if (previous === undefined) delete globalThis.window; else globalThis.window = previous; });
  return {change: () => values.set("brain-session-change", "another-tab-session"),
    notify: () => events.get("storage")({key: "brain-session-change"}),
    restore: () => events.get("pageshow")({persisted: true})};
}

test("a paused production provider cannot send a conversion even with a configured key", async t => {
  const ui = await dashboard(t, {...realState, conversionsEnabled: false}, {id: "a", status: "approved", role: "member"}, false);
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
  assert.match(ui.element("#provider-chip").textContent, /준비 중/);
  assert.match(ui.element("#submit-button span").textContent, /준비 중/);
});

test("the legacy link login message survives an unavailable session refresh", async t => {
  browserSession(t);
  window.location.hash = "#error=access_denied&error_code=otp_expired&error_description=dummy-secret";
  let cleared = false;
  window.history.replaceState = () => { cleared = true; };
  const ui = await dashboard(t, realState, null, false);
  assert.equal(cleared, true);
  assert.match(ui.element("#auth-feedback").textContent, /이메일과 비밀번호로 로그인/);
  assert.equal(ui.element("#auth-feedback").textContent.includes("dummy-secret"), false);
});

test("another tab's logout erases this tab's private DOM", async t => {
  const browser = browserSession(t);
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  await ui.submit();
  browser.change();
  browser.notify();
  assert.equal(ui.element("#strategy").value, "");
  assert.equal(ui.element("#expression-output").textContent, "");
  assert.equal(ui.element("#dashboard").hidden, true);
});

test("restoring a cached page clears the previous account before refreshing identity", async t => {
  const browser = browserSession(t);
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  await ui.submit();
  browser.change();
  ui.control.member = {id: "b", status: "approved", role: "member"};
  const restored = browser.restore();
  assert.equal(ui.element("#expression-output").textContent, "");
  await restored;
  assert.equal(ui.element("#strategy").value, "");
  assert.equal(ui.element("#dashboard").hidden, false);
});

test("cross-tab session marker blocks queued resubmission even before a storage event", async t => {
  const browser = browserSession(t);
  const realTimeout = globalThis.setTimeout;
  let wake;
  t.mock.method(globalThis, "setTimeout", (callback, ms, ...args) => {
    if (ms === 5000) { wake = callback; return 0; }
    return realTimeout(callback, ms, ...args);
  });
  const ui = await dashboard(t, realState, {id: "a", status: "approved", role: "member"});
  ui.control.convertResponses = [[{status: "queued", queuePosition: 1}, 202]];
  const pending = ui.submit();
  await new Promise(resolve => setImmediate(resolve));
  browser.change();
  wake();
  await pending;
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.element("#strategy").value, "");
  assert.equal(ui.element("#dashboard").hidden, true);
});

test("failed member reload removes inert rows and offers a working retry", async t => {
  const ui = await dashboard(t, realState, {id: "admin", status: "approved", role: "admin"});
  assert.equal(ui.element("#members-list").children.length, 1);
  ui.control.intercept = url => url.startsWith("/api/admin/members?") ? response({detail: "일시 오류"}, 503) : null;
  await ui.element("#members-refresh").emit("click");
  assert.equal(ui.element("#members-list").children.length, 0);
  assert.match(ui.element("#members-feedback").textContent, /새로고침/);
  ui.control.intercept = null;
  await ui.element("#members-refresh").emit("click");
  const row = ui.element("#members-list").children[0];
  await row.children[1].children.find(button => button.textContent === "승인").emit("click");
  assert.ok(ui.control.authCalls.some(call => call.url === "/api/admin/members/member-id"));
});


test("OpenAI conversion sends the fixed provider header", async t => {
  const ui = await dashboard(t, {provider: "openai", model: "gpt-5.4-mini", keyConfigured: true});
  assert.equal(ui.element("#provider-chip").textContent, "실제 AI 모드");
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
  assert.equal(ui.control.calls[0].headers["X-Expected-Provider"], "openai");
});

test("OpenAI with no key blocks conversion before the paid endpoint", async t => {
  const ui = await dashboard(t, {provider: "openai", model: "gpt-5.4-mini", keyConfigured: false});
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
  assert.match(ui.element("#error-message").textContent, /키가 설정되지/);
});


for (const mode of ["signup", "login"]) {
  for (const password of ["", "12345"]) {
    test(`${mode} rejects a short password before sending credentials`, async t => {
      const ui = await dashboard(t, realState, null);
      await ui.element(`#auth-${mode}-tab`).emit("click");
      ui.element("#auth-email").value = "member@example.test";
      ui.element("#auth-password").value = password;
      await ui.element("#auth-form").emit("submit");
      assert.equal(ui.control.authCalls.some(call => call.url.endsWith(mode)), false);
      assert.match(ui.element("#auth-feedback").textContent, /6~256자/);
      assert.equal(ui.element("#auth-password").value, "");
    });
  }
}

test("signup then login shows approval waiting and enables conversion only after approval", async t => {
  const ui = await dashboard(t, realState, null);
  await ui.element("#auth-signup-tab").emit("click");
  ui.element("#auth-email").value = "member@example.test";
  ui.element("#auth-password").value = "abcdef";
  await ui.element("#auth-form").emit("submit");
  ui.control.member = {id: "new-member", status: "pending", role: "member", email: "member@example.test"};
  ui.element("#auth-password").value = "abcdef";
  await ui.element("#auth-form").emit("submit");
  assert.equal(ui.element("#auth-waiting-card").hidden, false);
  assert.equal(ui.element("#dashboard").hidden, true);
  await ui.submit();
  assert.equal(ui.control.calls.length, 0);
  ui.control.member = {...ui.control.member, status: "approved"};
  await ui.element("#auth-refresh").emit("click");
  assert.equal(ui.element("#dashboard").hidden, false);
  await ui.submit();
  assert.equal(ui.control.calls.length, 1);
});
