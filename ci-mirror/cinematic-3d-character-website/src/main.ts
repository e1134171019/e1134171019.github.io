import './styles.css';
import { RuntimeApp } from './app/RuntimeApp';

let runtimeApp: RuntimeApp | null = null;

function disposeRuntime(): void {
  runtimeApp?.dispose();
  runtimeApp = null;
}

function bootstrapRuntime(): void {
  if (runtimeApp) {
    return;
  }

  const root = document.querySelector<HTMLElement>('#app');
  if (!root) {
    throw new Error('runtime_root_missing');
  }

  runtimeApp = new RuntimeApp({
    root,
    windowRef: window,
    documentRef: document,
  });

  void runtimeApp.start();
  window.addEventListener('pagehide', disposeRuntime, { once: true });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrapRuntime, { once: true });
} else {
  bootstrapRuntime();
}

if (import.meta.hot) {
  import.meta.hot.dispose(disposeRuntime);
}
