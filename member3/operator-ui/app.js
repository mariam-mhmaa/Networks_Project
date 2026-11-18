'use strict';
const $ = id => document.getElementById(id);
const fields = ['quantity', 'production', 'inspection', 'ruleN', 'ruleK'];
const queueFields=['queueCapacity','fullPolicy'];
let operatorId=sessionStorage.getItem('toy-workshop.operator');
if(!operatorId){operatorId='OP-'+[...crypto.getRandomValues(new Uint8Array(16))].map(n=>n.toString(16).padStart(2,'0')).join('');sessionStorage.setItem('toy-workshop.operator',operatorId);}
let commandSession=[...crypto.getRandomValues(new Uint8Array(16))].map(n=>n.toString(16).padStart(2,'0')).join(''),commandCounters={};
let connection = null, status = null, receivedAt = 0, live = false, commandBusy = false;
let pending = null, logRows = [], stage = 'disconnected', lastInputBatch = null;
const storageKey = 'toy-workshop.pending.v1';
try { pending = JSON.parse(sessionStorage.getItem(storageKey) || 'null'); }
catch { $('feedback').textContent = 'Saved command could not be read. Check gateway status before starting work.'; }

function message(text, error = false) { $('feedback').textContent = readableText(text); $('feedback').classList.toggle('error', error); }
function displayId(id) {
  const match=/^(.*)-(GW|OP)-([0-9a-f]{32})-(\d+)$/.exec(id||'');
  if(!match)return id||'';
  const alias=status?.session_labels?.[match[2]+':'+match[3]];
  return `${match[1]}-${match[2]}-${alias||'session pending'}-${Number(match[4])}`;
}
function readableText(value) {
  return String(value??'').replace(/[A-Za-z_]+-(?:GW|OP)-[0-9a-f]{32}-\d+/g,displayId)
    .replace(/BATCH-GW-[0-9a-f]{32}/g,id=>id===status?.batch.id?status.batch.display_id:'Saved batch')
    .replace(/(?:GW|OP)-[0-9a-f]{32}/g,'Gateway/operator session');
}
function log(event, text, id = '') {
  logRows.unshift({time: new Date().toLocaleTimeString(), event, text, id}); logRows = logRows.slice(0, 100);
  $('commandLog').replaceChildren(...logRows.map(row => {
    const line = document.createElement('li');
    line.textContent = readableText(`${row.time} · ${row.event} · ${row.text}${row.id ? ' [' + displayId(row.id) + ']' : ''}`);
    return line;
  }));
}
function persist(record) {
  if (record) sessionStorage.setItem(storageKey, JSON.stringify(record)); else sessionStorage.removeItem(storageKey);
  pending = record;
}
function readSettings() {
  if (fields.some(id => !$(id).value.trim())) throw new Error('Please fill in every setting.');
  const pt = Number($('production').value) * 1000, it = Number($('inspection').value) * 1000;
  if (Math.abs(pt - Math.round(pt)) > 1e-6 || Math.abs(it - Math.round(it)) > 1e-6) throw new Error('Use at most three decimal places for seconds.');
  return ToyProtocol.settings({batch_size: Number($('quantity').value), production_time_ms: Math.round(pt), inspection_time_ms: Math.round(it), N: Number($('ruleN').value), K: Number($('ruleK').value)});
}
function renderControls(){
  const owns=status?.operator.controller_id===operatorId;
  const locked=!live||!owns||commandBusy||!!pending||!!status?.control_pending;
  const active=status?.batch.outcome==='active';
  $('start').disabled=locked||status?.state!=='Idle'||!status?.ready||status?.orphaned;
  $('pause').disabled=locked||status?.state!=='Running';
  $('resume').disabled=locked||!status?.can_resume;
  $('stop').disabled=locked||!active;
  const edit=live&&owns&&!commandBusy&&!pending&&!status?.control_pending&&(!active||status.can_edit);
  fields.forEach(id=>$(id).disabled=!edit);
  queueFields.forEach(id=>$(id).disabled=!edit||active);
  $('minus').disabled=$('plus').disabled=!edit||active;
  $('quantity').disabled=!edit||active;
  $('applySettings').disabled=locked||!status?.can_edit;
  $('connect').disabled=commandBusy;
  $('retryCommand').hidden=true; // Exhausted mutations are recovered by lookup, never renewed.
  $('checkCommand').hidden=!pending||!live;
  $('dismissCommand').hidden=!pending||!live||pending.phase!=='unknown';
  $('pendingNotice').hidden=!pending;
  $('pendingNotice').textContent=pending?`Command ${pending.command}: ${pending.phase} · ${displayId(pending.cmd_id)}`:'';
  $('recoveryBox').hidden=status?.state!=='Fault'&&!status?.stations.production.restarted&&!status?.stations.inspection.restarted;
  for(const id of ['reconcile','continue','endBatch'])$(id).disabled=locked||!active;
  $('continue').disabled=locked||!active||!!status?.configuration_hold;
  $('recoverA').hidden=!status?.stations.production.restarted;
  $('recoverB').hidden=!status?.stations.inspection.restarted;
  $('recoverA').disabled=$('recoverB').disabled=locked;
  $('closeOrphans').hidden=!status?.orphaned;
  $('closeOrphans').disabled=locked||!status?.can_close_orphans;
  $('recoveryHelp').textContent=status?.state==='Idle'?'A station has already restarted. Confirm restarted A/B reconnects to its new idle boot before the next Start; it does not reboot the ESP or repeat parts.':status?.orphaned?'A station retains work from a previous gateway session. Wait for idle stations, then close the old scopes.':status?.configuration_hold?'Settings were not confirmed by both stations. End this batch before starting new work.':'Check saved results first. If an ESP restarted, Confirm restarted A/B verifies its new idle boot; then end the old batch before a new Start. Missing results remain unresolved. Continue remaining requires safe isolation.';
}
function updateMotion() {
  const making=live&&status?.stations.production.busy&&status.stations.production.phase==='active';
  const checking=live&&status?.stations.inspection.busy&&status.stations.inspection.phase==='active';
  const factory = $('factory');
  factory.classList.toggle('making', !!making); factory.classList.toggle('checking', !!checking);
  factory.classList.toggle('moving', !!making || !!checking); factory.classList.toggle('running', !!making || !!checking);
  document.body.classList.toggle('batch-still', !making && !checking);
  const toy = $('machineToy'), id = checking ? status.stations.inspection.part_id : null;
  if (toy.dataset.toy !== String(id)) { toy.dataset.toy = String(id); toy.innerHTML = id === null ? '' : toyArt(id - 1); }
}
function renderParts() {
  const toys = status?.parts.slice(0, 200) || [];
  const identity = (status?.gateway_id || '') + '/' + (status?.batch.id || '');
  if ($('parts').dataset.batch !== identity) { $('parts').replaceChildren(); $('parts').dataset.batch = identity; }
  const existing = new Map([...$('parts').children].map(node => [node.dataset.id, node]));
  const labels = {unresolved:'UNRESOLVED',uninspected:'NOT INSPECTED',not_started:'NOT STARTED',waiting: 'WAITING', producing: 'MAKING', queued: 'QUEUED', inspecting: 'CHECKING', pass: 'PASS ✓', fail: 'FAIL ×', stopped: 'STOPPED'};
  for (const p of toys) {
    const id = String(p.part_id); let node = existing.get(id);
    if (!node) {
      node = document.createElement('div'); node.dataset.id = id;
      node.innerHTML = toyArt(p.part_id - 1) + '<span class="toy-name"></span><strong></strong><small></small>';
      node.querySelector('.toy-name').textContent = p.part_id % 2 ? 'KITTY CAT' : 'PUPPY';
      node.querySelector('strong').textContent = id.padStart(2, '0'); $('parts').append(node);
    }
    if (node.dataset.status !== p.status) { node.className = 'part toy-card ' + p.status; node.dataset.status = p.status; }
    node.title = 'Part ' + id + ': ' + p.status+(p.isolated?' · safely isolated, original outcome unresolved':''); node.querySelector('small').textContent = p.isolated?'ISOLATED':labels[p.status];
    existing.delete(id);
  }
  for (const node of existing.values()) node.remove();
  $('parts').querySelectorAll('.placeholder').forEach(n=>n.remove());
  for(let i=status?.parts.length||0;i<(status?.batch.target||0);i++){
    const node=document.createElement('div');node.className='part toy-card placeholder';
    node.innerHTML=toyArt(i)+'<span class="toy-name">UNSTARTED</span><strong></strong><small>NO PART ID YET</small>';
    node.querySelector('strong').textContent='Slot '+(i+1);$('parts').append(node);
  }
  $('partLimit').textContent = status?.parts.length > 200 ? `Showing the first 200 of ${status.parts.length} toys. Counters include the full batch.` : '';
}
function render() {
  const fresh = live ? 'Live' : status ? 'Historical / not live' : 'Waiting for gateway';
  if (live && status) {
    $('gatewayState').textContent = status.simulation ? 'Test gateway live' : 'Gateway live';
    $('connectionReason').textContent = status.simulation ? 'Test gateway: stations and verdicts are simulated' : 'HTTP commands · WebSocket status';
  }
  if(live&&status?.operator.controller_id&&status.operator.controller_id!==operatorId) $('connectionReason').textContent='View only - another operator panel holds control';
  $('state').textContent = status ? status.state + (status.control_pending?' · '+({stop:'Stopping',configure:'Applying settings',completing_batch:'Closing batch'}[status.control_pending]||status.control_pending):'') + (live ? '' : ' · stale') : 'Not connected';
  $('state').dataset.state = live && status ? status.state : 'stale';
  for (const key of ['produced', 'inspected', 'passed', 'failed','unresolved','unstarted','not_inspected']) $(key).textContent = status ? String(status.counts[key]) : '—';
  $('outcome').textContent = status ? `${fresh} · Batch ${status.batch.outcome}` : 'No gateway status yet';
  $('batchLabel').textContent = status?.batch.id ? '/ ' + (status.batch.display_id||'Current batch') : '/ No batch';
  $('batchLabel').title=status?.batch.id?(status.batch.display_id||'Current batch'):'';
  $('faultMessage').hidden = !status?.fault; $('faultMessage').textContent = status?.fault || '';
  const q = status?.queue;
  const queueDrawing = q ? Array.from({length: Math.min(q.capacity, 20)}, (_, i) => '<div class="mini ' + (i < q.size ? 'filled' : '') + '"></div>').join('') : '';
  if ($('queueBoxes').innerHTML !== queueDrawing) $('queueBoxes').innerHTML = queueDrawing;
  $('queueText').textContent = q ? `${q.size} / ${q.capacity} toys${q.capacity > 20 ? ' (20 slots shown)' : ''}` : 'No queue status';
  const pct = status?.batch.target ? status.counts.inspected / status.batch.target * 100 : 0;
  $('bar').style.width = pct + '%'; $('progress').setAttribute('aria-valuenow', Math.round(pct));
  for (const [name, id] of [['production', 'stationA'], ['inspection', 'stationB']]) {
    const station = status?.stations[name]; $(id).textContent = `Station ${name === 'production' ? 'A' : 'B'} · ${!station ? 'unknown' : station.connected ? 'connected' : 'disconnected'}${status?.simulation ? ' · simulated' : ''}${live ? '' : ' · stale'}`;
  }
  renderParts(); renderControls(); updateMotion(); renderTimers();
}
function renderTimers() {
  const age = Math.max(0, performance.now() - receivedAt);
  $('freshness').textContent = status ? `Last fresh status ${Math.floor(age / 1000)}s ago${live ? '' : ' · values frozen'}` : 'Awaiting a complete gateway snapshot';
  for (const [name, ring, time, caption] of [['production', 'prodRing', 'prodTime', 'prodStatus'], ['inspection', 'inspectRing', 'inspectTime', 'inspectStatus']]) {
    const station = status?.stations[name], total = status?.settings?.[name + '_time_ms'];
    // Cosmetic countdown estimate only. It never changes a job, counter or verdict.
    const remain = station?.busy&&station.remaining_ms!==null ? Math.max(0,station.remaining_ms-(live?age:0)) : null;
    $(ring).style.setProperty('--pct', station?.busy && total && remain!==null ? Math.min(100, Math.max(0, 1 - remain / total) * 100) + '%' : '0%');
    $(time).textContent = remain !== null ? (remain / 1000).toFixed(1) + 's' : '—';
    $(caption).textContent = !station ? 'Awaiting status' : !live ? 'Status stale · frozen' : !station.connected ? 'Device disconnected' : station.busy&&remain===null?'Request sent · awaiting evidence':station.busy ? (remain === 0 ? 'Awaiting gateway completion' : `Toy ${station.part_id} · ${name === 'production' ? 'making' : 'checking'}`) : status.state === 'Fault'?'Fault · dispatch held':status.state === 'Paused' ? 'Paused · no new work' : name === 'production' && status.queue.size === status.queue.capacity ? 'Queue full · waiting' : 'Ready';
  }
  const ms = status ? status.batch.elapsed_ms + (live && status.batch.outcome === 'active' && status.state !== 'Fault' ? age : 0) : 0;
  $('elapsed').textContent = status ? String(Math.floor(ms / 60000)).padStart(2, '0') + ':' + String(Math.floor(ms / 1000) % 60).padStart(2, '0') : '—:—';
}
function completePending(r) {
  if (!pending || r.cmd_id !== pending.cmd_id || r.command !== pending.command || pending.gateway_id !== status?.gateway_id) return;
  if (['received','accepted'].includes(r.phase)) {
    if (pending.phase === 'unknown' && Date.now()-(pending.issued_at||0)>(pending.completion_window_ms||35000)) return;
    if (pending.phase !== 'accepted') { persist({...pending,phase:r.phase,completion_window_ms:r.completion_window_ms||pending.completion_window_ms||35000}); log(r.phase==='accepted'?'Acceptance':'Receipt', r.result, r.cmd_id); }
  } else {
    log(r.phase === 'completed'?'Completion':r.phase==='unresolved'?'Unresolved':'Rejected',r.result,r.cmd_id);
    message(r.result,r.phase!=='completed');persist(null);
  }
  renderControls();
}
function applySnapshot(s, meta) {
  const previous = status; status = s; receivedAt = performance.now();
  if (meta.initial) {
    clearWorkshopEffects(); log('Synchronized', `${s.gateway_display_id||'Gateway'}, sequence ${s.status_seq}`);
    if (pending && (pending.gateway_id !== s.gateway_id || pending.gateway_base !== connection.base)) {
      persist({...pending, phase: 'unknown'}); message('Gateway changed. Previous command outcome is unknown. Review current status before clearing the notice.', true);
    }
  }
  if (s.batch.id && s.settings && (s.batch.id !== lastInputBatch || pending?.command==='configure')) {
    lastInputBatch = s.batch.id;
    $('quantity').value = s.settings.batch_size; $('production').value = s.settings.production_time_ms / 1000;
    $('inspection').value = s.settings.inspection_time_ms / 1000; $('ruleN').value = s.settings.N; $('ruleK').value = s.settings.K;
  }
  render();
  // Do not replay effects for historical results after reconnecting or reloading.
  if (!meta.initial && previous?.gateway_id === s.gateway_id && previous.batch.id === s.batch.id && s.state !== 'Fault') {
    const old = new Map(previous.parts.map(p => [p.part_id, p.status])); let budget = 6;
    for (const p of s.parts) {
      const before = old.get(p.part_id);
      if (!before || before === p.status || budget <= 0) continue;
      if (before === 'producing' && ['queued', 'inspecting', 'pass', 'fail'].includes(p.status)) {
        workshopEffect('puff', p.part_id - 1); workshopEffect('toy-flight', p.part_id - 1); budget--;
      }
      if (['pass', 'fail'].includes(p.status) && budget > 0) {
        workshopEffect(p.status === 'pass' ? 'quality-pass' : 'quality-fail', p.part_id - 1);
        const card = [...$('parts').children].find(node => node.dataset.id === String(p.part_id));
        if (card) { const cls = p.status === 'pass' ? 'just-passed' : 'just-failed'; card.classList.add(cls); setTimeout(() => card.classList.remove(cls), 900); }
        budget--;
      }
    }
    if (previous.batch.outcome !== 'completed' && s.batch.outcome === 'completed') workshopCelebrate();
  }
  s.command_results.forEach(completePending);
  if(meta.initial&&!pending&&!s.control_pending&&s.state==='Idle'&&s.batch.outcome==='none')message('Gateway connected. Both stations are ready when their indicators show connected. Earlier batches are in Batch history.');
  if(!pending&&!commandBusy&&!s.control_pending&&['completed','incomplete'].includes(s.batch.outcome)) {
    message(`${s.batch.display_id||'Batch'} ${s.batch.outcome}: ${s.counts.passed} PASS, ${s.counts.failed} FAIL, ${s.counts.unresolved} unresolved, ${s.counts.not_inspected} not inspected.${s.history_error?' History warning: '+s.history_error:''}`,!!s.history_error);
  }
  if (meta.initial && pending && pending.gateway_id === s.gateway_id) checkPending();
}
function onConnection(next, reason) {
  const changed = next !== stage; stage = next; live = next === 'live';
  $('gatewayState').textContent = ({live: 'Gateway live', syncing: 'Synchronizing', connecting: 'Connecting', stale: 'Status stale', disconnected: 'Disconnected'})[next];
  $('gatewayPill').dataset.state = next; $('connectionReason').textContent = reason || 'HTTP commands · WebSocket status';
  if (!live) { clearWorkshopEffects(); if (changed) log('Connection', reason || next); }
  render();
}
function connect() {
  try {
    const target = $('gatewayAddress').value.trim() || location.origin;
    const next = new GatewayConnection(target, {onConnection,onSnapshot:applySnapshot,operatorId});
    connection?.close(); connection = next; status = null; lastInputBatch = null;
    selectedReport=null;$('historyDownload').disabled=true;$('historySelect').replaceChildren();$('historyResults').replaceChildren();
    $('historyMessage').textContent='Open Batch history or press Refresh history to choose a saved batch.';
    try { localStorage.setItem('toy-workshop.gateway', next.base); } catch { /* Connection still works without remembered preferences. */ }
    connection.connect();
    message(pending ? 'Restoring an unresolved command. Waiting for current gateway status.' : 'Connecting to the workshop gateway…');
  } catch (error) { message(error.message, true); }
}
async function dispatch(record) {
  commandBusy = true; renderControls();
  try {
    const ack = await connection.send(record, attempt => log('Sending', `${record.command}, attempt ${attempt}/2`, record.cmd_id));
    log('Delivery', 'Matching HTTP response received; this is not work completion.', record.cmd_id);
    if (!pending || pending.cmd_id !== record.cmd_id) return;
    if (!ack.accepted) { log('Rejected', ack.message, ack.cmd_id); persist(null); message(ack.message, true); }
    else { persist({...pending,phase:'accepted',completion_window_ms:ack.completion_window_ms||35000}); log('Acceptance', ack.message, ack.cmd_id); message(ack.message + ' Waiting for gateway completion.'); checkPending(); }
  } catch (error) {
    if (pending?.cmd_id === record.cmd_id) {
      persist({...pending, phase: 'unknown'}); message('Command outcome unknown: ' + error.message + '. Use read-only Check command and review current status.', true);
      log('Uncertain', error.message, record.cmd_id);
    }
  } finally { commandBusy = false; renderControls(); }
}
function command(name) {
  if (!live || pending || commandBusy) return;
  try {
    commandCounters[name]=(commandCounters[name]||0)+1;
    const cmd_id=`${name.toUpperCase()}-OP-${commandSession}-${String(commandCounters[name]).padStart(6,'0')}`;
    const body={schema_version:1,gateway_id:status.gateway_id,operator_id:operatorId,cmd_id};
    if(name==='start')Object.assign(body,readSettings(),{queue_capacity:Number($('queueCapacity').value),full_policy:$('fullPolicy').value});
    else {body.batch_id=status.batch.id;if(name==='configure')Object.assign(body,readSettings());}
    const record = {cmd_id, command: name, body, gateway_id: status.gateway_id, gateway_base: connection.base, phase: 'pending', issued_at: Date.now()};
    persist(record); message(`Sending ${name}…`); dispatch(record);
  } catch (error) { message(error.message, true); }
}
async function checkPending() {
  if (!pending || !live) return;
  const record = pending, client = connection;
  try {
    if (record.gateway_id !== client.gatewayId || record.gateway_base !== client.base) throw new Error('Different gateway session; old work cannot be safely retried.');
    const reply = await client.lookup(record.cmd_id);
    if (client !== connection || pending?.cmd_id !== record.cmd_id) return;
    if (reply.gateway_id !== record.gateway_id) throw new Error('Gateway restarted.');
    ToyProtocol.commandResult(reply); completePending(reply);
  } catch (error) {
    if (pending?.cmd_id === record.cmd_id) { persist({...pending, phase: 'unknown'}); message('Cannot confirm command: ' + error.message + '. Review status before clearing the notice.', true); renderControls(); }
  }
}
for (const name of ['start','pause','resume','stop','reconcile','continue']) $(name).onclick = () => command(name);
$('connect').onclick=connect;
$('applySettings').onclick=()=>command('configure');
$('endBatch').onclick=()=>command('stop');
$('recoverA').onclick=()=>command('recover_a');
$('recoverB').onclick=()=>command('recover_b');
$('closeOrphans').onclick=()=>command('close_orphans');
$('retryCommand').onclick=()=>message('The original retry budget is fixed. Use Check command for read-only recovery.',true);
$('checkCommand').onclick = checkPending;
$('dismissCommand').onclick = () => {
  if (!pending || !live || pending.phase !== 'unknown' || commandBusy) return;
  log('Acknowledged', 'Operator cleared an unknown outcome after reviewing the current snapshot.', pending.cmd_id);
  persist(null); message('Notice cleared. Current gateway state still controls available actions.'); renderControls();
};
for (const [id, delta] of [['minus', -1], ['plus', 1]]) $(id).onclick = () => { $('quantity').value = Math.max(1, Math.min(64, Number($('quantity').value) + delta)); };
$('downloadLog').onclick = () => {
  const blob = new Blob([JSON.stringify(logRows, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = 'operator-browser-log.json';document.body.append(link);link.click();link.remove();setTimeout(() => URL.revokeObjectURL(url), 1000);
};
let historyOffset=0, historyNext=null, selectedReport=null;
function downloadSelectedReport() {
  if(!connection||!selectedReport||selectedReport.batch.id!==$('historySelect').value){
    $('historyMessage').textContent='Select a saved batch and wait for its summary before downloading.';return;
  }
  const name=selectedReport.batch.display_id.toLowerCase().replace(' ','-')+'.json';
  const a=document.createElement('a');a.href=connection.base+'/api/history/'+encodeURIComponent(selectedReport.batch.id)+'?download=true';
  a.download=name;document.body.append(a);a.click();a.remove();
  $('historyMessage').textContent=`Requested ${name}. Check your browser Downloads. This file contains the selected batch's results and technical evidence for both stations.`;
}
async function loadHistory(offset=0) {
  if(!connection){$('historyMessage').textContent='Connect to the gateway before loading saved batches.';return;}
  const client=connection;
  selectedReport=null;$('historyDownload').disabled=true;
  try {
    $('historyMessage').textContent='Loading saved batches...';
    const page=await client.json('/api/history?offset='+offset);
    if(client!==connection)return;
    historyOffset=offset;historyNext=page.next_offset;
    $('historySelect').replaceChildren(...page.items.map(item=>{
      const option=document.createElement('option');option.value=item.batch.id;
      option.textContent=`${item.batch.display_id} - ${item.batch.outcome} - ${item.counts.passed??'?'} PASS / ${item.counts.failed??'?'} FAIL`;
      return option;
    }));
    $('historyPrevious').disabled=offset===0;$('historyNext').disabled=historyNext===null;
    $('historyPages').hidden=page.total<=20;
    $('historyMessage').textContent=page.total?`Saved batches ${offset+1}-${offset+page.items.length} of ${page.total}. Viewing history never changes current work.`:'No saved batches yet.';
    if(page.items.length){$('historySelect').value=page.items[0].batch.id;await selectHistory();}
    else {$('historyResults').replaceChildren();selectedReport=null;$('historyDownload').disabled=true;}
  } catch(error){$('historyMessage').textContent='History unavailable: '+error.message;}
}
function observationTimes(evidence, received='received_observed_at', accepted='accepted_observed_at', completed='completed_observed_at') {
  const values=[evidence?.[received],evidence?.[accepted],evidence?.[completed]],known=values.filter(v=>typeof v==='number');
  const origin=known.length?Math.min(...known):0;
  return values.map(v=>typeof v==='number'?`+${Math.round((v-origin)*1000)} ms`:'Not observed');
}
function timingReference(evidence) {
  const stages=[['Received','received_observed_at'],['Accepted','accepted_observed_at'],['Completed','completed_observed_at']];
  const known=stages.filter(([,key])=>typeof evidence?.[key]==='number').sort((a,b)=>evidence[a[1]]-evidence[b[1]]);
  return known.length?known[0][0]:'No reply observed';
}
function operationName(op) {
  const action=op.command||op.request?.type||op.result?.action||op.id.split('-')[0];
  return ({start:'Start batch',pause:'Pause dispatch',resume:'Resume batch',stop:'End batch',configure:'Apply settings',
    reconcile:'Check saved results',continue:'Continue remaining parts',recover_a:'Confirm restarted A',recover_b:'Confirm restarted B',close_orphans:'Close old station runs',
    CFG:'Apply settings',CONFIGURE:'Apply settings',PROD:'Produce part',PRODUCE:'Produce part',INSP:'Inspect part',INSPECT:'Inspect part',
    CLOSE:'Close station batch',QUERY:'Check a saved result',RETIRE:'Isolate an uncertain part'})[action]||readableText(action);
}
function operationDetails(op) {
  const r=op.recovered_result||op.result, result=r&&typeof r==='object'?r:{},e=op.evidence||{};
  const entries=[['ID',op.display_id||displayId(op.id)],['Action',operationName(op)],
    ['Station',op.station==='A'?'A - production':op.station==='B'?'B - inspection':'Gateway / operator control']];
  const part=op.request?.part_id??result.part_id;
  if(part!==undefined)entries.push(['Part',part]);
  entries.push(['Outcome',op.phase]);
  if(result.verdict)entries.push(['Inspection verdict',result.verdict]);
  if(result.config_version!==undefined)entries.push(['Settings revision',result.config_version]);
  const settings=result.settings||op.request||{};
  for(const [key,label] of [['production_time_ms','Production time'],['inspection_time_ms','Inspection time'],['N','Rule N'],['K','Rule K']]){
    if(settings[key]!==undefined)entries.push([label,key.endsWith('_ms')?`${settings[key]} ms`:settings[key]]);
  }
  if(result.elapsed_ms!==undefined)entries.push(['Device-reported execution time',`${result.elapsed_ms} ms`]);
  if(typeof r==='string')entries.push([op.command==='start'?'Start result recorded at the time':'Control result',r]);
  if(op.reason||op.recovery_note)entries.push(['Recovery / explanation',op.recovery_note||op.reason]);
  entries.push(['Timing starts at',timingReference(e)]);
  const times=observationTimes(e);['Received','Accepted','Completed'].forEach((label,i)=>entries.push([label,times[i]]));
  const established={RECEIVED:'Received acknowledgement',ACCEPTED:'Accepted acknowledgement',COMPLETED:'Completion reply',QUERY_COMPLETED:'Completed result recovered by a read-only query'};
  for(const [key,label] of [['delivery_established_by','Delivery confirmed by'],['acceptance_established_by','Acceptance confirmed by']]){
    if(e[key])entries.push([label,established[e[key]]||e[key]]);
  }
  if(e.request_attempts!==undefined)entries.push(['Original request attempts',e.request_attempts],['Recovery queries',e.query_attempts]);
  if(op.target_id)entries.push(['Query target',displayId(op.target_id)]);
  return entries.map(([label,value])=>[label,readableText(value)]);
}
async function selectHistory() {
  const client=connection,id=$('historySelect').value;
  if(!client||!id)return;
  selectedReport=null;$('historyDownload').disabled=true;
  try {
    const report=await client.json('/api/history/'+encodeURIComponent(id));
    if(client!==connection||id!==$('historySelect').value)return;
    selectedReport=report;$('historyDownload').disabled=false;
    const summary=document.createElement('p'),c=report.counts;
    summary.textContent=`${report.batch.display_id}: ${report.batch.outcome}. ${c.produced??'?'} produced, ${c.inspected??'?'} inspected; ${c.passed??'?'} PASS, ${c.failed??'?'} FAIL; ${c.unresolved??'?'} unresolved, ${c.unstarted??'?'} not started, ${c.not_inspected??'?'} not inspected.`;
    const explanation=document.createElement('p');
    explanation.textContent='Each row has its own clock. "Timing starts at" names the first reply observed for that row (+0 ms); the other times count from that reply, not from the batch start or request send. "Not observed" means that acknowledgement was missing. Device execution time is listed separately in Details. Short IDs are used on screen; the downloaded report preserves original identities for technical checks.';
    const table=document.createElement('table'),head=document.createElement('tr');
    for(const text of ['Operation','Station','Part','Outcome','Timing starts at','Received','Accepted','Completed','Attempts / queries','Details']){const th=document.createElement('th');th.textContent=text;head.append(th);}
    table.append(head);
    const rows=[...report.controls.map(r=>({id:r.cmd_id,display_id:r.display_id,command:r.command,phase:r.phase,
      result:r.result,evidence:{received_observed_at:r.received_at,accepted_observed_at:r.accepted_at,completed_observed_at:r.completed_at}})),...report.operations];
    for(const op of rows){
      const row=document.createElement('tr'),e=op.evidence;
      const result=op.recovered_result||op.result;
      const verdict=result&&typeof result==='object'?result.verdict:null;
      const operation=document.createElement('td'),name=document.createElement('strong'),identity=document.createElement('small');
      name.textContent=operationName(op);identity.textContent=op.display_id||displayId(op.id);operation.append(name,identity);row.append(operation);
      for(const text of [op.station||'Gateway',op.request?.part_id??result?.part_id??'-',op.phase+(verdict?' / '+verdict:''),timingReference(e),...observationTimes(e),e?.request_attempts===undefined?(op.target_id?'Recovery query':'Gateway control'):`${e.request_attempts} / ${e.query_attempts}`]){
        const cell=document.createElement('td');cell.textContent=text;row.append(cell);
      }
      const cell=document.createElement('td'),details=document.createElement('details'),label=document.createElement('summary');label.textContent='Details';details.append(label);
      const list=document.createElement('dl');
      for(const [key,value] of operationDetails(op)){const term=document.createElement('dt'),description=document.createElement('dd');term.textContent=key;description.textContent=value;list.append(term,description);}
      details.append(list);cell.append(details);row.append(cell);table.append(row);
    }
    const wrap=document.createElement('div');wrap.className='history-table';wrap.append(table);
    const parts=document.createElement('p');parts.textContent='Parts: '+report.parts.map(p=>`${p.part_id}: ${p.status.toUpperCase()}${p.isolated?' (isolated)':''}`).join('; ');
    $('historyResults').replaceChildren(summary,parts,explanation,wrap);
  } catch(error){$('historyMessage').textContent='Batch unavailable: '+error.message;}
}
$('historyRefresh').onclick=()=>loadHistory(0);
$('historyPrevious').onclick=()=>loadHistory(Math.max(0,historyOffset-20));
$('historyNext').onclick=()=>{if(historyNext!==null)loadHistory(historyNext);};
$('historySelect').onchange=selectHistory;
$('historyDownload').onclick=downloadSelectedReport;
$('historyPanel').ontoggle=()=>{if($('historyPanel').open)loadHistory(0);};
$('toyShelf').innerHTML = [0, 1, 0].map(toyArt).join('');
try { $('gatewayAddress').value = localStorage.getItem('toy-workshop.gateway') || location.origin; } catch { $('gatewayAddress').value = location.origin; }
render(); connect(); setInterval(renderTimers, 100);
setInterval(() => {
  if (pending?.phase !== 'accepted' || !live) return;
  if (Date.now()-(pending.issued_at||0)>(pending.completion_window_ms||35000)) {
    persist({...pending, phase: 'unknown'});
    message('Command accepted, but completion is overdue. Check its outcome before issuing new work.', true);
    log('Completion timeout', 'No terminal application result within its original bounded response window.', pending.cmd_id);
    renderControls();
  } else checkPending();
}, 2000);
