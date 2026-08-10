import {
  PerspectiveCamera,
  Scene,
  WebGLRenderer,
  type WebGLRendererParameters,
} from 'three';
import type { RuntimeErrorCode } from '../app/RuntimeContracts';
import { createCharacterEnvironment } from './Environment';
import { addCharacterReadabilityLighting } from './Lighting';

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

export type WebGL2AvailabilityProbe = () => WebGL2RenderingContext | null;
export type WebGL2CanvasProbe = (canvas: HTMLCanvasElement) => WebGL2RenderingContext | null;
export type RendererFactory = (parameters: WebGLRendererParameters) => WebGLRenderer;

export interface RendererBootstrapOptions {
  readonly container: HTMLElement;
  readonly width: number;
  readonly height: number;
  readonly pixelRatio?: number;
  readonly contextProbe?: WebGL2CanvasProbe;
  readonly rendererFactory?: RendererFactory;
}

export interface RendererHandle {
  readonly scene: Scene;
  readonly camera: PerspectiveCamera;
  readonly renderer: WebGLRenderer;
  resize(width: number, height: number): void;
  dispose(): void;
}

const DEFAULT_CONTEXT_ATTRIBUTES: WebGLContextAttributes = {
  alpha: false,
  antialias: true,
  depth: true,
  stencil: false,
  premultipliedAlpha: true,
  preserveDrawingBuffer: false,
  powerPreference: 'high-performance',
};

function defaultContextProbe(canvas: HTMLCanvasElement): WebGL2RenderingContext | null {
  return canvas.getContext('webgl2', DEFAULT_CONTEXT_ATTRIBUTES);
}

function defaultRendererFactory(parameters: WebGLRendererParameters): WebGLRenderer {
  return new WebGLRenderer(parameters);
}

export function assertWebGL2Available(
  probe: WebGL2AvailabilityProbe,
): WebGL2RenderingContext {
  const context = probe();

  if (!context) {
    throw new RendererInitializationError('unsupported_webgl2', 'unsupported_webgl2');
  }

  return context;
}

export function createRendererHandle(options: RendererBootstrapOptions): RendererHandle {
  const canvas = document.createElement('canvas');
  const contextProbe = options.contextProbe ?? defaultContextProbe;
  const rendererFactory = options.rendererFactory ?? defaultRendererFactory;

  let context: WebGL2RenderingContext;
  try {
    context = assertWebGL2Available(() => contextProbe(canvas));
  } catch (error) {
    if (error instanceof RendererInitializationError) {
      throw error;
    }

    throw new RendererInitializationError(
      'renderer_initialization_failed',
      'renderer_initialization_failed',
      { cause: error },
    );
  }

  let renderer: WebGLRenderer;
  try {
    renderer = rendererFactory({
      canvas,
      context,
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
    });
  } catch (error) {
    throw new RendererInitializationError(
      'renderer_initialization_failed',
      'renderer_initialization_failed',
      { cause: error },
    );
  }

  const scene = new Scene();
  const environment = createCharacterEnvironment(scene);
  addCharacterReadabilityLighting(scene);
  const camera = new PerspectiveCamera(45, options.width / options.height, 0.1, 100);
  const pixelRatio = options.pixelRatio ?? 1;

  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(options.width, options.height, false);
  options.container.appendChild(renderer.domElement);

  return {
    scene,
    camera,
    renderer,
    resize(width: number, height: number) {
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    },
    dispose() {
      environment.ground.geometry.dispose();
      environment.ground.material.dispose();
      renderer.dispose();

      if (renderer.domElement.parentElement === options.container) {
        options.container.removeChild(renderer.domElement);
      }
    },
  };
}
