// Cliente REST de GoLatex.
async function j(method, url, body) {
  const opts = { method };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* texto plano */ }
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('json') ? res.json() : res.text();
}

export const api = {
  state: () => j('GET', '/api/state'),
  open: (path) => j('POST', '/api/project/open', { path }),
  tree: () => j('GET', '/api/tree'),
  read: (path) => j('GET', `/api/file?path=${encodeURIComponent(path)}`),
  write: (path, content) => j('PUT', '/api/file', { path, content }),
  create: (path, type) => j('POST', '/api/fs/create', { path, type }),
  rename: (path, new_path) => j('POST', '/api/fs/rename', { path, new_path }),
  del: (path) => j('POST', '/api/fs/delete', { path }),
  setMain: (path) => j('POST', '/api/main', { path }),
  setEngine: (engine) => j('POST', '/api/engine', { engine }),
  compile: () => j('POST', '/api/compile'),
  log: () => j('GET', '/api/log'),
  browse: (path) => j('GET', `/api/browse?path=${encodeURIComponent(path || '')}`),
  syncForward: (file, line, col) =>
    j('GET', `/api/synctex/forward?file=${encodeURIComponent(file)}&line=${line}&col=${col || 1}`),
  syncInverse: (page, x, y) =>
    j('GET', `/api/synctex/inverse?page=${page}&x=${x.toFixed(2)}&y=${y.toFixed(2)}`),
};
