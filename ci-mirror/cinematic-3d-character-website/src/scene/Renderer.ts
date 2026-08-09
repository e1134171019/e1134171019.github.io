import type { RuntimeErrorCode } from '../app/RuntimeContracts';

export type RendererInitializationErrorCode = Extract<
  RuntimeErrorCode,
  'unsupported_webgl2' | 'renderer_initialization_failed'
>;

export class RendererInitializationError extends Error {
  readonly code: RendererInitializationErrorCode;

  constructor(code: RendererInitializationErrorCode, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = 'RendererInitializationError';
    this.code = code;
  }
}

export type WebGL2ContextProbe = () => WebGL2RenderingContext | null;

export function assertWebGL2Available(probe: WebGL2ContextProbe): WebGL2RenderingContext {
  const context = probe();

  if (!context) {
    throw new RendererInitializationError(
      'unsupported_webgl2',
      'unsupported_webgl2',
    );
  }

  return context;
}
