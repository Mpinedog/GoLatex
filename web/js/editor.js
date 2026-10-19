// Editor CodeMirror con pestañas y sincronización con cambios externos.
import { api } from './api.js';
import { toast } from './ui.js';

let cm = null;
let current = null;                 // path activo
const open = new Map();             // path -> {doc, savedHash, cleanGen, conflict}
let opts = {};
let jumpMark = null;

const tabsEl = () => document.getElementById('tabs');
const banner = () => document.getElementById('ext-banner');

export function initEditor(options) {
  opts = options;
  const host = document.getElementById('editor-host');
  cm = CodeMirror(host, {
    mode: 'stex',
    lineNumbers: true,
    lineWrapping: true,
    matchBrackets: true,
    autoCloseBrackets: true,
    styleActiveLine: true,
    theme: document.documentElement.dataset.theme === 'dark' ? 'material-darker' : 'default',
    extraKeys: {
      'Cmd-S': () => saveCurrent(),
      'Ctrl-S': () => saveCurrent(),
      'Cmd-Enter': () => opts.onCompile?.(),
      'Ctrl-Enter': () => opts.onCompile?.(),
      'Cmd-Alt-J': () => syncToPdf(),
      'Ctrl-Alt-J': () => syncToPdf(),
    },
  });
  cm.on('change', () => {
    const entry = open.get(current);
    if (!entry) return;
    const dirty = !entry.doc.isClean(entry.cleanGen);
    document.querySelector(`.tab[data-path="${CSS.escape(current)}"]`)
      ?.classList.toggle('dirty', dirty);
  });
  cm.getWrapperElement().style.display = 'none';

  document.getElementById('ext-reload').onclick = async () => {
    if (current) await forceReload(current);
    hideBanner();
  };
  document.getElementById('ext-keep').onclick = async () => {
    const entry = open.get(current);
    if (!entry) return;
    // tomar el hash actual del disco como base: el próximo guardado
    // sobrescribe a propósito la versión externa
    try {
      entry.savedHash = (await api.read(current)).hash;
    } catch { /* si ya no existe, guardar lo recrea */ }
    entry.conflict = false;
    hideBanner();
    renderTabs();
    toast('Se mantiene tu versión local; al guardar sobrescribirás el disco.', 'warn');
  };
}

export function setTheme(dark) {
  cm?.setOption('theme', dark ? 'material-darker' : 'default');
}

export function currentPath() { return current; }

export function isDirty(path) {
  const entry = open.get(path);
  return entry ? !entry.doc.isClean(entry.cleanGen) : false;
}

export async function openFile(path, line = null) {
  if (!open.has(path)) {
    const f = await api.read(path);
    const doc = CodeMirror.Doc(f.content, 'stex');
    open.set(path, { doc, savedHash: f.hash, cleanGen: doc.changeGeneration(), conflict: false });
  }
  current = path;
  const entry = open.get(path);
  cm.swapDoc(entry.doc);
  cm.getWrapperElement().style.display = '';
  document.getElementById('editor-empty').style.display = 'none';
  cm.refresh();
  renderTabs();
  if (entry.conflict) showBanner(path); else hideBanner();
  if (line != null) jumpToLine(line);
  cm.focus();
  opts.onOpen?.(path);
}

export function jumpToLine(line) {
  const ln = Math.max(0, line - 1);
  cm.setCursor({ line: ln, ch: 0 });
  cm.scrollIntoView({ line: ln, ch: 0 }, 120);
  if (jumpMark) jumpMark.clear();
  cm.addLineClass(ln, 'background', 'cm-jump-line');
  const lineNo = ln;
  jumpMark = { clear: () => cm.removeLineClass(lineNo, 'background', 'cm-jump-line') };
  setTimeout(() => { jumpMark?.clear(); jumpMark = null; }, 1800);
}

export async function saveCurrent() {
  if (!current) return;
  const entry = open.get(current);
  const content = entry.doc.getValue();
  const gen = entry.doc.changeGeneration();  // antes del await: lo que se tipee mientras tanto sigue "sucio"
  const path = current;
  try {
    const r = await api.write(path, content, entry.savedHash);
    entry.savedHash = r.hash;
    entry.cleanGen = gen;
    entry.conflict = false;
    hideBanner();
    renderTabs();
    opts.onSave?.(path);
  } catch (e) {
    if (e.status === 409) {
      // otro (el agente u otro editor) lo cambió: no pisar, avisar
      entry.conflict = true;
      if (path === current) showBanner(path);
      renderTabs();
      toast(`${path} cambió en el disco: no se guardó para no pisar esos cambios.`, 'warn', 6000);
      return;
    }
    toast(`Error al guardar: ${e.message}`, 'err');
  }
}

export function closeFile(path) {
  const entry = open.get(path);
  if (entry && !entry.doc.isClean(entry.cleanGen)
      && !confirm(`${path} tiene cambios sin guardar. ¿Cerrar igual?`)) return;
  open.delete(path);
  if (current === path) {
    current = [...open.keys()].pop() || null;
    if (current) {
      cm.swapDoc(open.get(current).doc);
    } else {
      cm.getWrapperElement().style.display = 'none';
      document.getElementById('editor-empty').style.display = '';
      hideBanner();
    }
  }
  renderTabs();
}

// Un agente (u otro editor) cambió el archivo en disco.
export async function onExternalChange(ev) {
  const entry = open.get(ev.path);
  if (!entry) return;
  if (ev.hash && ev.hash === entry.savedHash) return; // eco de nuestro guardado
  if (entry.doc.isClean(entry.cleanGen)) {
    await forceReload(ev.path);
    toast(`${ev.path} se actualizó desde el disco`, 'ok', 2500);
  } else {
    entry.conflict = true;
    if (ev.path === current) showBanner(ev.path);
    else renderTabs();
  }
}

async function forceReload(path) {
  const entry = open.get(path);
  if (!entry) return;
  const f = await api.read(path);
  const wasCurrent = path === current;
  const cursor = wasCurrent ? cm.getCursor() : null;
  const scroll = wasCurrent ? cm.getScrollInfo() : null;
  entry.doc.setValue(f.content);
  entry.savedHash = f.hash;
  entry.cleanGen = entry.doc.changeGeneration();
  entry.conflict = false;
  if (wasCurrent) {
    cm.setCursor(cursor);
    cm.scrollTo(scroll.left, scroll.top);
  }
  renderTabs();
}

function showBanner(path) {
  document.getElementById('ext-banner-text').textContent =
    `${path} cambió en el disco y tienes cambios sin guardar.`;
  banner().hidden = false;
}
function hideBanner() { banner().hidden = true; }

async function syncToPdf() {
  if (!current) return;
  const pos = cm.getCursor();
  try {
    const r = await api.syncForward(current, pos.line + 1, pos.ch + 1);
    opts.onSyncForward?.(r);
  } catch (e) {
    toast(e.message, 'warn');
  }
}

function renderTabs() {
  const el = tabsEl();
  el.innerHTML = '';
  for (const [path, entry] of open) {
    const tab = document.createElement('div');
    tab.className = 'tab';
    tab.dataset.path = path;
    if (path === current) tab.classList.add('active');
    if (!entry.doc.isClean(entry.cleanGen)) tab.classList.add('dirty');
    const dot = document.createElement('span');
    dot.className = 'dot';
    const name = document.createElement('span');
    name.textContent = (entry.conflict ? '⚠ ' : '') + path.split('/').pop();
    name.title = path;
    const close = document.createElement('button');
    close.className = 'close';
    close.textContent = '×';
    close.onclick = (e) => { e.stopPropagation(); closeFile(path); };
    tab.append(dot, name, close);
    tab.onclick = () => openFile(path);
    el.appendChild(tab);
  }
}
