import { describe, expect, it } from 'vitest';
import {
  Scene,
  type Material,
  type Mesh,
  type WebGLRenderer,
  type WebGLRendererParameters,
} from 'three';
import { createCharacterEnvironment } from './Environment';
import { addCharacterReadabilityLighting } from './Lighting';
import {
  assertWebGL2Available,
  createRendererHandle,
  RendererInitializationError,
} from './Renderer';

describe('renderer capability', () => {
  it('rejects an unavailable WebGL2 context explicitly', () => {
    expect(() => assertWebGL2Available(() => null)).toThrowError('unsupported_webgl2');
  });
});

describe('renderer bootstrap lifecycle', () => {
  it('creates the renderer only after WebGL2 capability succeeds and owns resize/dispose lifecycle', () => {
    const container = document.createElement('div');
    const context = {} as WebGL2RenderingContext;
    const sizeCalls: Array<[number, number, boolean | undefined]> = [];
    const pixelRatios: number[] = [];
    let disposed = false;

    const rendererFactory = (parameters: WebGLRendererParameters): WebGLRenderer => {
      expect(parameters.context).toBe(context);
      expect(parameters.canvas).toBeInstanceOf(HTMLCanvasElement);

      return {
        domElement: parameters.canvas as HTMLCanvasElement,
        setPixelRatio(value: number) {
          pixelRatios.push(value);
        },
        setSize(width: number, height: number, updateStyle?: boolean) {
          sizeCalls.push([width, height, updateStyle]);
        },
        dispose() {
          disposed = true;
        },
      } as unknown as WebGLRenderer;
    };

    const handle = createRendererHandle({
      container,
      width: 800,
      height: 600,
      pixelRatio: 1.5,
      contextProbe: () => context,
      rendererFactory,
    });

    expect(handle.scene.isScene).toBe(true);
    expect(handle.camera.isPerspectiveCamera).toBe(true);
    expect(handle.camera.aspect).toBeCloseTo(4 / 3);
    expect(pixelRatios).toEqual([1.5]);
    expect(sizeCalls).toEqual([[800, 600, false]]);
    expect(container.contains(handle.renderer.domElement)).toBe(true);
    expect(handle.scene.getObjectByName('character-readability-lighting')).toBeDefined();

    const ground = handle.scene.getObjectByName('character-ground') as Mesh;
    expect(ground).toBeDefined();

    let groundGeometryDisposed = false;
    let groundMaterialDisposed = false;
    ground.geometry.dispose = () => {
      groundGeometryDisposed = true;
    };
    (ground.material as Material).dispose = () => {
      groundMaterialDisposed = true;
    };

    handle.resize(1024, 512);

    expect(handle.camera.aspect).toBe(2);
    expect(sizeCalls.at(-1)).toEqual([1024, 512, false]);

    handle.dispose();

    expect(disposed).toBe(true);
    expect(groundGeometryDisposed).toBe(true);
    expect(groundMaterialDisposed).toBe(true);
    expect(container.contains(handle.renderer.domElement)).toBe(false);
  });

  it('maps renderer construction failure to an explicit typed initialization error', () => {
    const container = document.createElement('div');
    const context = {} as WebGL2RenderingContext;

    expect(() =>
      createRendererHandle({
        container,
        width: 800,
        height: 600,
        contextProbe: () => context,
        rendererFactory: () => {
          throw new Error('driver initialization failed');
        },
      }),
    ).toThrowError(RendererInitializationError);

    try {
      createRendererHandle({
        container,
        width: 800,
        height: 600,
        contextProbe: () => context,
        rendererFactory: () => {
          throw new Error('driver initialization failed');
        },
      });
    } catch (error) {
      expect(error).toMatchObject({
        code: 'renderer_initialization_failed',
        message: 'renderer_initialization_failed',
      });
    }
  });
});


describe('character readability lighting', () => {
  it('adds a bounded neutral key/fill/rim lighting rig as a separate scene responsibility', () => {
    const scene = new Scene();
    const rig = addCharacterReadabilityLighting(scene);

    expect(rig.name).toBe('character-readability-lighting');
    expect(scene.children).toContain(rig);
    expect(rig.children.map((child) => child.name)).toEqual([
      'character-key-light',
      'character-fill-light',
      'character-rim-light',
    ]);
    expect(rig.children.every((child) => child.type === 'DirectionalLight')).toBe(true);
  });
});


describe('minimal character environment', () => {
  it('adds only a subdued background and named ground plane baseline', () => {
    const scene = new Scene();
    const environment = createCharacterEnvironment(scene);

    expect(scene.background?.isColor).toBe(true);
    expect(environment.ground.name).toBe('character-ground');
    expect(environment.ground.geometry.type).toBe('PlaneGeometry');
    expect(environment.ground.rotation.x).toBeCloseTo(-Math.PI / 2);
    expect(scene.children).toEqual([environment.ground]);
  });
});
