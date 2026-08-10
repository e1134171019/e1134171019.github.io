import './styles.css';
import { RuntimeApp, type RuntimeAppDependencies } from './app/RuntimeApp';
import { createRendererHandle } from './scene/Renderer';

let runtimeApp: RuntimeApp | null = null;

function disposeRuntime(): void {
  runtimeApp?.dispose();
  runtimeApp = null;
}

function developmentDiagnosticDependencies(): Partial<RuntimeAppDependencies> | null {
  if (!import.meta.env.DEV) {
    return null;
  }

  const forceWebGL2Failure =
    new URLSearchParams(window.location.search).get('forceWebGL2Failure') === '1';

  if (!forceWebGL2Failure) {
    return null;
  }

  return {
    createRenderer: (options) =>
      createRendererHandle({
        ...options,
        contextProbe: () => null,
      }),
  };
}

function bootstrapRuntime(): void {
  if (runtimeApp) {
    return;
  }

  const root = document.querySelector<HTMLElement>('#app');
  if (!root) {
    throw new Error('runtime_root_missing');
  }

  const diagnosticDependencies = developmentDiagnosticDependencies();
  runtimeApp = new RuntimeApp({
    root,
    windowRef: window,
    documentRef: document,
    ...(diagnosticDependencies ? { dependencies: diagnosticDependencies } : {}),
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
