// Visor PDF con PDF.js: render perezoso, zoom, y SyncTeX inverso.
import { api } from './api.js';
import { toast } from './ui.js';

pdfjsLib.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.min.js';

const container = () => document.getElementById('pdf-container');

let pdfDoc = null;
let scale = null;          // CSS px por punto PDF
let fitWidth = true;
let pages = [];            // {wrapper, canvas, page, viewport, rendered, task}
let observer = null;
let currentPage = 1;
let loading = false;
let onInverse = null;      // callback({file, line})

export function initPdf(callbacks) {
  onInverse = callbacks.onInverse;
  document.getElementById('pdf-zoom-in').onclick = () => setZoom(scale * 1.2);
  document.getElementById('pdf-zoom-out').onclick = () => setZoom(scale / 1.2);
  document.getElementById('pdf-fit').onclick = () => { fitWidth = true; reloadView(); };
  document.getElementById('pdf-prev').onclick = () => scrollToPage(currentPage - 1);
  document.getElementById('pdf-next').onclick = () => scrollToPage(currentPage + 1);
  container().addEventListener('scroll', updatePageInfo);
  new ResizeObserver(() => { if (fitWidth && pdfDoc) reloadView(); }).observe(container());
}

export async function reloadPdf() {
  if (loading) return;
  loading = true;
  try {
    const doc = await pdfjsLib.getDocument({ url: '/api/pdf?v=' + Date.now() }).promise;
    const old = pdfDoc;
    pdfDoc = doc;
    await buildPages(true);
    if (old) old.destroy();
    document.getElementById('pdf-empty')?.remove();
  } catch (e) {
    if (!String(e).includes('404')) console.warn('pdf', e);
  } finally {
    loading = false;
  }
}

async function reloadView() {
  if (!pdfDoc) return;
  await buildPages(false);
}

async function buildPages(isNewDoc) {
  const cont = container();
  const prevScroll = cont.scrollTop;
  const prevScale = scale;

  const first = await pdfDoc.getPage(1);
  if (fitWidth || scale == null) {
    const avail = cont.clientWidth - 36;
    scale = Math.max(0.3, avail / first.getViewport({ scale: 1 }).width);
  }

  observer?.disconnect();
  for (const p of pages) p.task?.cancel();
  cont.querySelectorAll('.pdf-page').forEach((el) => el.remove());
  pages = [];

  observer = new IntersectionObserver(onIntersect, { root: cont, rootMargin: '400px 0px' });

  for (let i = 1; i <= pdfDoc.numPages; i++) {
    const page = i === 1 ? first : await pdfDoc.getPage(i);
    const viewport = page.getViewport({ scale });
    const wrapper = document.createElement('div');
    wrapper.className = 'pdf-page';
    wrapper.dataset.page = i;
    wrapper.style.width = viewport.width + 'px';
    wrapper.style.height = viewport.height + 'px';
    const num = document.createElement('span');
    num.className = 'pageno';
    num.textContent = i;
    wrapper.appendChild(num);
    wrapper.addEventListener('click', (e) => {
      if (e.altKey || e.metaKey) inverseSync(e, wrapper);
    });
    wrapper.addEventListener('dblclick', (e) => inverseSync(e, wrapper));
    cont.appendChild(wrapper);
    pages.push({ wrapper, page, viewport, canvas: null, rendered: false, task: null });
    observer.observe(wrapper);
  }

  // conservar posición: mismo doc → mismo scroll (ajustado si cambió el zoom)
  if (!isNewDoc && prevScale) {
    cont.scrollTop = prevScroll * (scale / prevScale);
  } else {
    cont.scrollTop = prevScroll;
  }
  updatePageInfo();
  updateZoomLabel();
}

function onIntersect(entries) {
  for (const entry of entries) {
    const idx = Number(entry.target.dataset.page) - 1;
    const p = pages[idx];
    if (!p) continue;
    if (entry.isIntersecting && !p.rendered) renderPage(p);
  }
}

async function renderPage(p) {
  if (p.rendered || p.task) return;
  const canvas = document.createElement('canvas');
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(p.viewport.width * ratio);
  canvas.height = Math.floor(p.viewport.height * ratio);
  canvas.style.width = p.viewport.width + 'px';
  canvas.style.height = p.viewport.height + 'px';
  const ctx = canvas.getContext('2d');
  p.task = p.page.render({
    canvasContext: ctx,
    viewport: p.viewport,
    transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
  });
  try {
    await p.task.promise;
    p.wrapper.prepend(canvas);
    p.canvas = canvas;
    p.rendered = true;
  } catch { /* render cancelado */ }
  p.task = null;
}

function setZoom(newScale) {
  fitWidth = false;
  scale = Math.min(4, Math.max(0.25, newScale));
  reloadView();
}

function updateZoomLabel() {
  document.getElementById('pdf-zoom').textContent = Math.round((scale || 1) * 100 / 1.335) + '%';
}

function updatePageInfo() {
  if (!pages.length) return;
  const cont = container();
  const mid = cont.scrollTop + cont.clientHeight / 3;
  let best = 1;
  for (const p of pages) {
    if (p.wrapper.offsetTop <= mid) best = Number(p.wrapper.dataset.page);
  }
  currentPage = best;
  document.getElementById('pdf-pageinfo').textContent = `${best} / ${pages.length}`;
}

export function scrollToPage(n, yPt = null) {
  const p = pages[n - 1];
  if (!p) return;
  const cont = container();
  const target = p.wrapper.offsetTop + (yPt != null ? yPt * scale - 120 : -12);
  cont.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
}

// Resalta el destino de un salto SyncTeX código → PDF.
export function flashAt(page, yPt) {
  scrollToPage(page, yPt);
  const p = pages[page - 1];
  if (!p) return;
  const flash = document.createElement('div');
  flash.className = 'sync-flash';
  flash.style.top = (yPt * scale - 11) + 'px';
  p.wrapper.appendChild(flash);
  setTimeout(() => flash.remove(), 1700);
}

async function inverseSync(e, wrapper) {
  const rect = wrapper.getBoundingClientRect();
  const x = (e.clientX - rect.left) / scale;
  const y = (e.clientY - rect.top) / scale;
  try {
    const r = await api.syncInverse(Number(wrapper.dataset.page), x, y);
    onInverse?.(r);
  } catch (err) {
    toast(err.message, 'warn');
  }
}

export function hasPdf() { return pdfDoc != null; }
