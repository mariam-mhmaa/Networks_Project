/* Shared, dependency-free v1 wire validation. No clocks or inspection rules here. */
(function (root) {
  'use strict';
  const statuses = ['waiting', 'producing', 'queued', 'inspecting', 'pass', 'fail', 'stopped'];
  const assert = (condition, text) => { if (!condition) throw new Error(text); };
  const integer = (n, min = 0, max = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(n) && n >= min && n <= max;
  const identifier = value => typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value);
  function settings(s) {
    assert(s && integer(s.batch_size, 1, 1000), 'Batch size must be 1–1000 whole toys.');
    for (const key of ['production_time_ms', 'inspection_time_ms'])
      assert(integer(s[key], 1, 3600000), 'Times must be 0.001–3600 seconds, in whole milliseconds.');
    assert(integer(s.N, 1, 1000000), 'N must be a whole number from 1 to 1,000,000.');
    assert(integer(s.K, -1000000, 1000000), 'K must be a whole number from −1,000,000 to 1,000,000.');
    return s;
  }
  function commandResult(r) {
    assert(r && identifier(r.cmd_id) && ['start', 'pause', 'resume', 'stop'].includes(r.command), 'Invalid command result ID or command.');
    assert(['accepted', 'completed', 'rejected'].includes(r.phase), 'Invalid command result phase.');
    assert(typeof r.result === 'string' && r.result.length <= 1000, 'Missing command result explanation.');
    return r;
  }
  function snapshot(s) {
    assert(s && s.schema_version === 1 && s.type === 'status', 'Unsupported status schema.');
    assert(typeof s.simulation === 'boolean', 'Status must identify simulated versus hardware stations.');
    assert(identifier(s.gateway_id) && integer(s.status_seq), 'Invalid gateway identity or status sequence.');
    assert(['Idle', 'Running', 'Paused', 'Fault'].includes(s.state), 'Invalid operating state.');
    assert(s.fault === null || (typeof s.fault === 'string' && s.fault.length <= 1000), 'Invalid fault.');
    assert(s.state !== 'Fault' || !!s.fault, 'Fault state needs an explanation.');
    const b = s.batch, c = s.counts, q = s.queue;
    assert(b && integer(b.target, 0, 1000) && integer(b.elapsed_ms), 'Invalid batch.');
    assert(['none', 'active', 'completed', 'aborted'].includes(b.outcome), 'Invalid batch outcome.');
    assert((b.id === null && b.target === 0 && b.outcome === 'none') || (identifier(b.id) && b.target > 0 && b.outcome !== 'none'), 'Batch identity/outcome mismatch.');
    if (b.target) { settings(s.settings); assert(s.settings.batch_size === b.target, 'Settings and target disagree.'); }
    else assert(s.settings === null, 'No-batch settings must be null.');
    assert(c && ['produced', 'inspected', 'passed', 'failed'].every(k => integer(c[k], 0, b.target)), 'Invalid counters.');
    assert(c.passed + c.failed === c.inspected && c.inspected <= c.produced, 'Inconsistent result counters.');
    assert(q && integer(q.capacity, 1, 1000) && integer(q.size, 0, q.capacity) && Array.isArray(q.part_ids) && q.part_ids.length === q.size, 'Invalid queue.');
    assert(Array.isArray(s.parts) && s.parts.length === b.target, 'Full snapshot must include every part.');
    const byId = new Map();
    for (const p of s.parts) {
      assert(p && integer(p.part_id, 1) && statuses.includes(p.status) && !byId.has(p.part_id), 'Invalid or duplicate part.');
      byId.set(p.part_id, p);
    }
    assert(new Set(q.part_ids).size === q.size && q.part_ids.every(id => byId.get(id)?.status === 'queued'), 'Queue does not match parts.');
    const count = status => s.parts.filter(p => p.status === status).length;
    assert(count('pass') === c.passed && count('fail') === c.failed && count('queued') === q.size, 'Parts do not match counters.');
    assert(s.stations && s.stations.production && s.stations.inspection, 'Missing station status.');
    for (const [name, active] of [['production', 'producing'], ['inspection', 'inspecting']]) {
      const station = s.stations[name];
      assert(typeof station.connected === 'boolean' && typeof station.busy === 'boolean', 'Invalid station connectivity.');
      assert(station.busy ? integer(station.remaining_ms) && byId.get(station.part_id)?.status === active && count(active) === 1 : station.part_id === null && station.remaining_ms === null && count(active) === 0, 'Station activity does not match parts.');
    }
    const knownProduced = count('queued') + count('inspecting') + count('pass') + count('fail');
    assert(c.produced >= knownProduced && c.produced <= knownProduced + count('stopped'), 'Produced count does not match parts.');
    if (b.outcome === 'active') assert(['Running', 'Paused', 'Fault'].includes(s.state), 'Active batch needs an active state.');
    if (['Running', 'Paused'].includes(s.state)) assert(b.outcome === 'active', 'Operating state needs an active batch.');
    if (b.outcome === 'completed') assert(c.produced === b.target && c.inspected === b.target && s.state === 'Idle', 'Premature batch completion.');
    if (['none', 'completed', 'aborted'].includes(b.outcome)) assert(!s.stations.production.busy && !s.stations.inspection.busy, 'Ended batch still has active jobs.');
    assert(Array.isArray(s.command_results) && s.command_results.length <= 100, 'Invalid recent command results.');
    s.command_results.forEach(commandResult);
    return s;
  }
  function ack(a, cmd) {
    assert(a && a.schema_version === 1 && identifier(a.gateway_id) && a.cmd_id === cmd.cmd_id && a.command === cmd.command, 'Command response does not match the request.');
    assert(typeof a.accepted === 'boolean' && a.phase === (a.accepted ? 'accepted' : 'rejected') && typeof a.message === 'string', 'Invalid acceptance response.');
    return a;
  }
  root.ToyProtocol = {settings, snapshot, commandResult, ack, identifier};
})(globalThis);
