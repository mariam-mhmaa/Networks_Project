// Run with Node 18+: node test_client.mjs. No npm packages required.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {Blob} from 'node:buffer';

const base = new URL('./', import.meta.url);
const protocol = await readFile(new URL('protocol.js', base), 'utf8');
const transport = await readFile(new URL('transport.js', base), 'utf8');
const app = await readFile(new URL('app.js', base), 'utf8');
const html = await readFile(new URL('index.html', base), 'utf8');
export const results = [];
const test = async (name, fn) => { await fn(); results.push(name); };
const clone = x => JSON.parse(JSON.stringify(x));
function snapshot(seq = 1, gateway = 'gateway-test') {
  return {schema_version: 1, type: 'status', simulation: false, gateway_id: gateway, status_seq: seq, state: 'Idle', fault: null, settings: null,
    batch: {id: null, target: 0, outcome: 'none', elapsed_ms: 0}, counts: {produced: 0, inspected: 0, passed: 0, failed: 0, unresolved:0, unstarted:0, not_inspected:0},
    queue: {size: 0, capacity: 5, part_ids: [], reserved:0, full_policy:'block'}, parts: [], command_results: [],
    operator:{controller_id:'OP-tests',lease_ms:5000},ready:true,can_edit:false,can_resume:false,can_close_orphans:false,orphaned:false,control_pending:null,
    stations: {production: {connected: true, busy: false, part_id: null, remaining_ms: null}, inspection: {connected: true, busy: false, part_id: null, remaining_ms: null}}};
}
function setup() {
  let now = 0, next = 0;
  const timers = new Map(), sockets = [], calls = [], snapshots = [], states = [];
  const env = {get: snapshot(), failPosts: 0};
  class Socket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 0; sockets.push(this); }
    open() { this.readyState = 1; this.onopen?.(); }
    emit(s) { this.onmessage?.({data: JSON.stringify(s)}); }
    close() { this.readyState = 3; this.onclose?.(); }
  }
  const context = vm.createContext({URL, AbortController, location: {protocol: 'http:'}, performance: {now: () => now}, WebSocket: Socket,
    setTimeout(fn, delay) { const id = ++next; timers.set(id, {fn, when: now + delay}); return id; },
    clearTimeout(id) { timers.delete(id); },
    setInterval(fn, delay) { const id = ++next; timers.set(id, {fn, when: now + delay, repeat: delay}); return id; },
    clearInterval(id) { timers.delete(id); },
    async fetch(url, options) {
      calls.push({url, options});
      if (options.method === 'POST') {
        if (env.failPosts-- > 0) throw new Error('Lost reply');
        const body = JSON.parse(options.body);
        const reply = {schema_version: 1, gateway_id: body.gateway_id, cmd_id: body.cmd_id, command: url.split('/').pop(), accepted: true, phase: 'accepted', message: 'Accepted'};
        if (env.badAck) reply.cmd_id = 'wrong-id';
        return {ok: true, status: 202, async json() { return reply; }};
      }
      if (env.getPromise) return env.getPromise;
      return {ok: true, status: 200, async json() { return clone(env.get); }};
    }});
  vm.runInContext(protocol, context); vm.runInContext(transport, context);
  const client = new context.GatewayConnection('http://127.0.0.1:8080', {
    onConnection: (...args) => states.push(args), onSnapshot: (s, meta) => snapshots.push({s, meta})});
  return {context, client, env, sockets, calls, snapshots, states,
    async advance(ms) {
      now += ms;
      for (const [id, timer] of [...timers]) if (timer.when <= now && timers.has(id)) {
        if (timer.repeat) timer.when = now + timer.repeat; else timers.delete(id); timer.fn();
      }
      await flush();
    }};
}
async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve(); }

await test('Protocol rejects inconsistent counters, invalid rules and premature completion', () => {
  const {context, client} = setup();
  assert.doesNotThrow(() => context.ToyProtocol.snapshot(snapshot()));
  let s = snapshot(); s.counts.passed = 1;
  assert.throws(() => context.ToyProtocol.snapshot(s));
  s = snapshot(); s.stations.inspection.busy = true;
  assert.throws(() => context.ToyProtocol.snapshot(s));
  s = snapshot(); s.batch.outcome = 'completed';
  assert.throws(() => context.ToyProtocol.snapshot(s));
  assert.throws(() => context.ToyProtocol.settings({batch_size: 1, production_time_ms: 10, inspection_time_ms: 10, N: 0, K: 0}));
  client.close();
});
await test('Connect synchronizes GET snapshot, then applies buffered newer WebSocket updates', async () => {
  const h = setup(); let release;
  h.env.getPromise = new Promise(resolve => { release = resolve; });
  h.client.connect(); h.sockets[0].open(); h.sockets[0].emit(snapshot(5));
  assert.equal(h.client.live, false);
  release({ok: true, async json() { return snapshot(4); }}); await flush();
  assert.equal(h.client.live, true);
  assert.deepEqual(h.snapshots.map(x => x.s.status_seq), [4, 5]);
  h.sockets[0].emit(snapshot(3)); h.sockets[0].emit(snapshot(5));
  assert.equal(h.snapshots.length, 2);
  h.client.close();
});
await test('Stale data freezes live state; reconnect accepts fresh boot without replaying old results', async () => {
  const h = setup(); h.client.connect(); h.sockets[0].open(); await flush();
  await h.advance(3501);
  assert.equal(h.client.live, false); assert(h.states.some(([s]) => s === 'stale'));
  h.env.get = snapshot(1, 'gateway-restarted');
  await h.advance(600); assert.equal(h.sockets.length, 2);
  h.sockets[1].open(); await flush();
  assert.equal(h.client.live, true);
  assert.equal(h.snapshots.at(-1).meta.initial, true);
  assert.equal(h.snapshots.at(-1).meta.restarted, true);
  h.client.close();
});
await test('Timeout retry preserves exact command ID and body; acceptance is not completion', async () => {
  const h = setup(); h.client.connect(); h.sockets[0].open(); await flush(); h.env.failPosts = 1;
  const record = {cmd_id: 'stable-id', command: 'start', gateway_id: 'gateway-test', body: {cmd_id: 'stable-id', gateway_id: 'gateway-test'}};
  const ack = await h.client.send(record);
  const posts = h.calls.filter(c => c.options.method === 'POST');
  assert.equal(posts.length, 2); assert.equal(posts[0].options.body, posts[1].options.body);
  assert.equal(ack.phase, 'accepted'); assert.equal(h.snapshots.length, 1);
  h.env.badAck = true;
  await assert.rejects(h.client.send({...record,cmd_id:'another-id',body:{...record.body,cmd_id:'another-id'},attempts:0,serializedBody:undefined}), /Mismatched/);
  h.client.close();
});
await test('Retries retain their original attempt/deadline limits and reject altered contents', async () => {
  const h=setup();h.client.connect();h.sockets[0].open();await flush();h.env.failPosts=9;
  const r={cmd_id:'original-id',command:'pause',gateway_id:'gateway-test',body:{cmd_id:'original-id',gateway_id:'gateway-test'}};
  await assert.rejects(h.client.send(r));assert.equal(r.attempts,2);
  await assert.rejects(h.client.send(r),/budget exhausted/);assert.equal(h.calls.filter(c=>c.options.method==='POST').length,2);
  await assert.rejects(h.client.send({...r,body:{...r.body,extra:1}}),/immutable/);
  const late={...r,attempts:0,absoluteSendAt:1};await h.advance(2);
  await assert.rejects(h.client.send(late),/budget exhausted/);assert.equal(late.attempts,0);h.client.close();
});
await test('Examiner settings cover agreed arithmetic and timing bounds',()=>{
  const h=setup();const s={batch_size:64,production_time_ms:600000,inspection_time_ms:1,N:2147483647,K:-2147483648};
  assert.doesNotThrow(()=>h.context.ToyProtocol.settings(s));
  for(const extra of [{batch_size:65},{production_time_ms:600001},{inspection_time_ms:0},{N:2147483648},{K:2147483648}])assert.throws(()=>h.context.ToyProtocol.settings({...s,...extra}));
  h.client.close();
});
await test('Malformed status takes the display offline instead of accepting fabricated counters', async () => {
  const h = setup(); h.client.connect(); h.sockets[0].open(); await flush();
  const bad = snapshot(2); bad.counts.inspected = 10; h.sockets[0].emit(bad);
  assert.equal(h.client.live, false); assert.equal(h.snapshots.length, 1); h.client.close();
});
await test('Reconnect refuses a stale sequence under an unchanged gateway boot', async () => {
  const h = setup(); h.env.get = snapshot(10); h.client.connect(); h.sockets[0].open(); await flush();
  h.sockets[0].close(); h.env.get = snapshot(9); await h.advance(600);
  h.sockets[1].open(); await flush();
  assert.equal(h.client.live, false); assert.equal(h.snapshots.length, 1);
  h.client.close();
});
await test('Operator does not optimistically start work, double-click, or complete jobs when a timer reaches zero', async () => {
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]));
  for (const match of app.matchAll(/\$\('([^']+)'\)/g)) assert(ids.has(match[1]), 'Missing HTML element ' + match[1]);
  const elements = new Map(), storage = new Map(), intervals = []; let client, release, sends = 0, now = 0, effects = 0;
  function node() {
    const selectors = new Map();
    return {value: '', dataset: {}, children: [], style: {setProperty() {}}, classList: {toggle() {}, add() {}, remove() {}},
      setAttribute() {}, append(child) { this.children.push(child); }, replaceChildren(...children) { this.children = children; }, querySelectorAll() {return [];},
      querySelector(key) { if (!selectors.has(key)) selectors.set(key, node()); return selectors.get(key); }, remove() {}, click() {}};
  }
  for (const id of ids) elements.set(id, node());
  for (const [id, value] of Object.entries({quantity: '12', production: '2', inspection: '3', ruleN: '4', ruleK: '0',queueCapacity:'5',fullPolicy:'block'})) elements.get(id).value = value;
  const memory = {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)};
  class Client {
    constructor(origin, handlers) { this.base = new URL(origin).origin; this.handlers = handlers; this.gatewayId = 'gateway-test'; client = this; }
    connect() {} close() {}
    send(record) { sends++; this.record = record; return new Promise(resolve => { release = resolve; }); }
    async lookup() { return {...this.record, phase: 'accepted', result: 'Accepted', gateway_id: this.gatewayId}; }
  }
  const ctx = vm.createContext({document: {getElementById: id => elements.get(id), createElement: node, body: node()},
    localStorage: memory, sessionStorage: memory, location: {origin: 'http://127.0.0.1:8080'}, performance: {now: () => now},
    crypto: {getRandomValues: array => array.fill(7)}, Uint8Array, GatewayConnection: Client,
    toyArt: () => '<svg></svg>', clearWorkshopEffects() {}, workshopEffect() { effects++; }, workshopCelebrate() { effects++; },
    setInterval(fn) { intervals.push(fn); }, setTimeout() {}, URL, Blob});
  vm.runInContext(protocol, ctx); vm.runInContext(app, ctx);
  assert.equal(elements.get('start').disabled, true);
  client.handlers.onConnection('live'); const initial=snapshot();initial.operator.controller_id=storage.get('toy-workshop.operator');client.handlers.onSnapshot(initial, {initial: true});
  assert.equal(elements.get('start').disabled, false);
  elements.get('start').onclick(); elements.get('start').onclick();
  assert.equal(sends, 1); assert.equal(elements.get('state').textContent, 'Idle');
  assert.equal(client.record.body.production_time_ms, 2000);
  assert.equal(client.record.body.inspection_time_ms, 3000);
  const intermediate=snapshot(2);intermediate.operator=initial.operator;intermediate.command_results=[{cmd_id:client.record.cmd_id,command:'start',phase:'accepted',result:'Accepted'}];client.handlers.onSnapshot(intermediate,{initial:false});
  release({accepted: true, message: 'Accepted', cmd_id: client.record.cmd_id}); await flush();
  assert.equal(elements.get('state').textContent, 'Idle');
  assert(storage.has('toy-workshop.pending.v1'));
  vm.runInContext('pending.issued_at = Date.now() - 36001', ctx); intervals.at(-1)();
  assert.equal(JSON.parse(storage.get('toy-workshop.pending.v1')).phase, 'unknown');
  assert.equal(elements.get('start').disabled, true);
  assert.equal(elements.get('retryCommand').hidden, true);
  const s = snapshot(3);s.operator=initial.operator; s.state = 'Running';
  s.batch = {id: 'batch-test', target: 1, outcome: 'active', elapsed_ms: 100};
  s.settings = {batch_size: 1, production_time_ms: 10, inspection_time_ms: 10, N: 4, K: 0};
  s.counts.unstarted=0;s.counts.not_inspected=1;
  s.parts = [{part_id: 1, status: 'producing', produced:false, isolated:false}];
  s.stations.production = {connected: true, busy: true, part_id: 1, remaining_ms: 10, phase:'active'};
  s.command_results = [{cmd_id: client.record.cmd_id, command: 'start', phase: 'completed', result: 'Started'}];
  client.handlers.onSnapshot(s, {initial: false});
  assert.equal(storage.has('toy-workshop.pending.v1'), false);
  now = 1000; vm.runInContext('renderTimers()', ctx);
  assert.equal(elements.get('prodTime').textContent, '0.0s');
  assert.equal(elements.get('prodStatus').textContent, 'Awaiting gateway completion');
  assert.equal(elements.get('produced').textContent, '0');
  assert.equal(elements.get('state').textContent, 'Running');
  const finished = clone(s); finished.status_seq = 4; finished.state = 'Idle'; finished.batch.outcome = 'completed';
  finished.parts[0].status = 'pass'; finished.counts = {produced: 1, inspected: 1, passed: 1, failed: 0, unresolved:0, unstarted:0, not_inspected:0};
  finished.stations.production = {connected: true, busy: false, part_id: null, remaining_ms: null};
  client.handlers.onConnection('disconnected'); client.handlers.onConnection('live');
  client.handlers.onSnapshot(finished, {initial: true});
  assert.equal(effects, 0, 'Reconnect must not replay historical completion effects');
});
console.log('Passed ' + results.length + ' client/protocol checks:\n- ' + results.join('\n- '));
