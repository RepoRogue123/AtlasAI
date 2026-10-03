// Page -> compact text snapshot for the LLM.
// Interactive elements get a numbered ref ([12] button "Submit bill") stored in data-atlas-ref, so the
// agent addresses elements by ref instead of brittle CSS selectors. Refs are re-assigned on every observe.
() => {
  const out = [];
  let n = 0;
  document.querySelectorAll('[data-atlas-ref]').forEach(e => e.removeAttribute('data-atlas-ref'));
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'TEMPLATE', 'HEAD', 'IFRAME']);
  const BLOCK = new Set(['DIV', 'P', 'TR', 'LI', 'UL', 'OL', 'TABLE', 'FORM', 'SECTION', 'HEADER', 'FOOTER',
    'MAIN', 'NAV', 'ARTICLE', 'ASIDE', 'PRE', 'BR', 'DL', 'DT', 'DD', 'FIGURE', 'BLOCKQUOTE', 'THEAD', 'TBODY']);
  const visible = el => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (s.display === 'contents') return true;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const labelOf = el => {
    const aria = el.getAttribute('aria-label');
    if (aria) return clean(aria);
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return clean(l.innerText);
    }
    const pl = el.closest('label');
    if (pl) return clean(pl.innerText);
    return clean(el.placeholder || el.name || el.title || '');
  };
  const shortHref = a => {
    try {
      const u = new URL(a.href, location.href);
      return u.origin === location.origin ? u.pathname + u.search : u.href;
    } catch { return a.getAttribute('href') || ''; }
  };
  const describe = el => {
    const tag = el.tagName, role = el.getAttribute('role'), type = (el.type || '').toLowerCase();
    if (tag === 'A') return `link "${clean(el.innerText) || el.title || labelOf(el)}" -> ${shortHref(el)}`;
    if (tag === 'SELECT') {
      const opts = [...el.options].map(o => clean(o.text)).join(' | ');
      return `select "${labelOf(el)}" selected="${clean(el.selectedOptions[0]?.text)}" options=[${opts}]`;
    }
    if (tag === 'TEXTAREA') return `textarea "${labelOf(el)}" value="${el.value.slice(0, 300)}"`;
    if (tag === 'INPUT') {
      if (['submit', 'button', 'reset'].includes(type)) return `button "${clean(el.value) || labelOf(el)}"`;
      if (type === 'checkbox' || type === 'radio') return `${type} "${labelOf(el)}" checked=${el.checked}`;
      const val = type === 'password' ? (el.value ? '********' : '') : el.value;
      return `input[${type || 'text'}] "${labelOf(el)}" value="${val}"`;
    }
    return `button "${clean(el.innerText) || labelOf(el)}"`;
  };
  const isInteractive = el => {
    const tag = el.tagName, role = el.getAttribute('role');
    if (tag === 'A') return el.hasAttribute('href');
    if (['BUTTON', 'SELECT', 'TEXTAREA', 'SUMMARY'].includes(tag)) return true;
    if (tag === 'INPUT') return el.type !== 'hidden';
    return ['button', 'link', 'checkbox', 'tab', 'menuitem'].includes(role) || el.hasAttribute('onclick');
  };
  const walk = node => {
    if (node.nodeType === 3) { const t = clean(node.textContent); if (t) out.push(t); return; }
    if (node.nodeType !== 1) return;
    const el = node, tag = el.tagName;
    if (SKIP.has(tag) || el.getAttribute('aria-hidden') === 'true') return;
    if (tag === 'OPTION' || !visible(el)) return;
    if (isInteractive(el)) {
      n += 1;
      el.setAttribute('data-atlas-ref', String(n));
      // Links stay inline (keeps table rows on one line); form controls get their own line.
      out.push(tag === 'A' ? `[${n}] ${describe(el)}` : `\n[${n}] ${describe(el)}\n`);
      if (!['DIV', 'SPAN', 'LI', 'TD'].includes(tag)) return;
    }
    if (/^H[1-6]$/.test(tag)) { out.push('\n' + '#'.repeat(+tag[1]) + ' ' + clean(el.innerText) + '\n'); return; }
    const block = BLOCK.has(tag);
    if (block) out.push('\n');
    for (const c of el.childNodes) walk(c);
    if (tag === 'TD' || tag === 'TH') out.push(' | ');
    if (block) out.push('\n');
  };
  walk(document.body);
  let text = out.join(' ').replace(/[ \t]+/g, ' ').replace(/ *\n */g, '\n').replace(/\n{2,}/g, '\n').trim();
  const dialogs = [...document.querySelectorAll('[role="dialog"][aria-modal="true"], dialog[open]')].filter(visible);
  const modal = dialogs.length ? clean(dialogs[0].innerText).slice(0, 200) : null;
  return { url: location.href, title: document.title, text, refs: n, modal };
}
