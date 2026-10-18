// GoLatex: orquestación de la UI.
import { api } from './api.js';
import { connectWS, on } from './ws.js';
import { toast } from './ui.js';
import * as editor from './editor.js';
import * as pdf from './pdfview.js';
import * as tree from './tree.js';
import * as errors from './errors.js';

let project = null;
let compiling = false;

const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const baseName = (p) => p.split(/[\\/]/).filter(Boolean).pop() || p;

// En Windows/Linux los atajos se muestran con Ctrl/Alt en vez de ⌘/⌥.
function localizeShortcuts() {
  if (IS_MAC) return;
  const hints = document.getElementById('kbd-hints');
  if (hints) {
    hints.innerHTML = '';
    for (const [k, label] of [['Ctrl+S', ' guardar \u00a0 '], ['Ctrl+Enter', ' compilar \u00a0 '],
                              ['Alt+clic', ' en el PDF → código']]) {
      const kbd = document.createElement('kbd');
      kbd.textContent = k;
      hints.append(kbd, label);
    }
  }
  document.querySelectorAll('.hint').forEach((el) => {
    el.textContent = el.textContent.replace('⌥', 'Alt+');
  });
}

// ---------- tema ----------

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('golatex.theme', theme);
  document.getElementById('btn-theme').textContent = theme === 'dark' ? '☀️' : '🌙';
  editor.setTheme(theme === 'dark');
}

// ---------- estado de compilación ----------

function setChip(cls, text, onclick = null) {
  const chip = document.getElementById('status-chip');
  chip.className = 'chip ' + cls;
  chip.textContent = text;
  chip.onclick = onclick;
}

async function compile() {
  if (!project || compiling) return;
  try {
    await api.compile();  // la UI se actualiza vía WebSocket
  } catch (e) {
    toast('No se pudo compilar: ' + e.message, 'err');
    setChip('err', 'error');
    compiling = false;
  }
}

function onCompileStarted(ev) {
  compiling = true;
  document.getElementById('btn-compile').disabled = true;
  setChip('busy', ev.source === 'mcp' ? 'agente compilando…' : 'compilando…');
}

function onCompileFinished(ev) {
  compiling = false;
  document.getElementById('btn-compile').disabled = false;
  const meta = [];
  if (ev.pages) meta.push(`${ev.pages} págs`);
  if (ev.seconds != null) meta.push(`${ev.seconds}s`);
  document.getElementById('compile-meta').textContent =
    (ev.source === 'mcp' ? 'agente · ' : '') + meta.join(' · ');
  if (ev.ok) {
    setChip('ok', `✓ OK · ${meta.join(' · ')}`);
    if (ev.source === 'mcp') toast(`El agente compiló: OK, ${ev.pages} páginas`, 'ok');
    pdf.reloadPdf();
  } else {
    const n = (ev.errors || []).length;
    setChip('err', `✖ ${n} error${n === 1 ? '' : 'es'}`, () => errors.togglePanel(true));
    if (ev.source === 'mcp') toast('El agente compiló con errores', 'err');
  }
  errors.showResult(ev);
}

// ---------- proyecto ----------

async function boot() {
  const st = await api.state();
  project = st.project;
  renderRecents(st.recents);
  if (!project) {
    openProjectDialog(false);
    return;
  }
  document.getElementById('project-name').textContent = project.name;
  document.title = `${project.name} — GoLatex`;
  tree.setProject(project.root);
  const nodes = await tree.refreshTree();
  fillMainSelect(nodes);
  if (project.pdf_exists) pdf.reloadPdf();
  if (st.last_compile) errors.showResult(st.last_compile);
  fillEngineSelect();
}

function fillEngineSelect() {
  const sel = document.getElementById('engine-select');
  sel.innerHTML = '';
  const detected = project.engine_setting ? null : project.engine;
  const opts = [['auto', `auto (${detected || 'detectar'})`],
                ...(project.engines || ['pdflatex', 'xelatex', 'lualatex']).map((e) => [e, e])];
  for (const [value, label] of opts) {
    const o = document.createElement('option');
    o.value = value;
    o.textContent = '⚙ ' + label;
    if ((project.engine_setting || 'auto') === value) o.selected = true;
    sel.appendChild(o);
  }
  sel.onchange = () => api.setEngine(sel.value).catch((e) => toast(e.message, 'err'));
}

function collectTex(nodes, out = []) {
  for (const n of nodes) {
    if (n.type === 'dir') collectTex(n.children || [], out);
    else if (n.name.endsWith('.tex')) out.push(n.path);
  }
  return out;
}

function fillMainSelect(nodes) {
  const sel = document.getElementById('main-select');
  sel.innerHTML = '';
  for (const p of collectTex(nodes)) {
    const o = document.createElement('option');
    o.value = p;
    o.textContent = '★ ' + p;
    if (p === project.main) o.selected = true;
    sel.appendChild(o);
  }
  sel.onchange = () => api.setMain(sel.value).catch((e) => toast(e.message, 'err'));
}

// ---------- diálogo abrir proyecto ----------

let browsePath = '';

function renderRecents(recents) {
  const box = document.getElementById('recents');
  box.innerHTML = '';
  document.getElementById('recents-block').style.display = recents.length ? '' : 'none';
  for (const r of recents) {
    const el = document.createElement('div');
    el.className = 'recent';
    el.innerHTML = `<span class="rname">${baseName(r.path)}</span><span class="rpath">${r.path}</span>`;
    el.onclick = () => doOpen(r.path);
    box.appendChild(el);
  }
}

async function browse(path) {
  try {
    const r = await api.browse(path);
    browsePath = r.path;
    document.getElementById('browse-path').value = r.path;
    const list = document.getElementById('browse-list');
    list.innerHTML = '';
    if (r.parent) {
      const up = document.createElement('div');
      up.className = 'bdir';
      up.innerHTML = '<span>↰ ..</span>';
      up.onclick = () => browse(r.parent);
      list.appendChild(up);
    }
    for (const d of r.dirs) {
      const el = document.createElement('div');
      el.className = 'bdir';
      el.innerHTML = `<span>📁 ${d}</span>`;
      el.onclick = () => browse(r.path.replace(/[\\/]+$/, '') + (r.sep || '/') + d);
      list.appendChild(el);
    }
    document.getElementById('browse-open').textContent =
      r.has_tex ? 'Abrir esta carpeta ✓ (.tex detectado)' : 'Abrir esta carpeta';
  } catch (e) {
    toast(e.message, 'err');
  }
}

async function doOpen(path) {
  try {
    await api.open(path);
    document.getElementById('dlg-project').close();
    location.reload(); // arranque limpio con el proyecto nuevo
  } catch (e) {
    toast(e.message, 'err');
  }
}

function openProjectDialog(cancelable = true) {
  const dlg = document.getElementById('dlg-project');
  document.getElementById('dlg-project-close').style.display = cancelable ? '' : 'none';
  browse(browsePath || '');
  api.state().then((st) => renderRecents(st.recents));
  if (!dlg.open) dlg.showModal();
  dlg.oncancel = (e) => { if (!cancelable) e.preventDefault(); };
}

// ---------- wiring ----------

function init() {
  localizeShortcuts();
  applyTheme(localStorage.getItem('golatex.theme')
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

  const auto = document.getElementById('chk-autocompile');
  auto.checked = localStorage.getItem('golatex.autocompile') === '1';
  auto.onchange = () => localStorage.setItem('golatex.autocompile', auto.checked ? '1' : '0');

  editor.initEditor({
    onCompile: compile,
    onSave: () => { if (auto.checked) compile(); },
    onOpen: (path) => tree.setActive(path),
    onSyncForward: (r) => pdf.flashAt(r.page, r.y),
  });

  pdf.initPdf({
    onInverse: (r) => {
      editor.openFile(r.file, r.line).catch((e) => toast(e.message, 'err'));
    },
  });

  tree.initTree({
    getMain: () => project?.main,
    onOpenFile: (path) => editor.openFile(path).catch((e) => toast(e.message, 'err')),
    onRenamed: () => location.reload(),
    onDeleted: (path) => editor.closeFile(path),
  });

  errors.initErrors({
    onJump: (file, line) => editor.openFile(file, line).catch((e) => toast(e.message, 'err')),
  });

  document.getElementById('btn-compile').onclick = compile;
  document.getElementById('pdf-download').onclick = () => {
    if (!project?.pdf_exists && !pdf.hasPdf()) {
      toast('Aún no hay PDF; compila primero.', 'warn');
      return;
    }
    const a = document.createElement('a');
    a.href = '/api/pdf?v=' + Date.now();
    a.download = (project?.name || 'documento') + '.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
  };
  document.getElementById('btn-theme').onclick = () =>
    applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  document.getElementById('btn-project').onclick = () => openProjectDialog(!!project);
  document.getElementById('dlg-project-close').onclick = () =>
    document.getElementById('dlg-project').close();
  document.getElementById('browse-go').onclick = () =>
    browse(document.getElementById('browse-path').value);
  document.getElementById('browse-path').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') browse(e.target.value);
  });
  document.getElementById('browse-open').onclick = () => doOpen(browsePath);
  document.getElementById('dlg-img-close').onclick = () =>
    document.getElementById('dlg-img').close();

  document.addEventListener('keydown', (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key === 'Enter') { e.preventDefault(); compile(); }
    if (mod && e.key.toLowerCase() === 's' && !e.target.closest('.CodeMirror')) {
      e.preventDefault();
      editor.saveCurrent();
    }
  });

  // resizers
  setupGutter('gutter-left', document.getElementById('pane-tree'), false);
  setupGutter('gutter-right', document.getElementById('pane-pdf'), true);

  // eventos en vivo
  on('file_changed', (ev) => editor.onExternalChange(ev));
  on('tree_changed', async () => {
    const nodes = await tree.refreshTree();
    if (project) fillMainSelect(nodes);
  });
  on('compile_started', onCompileStarted);
  on('compile_finished', onCompileFinished);
  on('pdf_updated', () => pdf.reloadPdf());
  on('main_changed', async (ev) => {
    if (project) project.main = ev.path;
    const nodes = await tree.refreshTree();
    fillMainSelect(nodes);
    toast('Archivo principal: ' + ev.path, 'ok', 2000);
  });
  on('engine_changed', (ev) => {
    if (!project) return;
    project.engine = ev.engine;
    project.engine_setting = ev.setting;
    fillEngineSelect();
    toast('Motor: ' + (ev.setting || `auto (${ev.engine})`), 'ok', 2000);
  });
  on('project_opened', (ev) => {
    if (!project || project.root !== ev.root) location.reload();
  });

  connectWS();
  boot().catch((e) => toast(e.message, 'err'));
}

function setupGutter(id, pane, invert) {
  const g = document.getElementById(id);
  g.addEventListener('mousedown', (e) => {
    e.preventDefault();
    g.classList.add('dragging');
    const startX = e.clientX;
    const startW = pane.getBoundingClientRect().width;
    const move = (ev) => {
      const dx = ev.clientX - startX;
      pane.style.width = Math.max(140, startW + (invert ? -dx : dx)) + 'px';
    };
    const up = () => {
      g.classList.remove('dragging');
      removeEventListener('mousemove', move);
      removeEventListener('mouseup', up);
    };
    addEventListener('mousemove', move);
    addEventListener('mouseup', up);
  });
}

init();
