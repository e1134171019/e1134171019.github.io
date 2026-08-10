import type { RuntimeErrorCode } from '../app/RuntimeContracts';

export interface RuntimeError {
  readonly code: RuntimeErrorCode;
  readonly message: string;
}

export type RuntimeState =
  | { readonly mode: 'loading' }
  | { readonly mode: 'presentation' }
  | { readonly mode: 'interactive' }
  | { readonly mode: 'fallback'; readonly error: RuntimeError };

export type RuntimeEvent =
  | { readonly type: 'assetsReady' }
  | { readonly type: 'interactionStarted' }
  | { readonly type: 'presentationRequested' }
  | {
      readonly type: 'runtimeError';
      readonly code: RuntimeErrorCode;
      readonly message: string;
    };

export function reduceRuntimeState(state: RuntimeState, event: RuntimeEvent): RuntimeState {
  if (event.type === 'runtimeError') {
    return {
      mode: 'fallback',
      error: {
        code: event.code,
        message: event.message,
      },
    };
  }

  if (state.mode === 'fallback') {
    return state;
  }

  switch (event.type) {
    case 'assetsReady':
      return state.mode === 'loading' ? { mode: 'presentation' } : state;
    case 'interactionStarted':
      return state.mode === 'presentation' ? { mode: 'interactive' } : state;
    case 'presentationRequested':
      return state.mode === 'interactive' ? { mode: 'presentation' } : state;
  }
}
