// Offline execution of the real panel script against a small DOM boundary.
// This checks rendered content and requests; it is not a browser/layout test.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const created = [];
class Element {
  constructor(tag = '#text', text = '') { this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.ownText = text; this.open = false; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; this.ownText = ''; }
  setAttribute(k, v) { this.attrs[k] = v; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(k, v) { this.listeners[k] = v; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  get textContent() { return this.ownText + this.children.map(n => n.textContent).join(''); }
  set textContent(v) { this.ownText = String(v); this.children = []; }
  set innerHTML(_) { throw new Error('Untrusted material must remain text'); }
}
const nodes = new Map();
const document = {
  hidden: false, activeElement: { tagName: 'BODY' },
  querySelector(s) { if (!nodes.has(s)) nodes.set(s, new Element('div')); return nodes.get(s); },
  querySelectorAll() { return []; },
  createElement(t) { created.push(t); return new Element(t); },
  createTextNode(v) { return new Element('#text', String(v)); },
};
const calls = [];
const fixture = {
  request: { id: 'synthetic-request', state: 'succeeded', recorded_at: '2026-11-10T00:00:00Z', model_config_id: 'synthetic-model-config' },
  input: { available: true, value: { context_mode: 'fresh_request', input: { last_field: 'whole-input-sentinel' } } },
  features: [{ name: '人格', items: [{ field: 'vector', state: 'provided', value: { zero: 0, flag: false, known_null: null } }] }],
  provider_invocations: [{ available: true, value: { messages: [{ role: 'user', content: 'actual-wire-sentinel <img src=x onerror=bad()>' }] } }],
  attempts: [{ attempt_no: 1, state: 'succeeded', model: 'synthetic', sent_at: '2026-11-10T00:00:01Z', finished_at: '2026-11-10T00:00:02Z', error_code: null }],
  results: [{ received_at: '2026-11-10T00:00:02Z', validation_state: 'valid', acceptance: 'accepted', response: { available: true, value: { sentinel: 'whole-output-sentinel' } }, parsed_output: { available: true, value: { action: 'wait' } }, validation_errors: [] }],
  behavior_decisions: [{ probability: 0, selected: false }], usage: [{ input_tokens: 0, output_tokens: null }], pinned_model_configuration: { model: 'synthetic' },
};
const sandbox = {
  document, Node: Element, URLSearchParams, AbortController, DOMException,
  setInterval() { return 0; }, clearInterval() {}, setTimeout() { return 0; }, clearTimeout() {},
  fetch: async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => structuredClone(fixture) }; },
  console, fixture,
};
vm.createContext(sandbox);
const root = path.resolve(__dirname, '../..');
vm.runInContext(fs.readFileSync(path.join(root, 'digital_life/web/app.js'), 'utf8'), sandbox);
async function main() {
  vm.runInContext('rendered = renderThoughtDetail(fixture)', sandbox);
  const text = sandbox.rendered.textContent;
  for (const s of ['whole-input-sentinel', 'actual-wire-sentinel', 'whole-output-sentinel', '调用尝试与状态', 'false', 'null', '"zero": 0']) assert.ok(text.includes(s), s);
  assert.ok(!created.includes('img'));
  assert.equal(calls.length, 0);
  vm.runInContext("state.token='fixture-only-token'; pending=openThoughtDetail('id /?', 'activity')", sandbox);
  await sandbox.pending;
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/v1/thoughts/id%20%2F%3F');
  assert.equal(calls[0].options.method, 'GET');
  assert.equal(calls[0].options.headers.Authorization, 'Bearer fixture-only-token');
  assert.ok(!nodes.get('#dialog').textContent.includes('fixture-only-token'));
  sandbox.unavailable = structuredClone(fixture);
  sandbox.unavailable.input = { available: false, value: null, reason: 'retention-unavailable' };
  sandbox.unavailable.provider_invocations = [{ available: false, reason: 'wire-unavailable' }];
  sandbox.unavailable.features = [{ name: '认知', items: [{ field: 'value', state: 'unavailable' }] }];
  sandbox.unavailable.attempts = []; sandbox.unavailable.results = []; sandbox.unavailable.usage = [];
  vm.runInContext('unavailableRendered = renderThoughtDetail(unavailable)', sandbox);
  for (const s of ['retention-unavailable', 'wire-unavailable', '原始输入不可用', '没有用量记录；不估算为0']) assert.ok(sandbox.unavailableRendered.textContent.includes(s), s);
  assert.ok(!sandbox.unavailableRendered.textContent.includes('actual-wire-sentinel'));
  assert.equal(calls.length, 1); // Displaying stored records never dispatches a model.
  console.log(JSON.stringify({ passed: true, checks: ['complete snapshots and actual wire', 'zero/false/null', 'text-only untrusted content', 'encoded authenticated GET', 'unavailable and unknown states', 'no model dispatch'], browser_layout_verified: false, real_model_calls: 0, instance_access: false }));
}
main().catch(e => { console.error(e); process.exitCode = 1; });
