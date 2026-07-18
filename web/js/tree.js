// Árbol de archivos con menú contextual (crear, renombrar, eliminar, main).
import { api } from './api.js';
import { showMenu, toast } from './ui.js';

const IMG_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
let opts = {};
let openDirs = new Set();
let rootKey = '';
let activePath = null;

export function initTree(options) {
  opts = options;
  document.getElementById('btn-new-file').onclick = () => createItem('', 'file');
  document.getElementById('btn-new-dir').onclick = () => createItem('', 'dir');
}

export function setProject(root) {
  rootKey = 'golatex.dirs.' + root;
  try { openDirs = new Set(JSON.parse(localStorage.getItem(rootKey) || '[]')); }
  catch { openDirs = new Set(); }
}

export function setActive(path) {
  activePath = path;
  document.querySelectorAll('#tree .trow.active').forEach((el) => el.classList.remove('active'));
  if (path) {
    document.querySelector(`#tree .trow[data-path="${CSS.escape(path)}"]`)?.classList.add('active');
  }
}

export async function refreshTree() {
  const data = await api.tree();
  render(data);
  return data;
}

function persistDirs() {
  localStorage.setItem(rootKey, JSON.stringify([...openDirs]));
}

function icon(node) {
  if (node.type === 'dir') return '📁';
  const n = node.name.toLowerCase();
  if (n.endsWith('.tex')) return '📄';
  if (n.endsWith('.bib') || n.endsWith('.bst')) return '📚';
  if (n.endsWith('.pdf')) return '📕';
  if (IMG_EXTS.some((e) => n.endsWith(e))) return '🖼';
  return '📃';
}

export function render(nodes) {
  const treeEl = document.getElementById('tree');
  treeEl.innerHTML = '';
  treeEl.appendChild(renderLevel(nodes));
  setActive(activePath);
  treeEl.oncontextmenu = (e) => {
    if (e.target === treeEl) {
      e.preventDefault();
      showMenu(e.clientX, e.clientY, rootMenu());
    }
  };
}

function renderLevel(nodes) {
  const frag = document.createDocumentFragment();
  for (const node of nodes) {
    const wrap = document.createElement('div');
    wrap.className = 'tnode';
    const row = document.createElement('div');
    row.className = 'trow';
    row.dataset.path = node.path;

    if (node.type === 'dir') {
      const caret = document.createElement('span');
      caret.className = 'caret' + (openDirs.has(node.path) ? ' open' : '');
      caret.textContent = '▶';
      row.append(caret, mkIcon(node), mkName(node));
      const kids = document.createElement('div');
      kids.className = 'tchildren';
      kids.style.display = openDirs.has(node.path) ? '' : 'none';
      kids.appendChild(renderLevel(node.children || []));
      row.onclick = () => {
        const isOpen = openDirs.has(node.path);
        if (isOpen) openDirs.delete(node.path); else openDirs.add(node.path);
        caret.classList.toggle('open', !isOpen);
        kids.style.display = isOpen ? 'none' : '';
        persistDirs();
      };
      row.oncontextmenu = (e) => { e.preventDefault(); showMenu(e.clientX, e.clientY, dirMenu(node)); };
      wrap.append(row, kids);
    } else {
      const pad = document.createElement('span');
      pad.className = 'caret';
      row.append(pad, mkIcon(node), mkName(node));
      if (node.path === opts.getMain?.()) {
        const star = document.createElement('span');
        star.className = 'main-star';
        star.textContent = '★ main';
        row.appendChild(star);
      }
      if (!node.text) row.classList.add('nontext');
      row.onclick = () => openNode(node);
      row.oncontextmenu = (e) => { e.preventDefault(); showMenu(e.clientX, e.clientY, fileMenu(node)); };
      wrap.appendChild(row);
    }
    frag.appendChild(wrap);
  }
  return frag;
}

const mkIcon = (node) => {
  const s = document.createElement('span');
  s.className = 'ficon';
  s.textContent = icon(node);
  return s;
};
const mkName = (node) => {
  const s = document.createElement('span');
  s.textContent = node.name;
  return s;
};

function openNode(node) {
  const n = node.name.toLowerCase();
  if (node.text) {
    opts.onOpenFile?.(node.path);
  } else if (IMG_EXTS.some((e) => n.endsWith(e))) {
    const dlg = document.getElementById('dlg-img');
    document.getElementById('dlg-img-el').src = '/api/raw?path=' + encodeURIComponent(node.path);
    dlg.showModal();
  } else {
    toast('Archivo binario; no se puede editar aquí.', 'warn', 2200);
  }
}

// ---------- menús ----------

function rootMenu() {
  return [
    { label: 'Nuevo archivo', fn: () => createItem('', 'file') },
    { label: 'Nueva carpeta', fn: () => createItem('', 'dir') },
  ];
}

function dirMenu(node) {
  return [
    { label: 'Nuevo archivo aquí', fn: () => createItem(node.path + '/', 'file') },
    { label: 'Nueva carpeta aquí', fn: () => createItem(node.path + '/', 'dir') },
    '-',
    { label: 'Renombrar…', fn: () => renameItem(node) },
    { label: 'Eliminar (a Papelera)', danger: true, fn: () => deleteItem(node) },
  ];
}

function fileMenu(node) {
  const items = [];
  if (node.text) items.push({ label: 'Abrir', fn: () => openNode(node) });
  if (node.name.endsWith('.tex')) {
    items.push({ label: 'Fijar como principal ★', fn: async () => {
      await api.setMain(node.path);
    } });
  }
  items.push('-',
    { label: 'Renombrar…', fn: () => renameItem(node) },
    { label: 'Eliminar (a Papelera)', danger: true, fn: () => deleteItem(node) });
  return items;
}

async function createItem(prefix, type) {
  const label = type === 'dir' ? 'Nombre de la carpeta' : 'Nombre del archivo (p. ej. capitulo_5.tex)';
  const name = prompt(label, prefix);
  if (!name) return;
  try {
    await api.create(name, type);
    await refreshTree();
    if (type === 'file' && name.endsWith('.tex')) opts.onOpenFile?.(name);
  } catch (e) { toast(e.message, 'err'); }
}

async function renameItem(node) {
  const name = prompt('Nuevo nombre/ruta', node.path);
  if (!name || name === node.path) return;
  try {
    await api.rename(node.path, name);
    await refreshTree();
    opts.onRenamed?.(node.path, name);
  } catch (e) { toast(e.message, 'err'); }
}

async function deleteItem(node) {
  if (!confirm(`¿Enviar "${node.path}" a la Papelera?`)) return;
  try {
    await api.del(node.path);
    await refreshTree();
    opts.onDeleted?.(node.path);
  } catch (e) { toast(e.message, 'err'); }
}
