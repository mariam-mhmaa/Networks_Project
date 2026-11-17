(function (root) {
  'use strict';
  class GatewayConnection {
    constructor(base, handlers = {}) {
      const url = new URL(base);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash)
        throw new Error('Use a gateway origin such as http://192.168.137.1:8080 (no path or credentials).');
      if (location.protocol === 'https:' && url.protocol === 'http:') throw new Error('An HTTPS page requires an HTTPS/WSS gateway. Use same-origin hosting on the gateway.');
      this.base = url.origin; this.handlers = handlers; this.closed = false;
      this.generation = 0; this.backoff = 500; this.gatewayId = null; this.sequence = -1;
      this.lastReceived = 0; this.live = false; this.connectionState = 'disconnected';
      this.watchdog = setInterval(() => {
        if (this.live && performance.now() - this.lastReceived > 3500) {
          this.setState('stale', 'No fresh status for 3.5 seconds.');
          this.ws?.close();
        }
      }, 250);
    }
    setState(state, reason = '') {
      this.live = state === 'live'; this.connectionState = state;
      this.handlers.onConnection?.(state, reason);
    }
    connect() {
      if (this.closed) return;
      const generation = ++this.generation;
      this.setState('connecting', 'Waiting for a fresh complete status.');
      const url = new URL('/ws/status', this.base); url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = this.ws = new WebSocket(url);
      let first = true, synced = false, syncing = false, buffer = [];
      const accept = (raw, initial = false) => {
        const s = ToyProtocol.snapshot(raw);
        if (initial && s.gateway_id === this.gatewayId && s.status_seq <= this.sequence)
          throw new Error('Synchronization returned an old sequence under the same gateway boot.');
        if (!initial && s.gateway_id !== this.gatewayId) throw new Error('Gateway identity changed inside a connection.');
        if (!initial && s.status_seq <= this.sequence) return;
        const restarted = this.gatewayId !== null && this.gatewayId !== s.gateway_id;
        this.gatewayId = s.gateway_id; this.sequence = s.status_seq;
        this.lastReceived = performance.now(); this.backoff = 500;
        this.setState('live'); this.handlers.onSnapshot?.(s, {initial, restarted});
      };
      const synchronize = async () => {
        if (syncing) return; syncing = true;
        try {
          const s = await this.json('/api/status');
          if (this.closed || generation !== this.generation || ws.readyState !== WebSocket.OPEN) return;
          // The GET response and buffered WS snapshots belong to the same boot.
          const ordered = buffer.filter(item => item.gateway_id === s.gateway_id).sort((a,b) => a.status_seq-b.status_seq);
          accept(s, true); first = false; synced = true;
          for (const item of ordered) accept(item);
          buffer = [];
        } catch (error) {
          if (generation !== this.generation || this.closed) return;
          this.setState('stale', 'Cannot synchronize: ' + error.message); ws.close();
        }
      };
      ws.onopen = () => {
        if (generation !== this.generation) return;
        this.setState('syncing', 'Connected; fetching current status.'); synchronize();
      };
      ws.onmessage = event => {
        if (generation !== this.generation || this.closed) return;
        try {
          const s = ToyProtocol.snapshot(JSON.parse(event.data));
          if (!synced) { buffer.push(s); if (buffer.length > 100) throw new Error('Too many unsynchronized updates.'); return; }
          accept(s, first); first = false;
        } catch (error) {
          this.setState('stale', 'Invalid gateway status: ' + error.message); ws.close();
        }
      };
      ws.onerror = () => ws.close();
      const deadline = setTimeout(() => { if (!synced && generation === this.generation) ws.close(); }, 6000);
      ws.onclose = () => {
        clearTimeout(deadline);
        if (this.closed || generation !== this.generation) return;
        this.setState('disconnected', 'Connection lost. Displayed data is historical.');
        this.reconnectTimer = setTimeout(() => this.connect(), this.backoff);
        this.backoff = Math.min(this.backoff * 2, 8000);
      };
    }
    async json(path, options = {}) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      try {
        const response = await fetch(this.base + path, {...options, signal: controller.signal, cache: 'no-store'});
        const body = await response.json();
        return options.method === 'POST' ? {body, status: response.status} : (() => {
          if (!response.ok) { const error = new Error(body.error || 'HTTP ' + response.status); error.status = response.status; throw error; }
          return body;
        })();
      } finally { clearTimeout(timeout); }
    }
    async send(record, onAttempt) {
      // One retry at most, with the exact same serialized body and identifier.
      let lastError;
      for (let attempt = 1; attempt <= 2; attempt++) {
        onAttempt?.(attempt);
        try {
          const {body, status} = await this.json('/api/' + record.command, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(record.body)});
          const ack = ToyProtocol.ack(body, record);
          if (ack.gateway_id !== record.gateway_id) throw new Error('Gateway restarted while processing the command.');
          if ((status >= 200 && status < 300) !== ack.accepted) throw new Error('HTTP status and acceptance disagree.');
          return ack;
        } catch (error) { lastError = error; }
        if (!this.live || this.gatewayId !== record.gateway_id) break;
      }
      throw lastError;
    }
    async lookup(id) { return this.json('/api/commands/' + encodeURIComponent(id)); }
    close() {
      this.closed = true; this.generation++; clearTimeout(this.reconnectTimer); clearInterval(this.watchdog); this.ws?.close();
    }
  }
  root.GatewayConnection = GatewayConnection;
})(globalThis);
