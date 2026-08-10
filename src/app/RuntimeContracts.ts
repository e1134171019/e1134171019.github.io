export type RuntimeMode = 'loading' | 'presentation' | 'interactive' | 'fallback';

export type RuntimeErrorCode =
  | 'unsupported_webgl2'
  | 'renderer_initialization_failed'
  | 'asset_load_failed'
  | 'invalid_asset'
  | 'runtime_failure';

export function isInteractiveRuntimeMode(mode: RuntimeMode): boolean {
  return mode === 'interactive';
}
