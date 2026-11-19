/* Validated full snapshots; every result comes from the gateway/station. */
(function(root){
  'use strict';
  const actions=['start','pause','resume','stop','configure','reconcile','continue','recover_a','recover_b','close_orphans'];
  const phases=['received','accepted','completed','rejected','unresolved'];
  const assert=(ok,text)=>{if(!ok)throw new Error(text);};
  const integer=(n,min=0,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(n)&&n>=min&&n<=max;
  const identifier=n=>typeof n==='string'&&/^[A-Za-z0-9_:-]{1,96}$/.test(n);
  function settings(s){
    assert(s&&integer(s.batch_size,1,64),'Batch size must be 1–64 whole parts.');
    for(const k of ['production_time_ms','inspection_time_ms'])assert(integer(s[k],1,600000),'Times must be 0.001–600 seconds in whole milliseconds.');
    assert(integer(s.N,1,2147483647),'N must be a positive signed 32-bit integer.');
    assert(integer(s.K,-2147483648,2147483647),'K must be a signed 32-bit integer.');return s;
  }
  function commandResult(r){assert(r&&identifier(r.cmd_id)&&actions.includes(r.command)&&phases.includes(r.phase)&&typeof r.result==='string','Invalid command result');return r;}
  function snapshot(s){
    assert(s&&s.schema_version===1&&s.type==='status'&&typeof s.simulation==='boolean','Invalid status schema');
    assert(identifier(s.gateway_id)&&integer(s.status_seq),'Invalid gateway identity/sequence');
    assert(['Idle','Running','Paused','Fault'].includes(s.state),'Invalid operating state');
    assert(s.fault===null||typeof s.fault==='string','Invalid Fault');assert(s.state!=='Fault'||!!s.fault,'Fault needs a reason');
    const b=s.batch,c=s.counts,q=s.queue;
    assert(b&&integer(b.target,0,64)&&integer(b.elapsed_ms)&&['none','active','completed','incomplete'].includes(b.outcome),'Invalid batch');
    assert(b.id===null?b.target===0&&b.outcome==='none':identifier(b.id)&&b.target>0,'Invalid batch identity');
    if(s.settings!==null){settings(s.settings);assert(s.settings.batch_size===b.target,'Target/settings mismatch');}
    assert(c&&['produced','inspected','passed','failed','unresolved','unstarted','not_inspected'].every(k=>integer(c[k],0,b.target)),'Invalid counts');
    assert(c.passed+c.failed===c.inspected&&c.inspected<=c.produced&&c.not_inspected===b.target-c.inspected,'Conflicting result counts');
    assert(q&&integer(q.capacity,1,64)&&integer(q.size,0,q.capacity)&&integer(q.reserved,0,q.capacity)&&['block','fault'].includes(q.full_policy),'Invalid queue');
    assert(Array.isArray(q.part_ids)&&q.part_ids.length===q.size&&Array.isArray(s.parts)&&s.parts.length<=b.target,'Invalid part inventory');
    const statuses=['waiting','not_started','producing','queued','inspecting','pass','fail','unresolved','uninspected'];
    const ids=new Map();
    for(const p of s.parts){assert(p&&integer(p.part_id,1,4294967295)&&!ids.has(p.part_id)&&statuses.includes(p.status)&&typeof p.produced==='boolean'&&typeof p.isolated==='boolean','Invalid part');ids.set(p.part_id,p);}
    assert(new Set(q.part_ids).size===q.size&&q.part_ids.every(id=>ids.get(id)?.status==='queued'),'Queue/parts mismatch');
    assert(s.parts.filter(p=>p.status==='pass').length===c.passed&&s.parts.filter(p=>p.status==='fail').length===c.failed,'Verdict/parts mismatch');
    for(const name of ['production','inspection']){
      const st=s.stations?.[name];assert(st&&typeof st.connected==='boolean'&&typeof st.busy==='boolean','Invalid station');
      assert(st.busy?integer(st.part_id,1,4294967295)&&ids.has(st.part_id)&&(st.remaining_ms===null||integer(st.remaining_ms)):st.part_id===null&&st.remaining_ms===null,'Invalid station job');
    }
    assert(Array.isArray(s.command_results)&&s.command_results.length<=100,'Invalid command history');s.command_results.forEach(commandResult);
    assert(s.operator&&(s.operator.controller_id===null||identifier(s.operator.controller_id))&&integer(s.operator.lease_ms,1),'Invalid operator liveness');
    if(b.outcome==='completed')assert(c.inspected===b.target&&s.state==='Idle','Premature batch completion');
    return s;
  }
  function ack(a,cmd){assert(a&&a.schema_version===1&&identifier(a.gateway_id)&&a.cmd_id===cmd.cmd_id&&a.command===cmd.command,'Mismatched command acknowledgement');assert(typeof a.accepted==='boolean'&&a.phase===(a.accepted?'accepted':'rejected')&&typeof a.message==='string','Invalid acceptance');return a;}
  root.ToyProtocol={settings,snapshot,commandResult,ack,identifier,actions};
})(globalThis);
