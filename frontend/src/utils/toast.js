// Minimal global toast bus. Components call toast.success/error/info;
// any mounted <Toaster /> renders them. No React context needed.
let listeners = [];

export function subscribeToast(fn) {
  listeners.push(fn);
  return () => { listeners = listeners.filter(l => l !== fn); };
}

export function toast(message, kind = 'info') {
  const item = { id: `${Date.now()}-${Math.random()}`, message, kind };
  listeners.forEach(fn => { try { fn(item); } catch {} });
}
toast.success = (m) => toast(m, 'success');
toast.error = (m) => toast(m, 'error');
