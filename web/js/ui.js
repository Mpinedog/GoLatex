// Piezas de UI genéricas: toasts y menú contextual.

export function toast(msg, kind = 'ok', ms = 3500) {
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .3s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 320);
  }, ms);
}

const menu = () => document.getElementById('ctxmenu');

export function showMenu(x, y, items) {
  const m = menu();
  m.innerHTML = '';
  for (const it of items) {
    if (it === '-') {
      const s = document.createElement('div');
      s.className = 'sep';
      m.appendChild(s);
      continue;
    }
    const b = document.createElement('button');
    b.textContent = it.label;
    if (it.danger) b.classList.add('danger');
    b.onclick = () => { hideMenu(); it.fn(); };
    m.appendChild(b);
  }
  m.hidden = false;
  const rect = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - rect.width - 8) + 'px';
  m.style.top = Math.min(y, innerHeight - rect.height - 8) + 'px';
}

export function hideMenu() { menu().hidden = true; }

document.addEventListener('click', hideMenu);
document.addEventListener('contextmenu', (e) => {
  if (!e.target.closest('#tree')) hideMenu();
});
window.addEventListener('blur', hideMenu);
