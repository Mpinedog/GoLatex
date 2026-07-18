// WebSocket de eventos en vivo, con reconexión automática.
const handlers = {};

export function on(type, fn) {
  (handlers[type] ||= []).push(fn);
}

export function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    (handlers[ev.type] || []).forEach((fn) => {
      try { fn(ev); } catch (err) { console.error('handler', ev.type, err); }
    });
  };
  ws.onclose = () => setTimeout(connectWS, 1500);
  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send('ping');
    if (ws.readyState === WebSocket.CLOSED) clearInterval(ping);
  }, 25000);
}
