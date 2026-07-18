// Panel de problemas (errores/warnings parseados) y log crudo.
import { api } from './api.js';

let opts = {};
let logStale = true;

export function initErrors(options) {
  opts = options;
  document.querySelectorAll('.ptab').forEach((b) => {
    b.onclick = () => selectTab(b.dataset.tab);
  });
  document.getElementById('panel-toggle').onclick = togglePanel;
}

export function togglePanel(force) {
  const panel = document.getElementById('panel-bottom');
  const collapse = force !== undefined ? !force : !panel.classList.contains('collapsed');
  panel.classList.toggle('collapsed', collapse);
  document.getElementById('panel-toggle').textContent = collapse ? '▴' : '▾';
}

function selectTab(name) {
  document.querySelectorAll('.ptab').forEach((b) =>
    b.classList.toggle('active', b.dataset.tab === name));
  document.getElementById('panel-errors').hidden = name !== 'errors';
  document.getElementById('panel-log').hidden = name !== 'log';
  togglePanel(true);
  if (name === 'log' && logStale) loadLog();
}

async function loadLog() {
  try {
    document.getElementById('panel-log').textContent = await api.log();
    logStale = false;
  } catch (e) {
    document.getElementById('panel-log').textContent = '(no se pudo cargar el log: ' + e.message + ')';
  }
}

export function showResult(result) {
  logStale = true;
  if (!document.getElementById('panel-log').hidden) loadLog();

  const items = [...(result.errors || []), ...(result.warnings || [])];
  const box = document.getElementById('panel-errors');
  box.innerHTML = '';

  const count = document.getElementById('err-count');
  const nErr = (result.errors || []).length;
  const nWarn = (result.warnings || []).length;
  if (nErr + nWarn > 0) {
    count.hidden = false;
    count.textContent = nErr > 0 ? nErr : nWarn;
    count.classList.toggle('warnonly', nErr === 0);
  } else {
    count.hidden = true;
  }

  if (!items.length) {
    box.innerHTML = '<div class="empty small">Compilación limpia, sin problemas. 🎉</div>';
    return;
  }
  for (const it of items) {
    const row = document.createElement('div');
    row.className = 'prob ' + it.type;
    const sev = document.createElement('span');
    sev.className = 'sev';
    sev.textContent = it.type === 'error' ? '✖' : '▲';
    const loc = document.createElement('span');
    loc.className = 'loc';
    loc.textContent = it.file ? `${it.file}${it.line ? ':' + it.line : ''}` : '·';
    const msg = document.createElement('span');
    msg.className = 'msg';
    msg.textContent = it.message;
    msg.title = it.message;
    row.append(sev, loc, msg);
    if (it.file) {
      row.onclick = () => opts.onJump?.(it.file, it.line || 1);
    }
    box.appendChild(row);
  }
  if (nErr > 0) {
    selectTab('errors');
    togglePanel(true);
  }
}
