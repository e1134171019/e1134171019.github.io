import { describe, expect, it, vi } from 'vitest';
import {
  Object3D,
  PerspectiveCamera,
  Scene,
  Vector3,
  type AnimationClip,
  type WebGLRenderer,
} from 'three';
import { RendererInitializationError, type RendererHandle } from '../scene/Renderer';
import { TEST_CHARACTER_ASSET_MANIFEST, type RuntimeAssetManifest } from '../assets/AssetManifest';
import type { RuntimeCharacterAsset } from '../assets/AssetLoader';
import type { InputSnapshot } from '../input/InputActions';
import type { CharacterDesiredState } from '../state/CharacterState';
import type { CharacterCameraUpdateInput, CharacterCameraSnapshot } from '../camera/CharacterCamera';
import type { AnimationTransitionResult } from '../character/AnimationCoordinator';
import { RuntimeApp, type RuntimeAppDependencies } from './RuntimeApp';

const EMPTY_INPUT: InputSnapshot = {
  held: {
    moveForward: false,
    moveBackward: false,
    turnLeft: false,
    turnRight: false,
  },
  pressed: { primaryAction: false },
};

interface Harness {
  readonly root: HTMLElement;
  readonly character: Object3D;
  readonly dependencies: RuntimeAppDependencies;
  readonly input: {
    start: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
    snapshot: ReturnType<typeof vi.fn>;
  };
  readonly rendererDispose: ReturnType<typeof vi.fn>;
  readonly rendererRender: ReturnType<typeof vi.fn>;
  readonly animation: {
    transitionTo: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
  };
  readonly cancelFrame: ReturnType<typeof vi.fn>;
  readonly requestedFrames: Array<FrameRequestCallback>;
}

function createHarness(overrides: Partial<RuntimeAppDependencies> = {}): Harness {
  const root = document.createElement('main');
  document.body.replaceChildren(root);

  const scene = new Scene();
  const camera = new PerspectiveCamera();
  const canvas = document.createElement('canvas');
  const rendererDispose = vi.fn();
  const rendererRender = vi.fn();
  const renderer = {
    domElement: canvas,
    render: rendererRender,
  } as unknown as WebGLRenderer;
  const rendererHandle: RendererHandle = {
    scene,
    camera,
    renderer,
    resize: vi.fn(),
    dispose: rendererDispose,
  };

  const character = new Object3D();
  const asset: RuntimeCharacterAsset = {
    root: character,
    clips: [] as AnimationClip[],
    manifest: TEST_CHARACTER_ASSET_MANIFEST,
  };

  const input = {
    start: vi.fn(),
    stop: vi.fn(),
    snapshot: vi.fn(() => EMPTY_INPUT),
  };

  const animation = {
    transitionTo: vi.fn(
      (desiredState: CharacterDesiredState): AnimationTransitionResult => ({
        desiredState,
        actualAnimationState: 'none',
        selectedClipName: null,
        usedFallback: true,
        transition: 'none',
      }),
    ),
    update: vi.fn(() => []),
    dispose: vi.fn(),
  };

  const cameraController = {
    update: vi.fn(
      (update: CharacterCameraUpdateInput): CharacterCameraSnapshot => ({
        mode: update.mode,
        position: new Vector3(0, 2, 5),
        target: new Vector3(0, 1.5, 0),
      }),
    ),
  };

  const requestedFrames: FrameRequestCallback[] = [];
  const cancelFrame = vi.fn();

  const dependencies: RuntimeAppDependencies = {
    createRenderer: vi.fn(() => rendererHandle),
    loadAsset: vi.fn(async (_manifest: RuntimeAssetManifest) => asset),
    createInput: vi.fn(() => input),
    createAnimation: vi.fn(() => animation),
    createCamera: vi.fn(() => cameraController),
    requestFrame: vi.fn((callback: FrameRequestCallback) => {
      requestedFrames.push(callback);
      return requestedFrames.length;
    }),
    cancelFrame,
    now: vi.fn(() => 100),
    ...overrides,
  };

  return {
    root,
    character,
    dependencies,
    input,
    rendererDispose,
    rendererRender,
    animation,
    cancelFrame,
    requestedFrames,
  };
}

describe('RuntimeApp lifecycle', () => {
  it('reaches interactive after renderer and asset initialization succeed', async () => {
    const harness = createHarness();
    const app = new RuntimeApp({
      root: harness.root,
      windowRef: window,
      documentRef: document,
      dependencies: harness.dependencies,
    });

    await app.start();

    expect(app.state.mode).toBe('interactive');
    expect(harness.input.start).toHaveBeenCalledTimes(1);
    expect(harness.requestedFrames).toHaveLength(1);
    expect(harness.root.querySelector('[data-runtime-mode="interactive"]')).not.toBeNull();
    expect(harness.character.parent).toBeInstanceOf(Scene);
  });

  it('applies the selected asset runtime transform to the loaded character root', async () => {
    const harness = createHarness();
    const app = new RuntimeApp({
      root: harness.root,
      windowRef: window,
      documentRef: document,
      dependencies: harness.dependencies,
    });

    await app.start();

    expect(harness.character.scale.x).toBeCloseTo(0.369, 6);
    expect(harness.character.scale.y).toBeCloseTo(0.369, 6);
    expect(harness.character.scale.z).toBeCloseTo(0.369, 6);
    expect(harness.character.rotation.y).toBeCloseTo(Math.PI, 6);
  });

  it('maps renderer initialization failure to explicit fallback without starting input or frames', async () => {
    const harness = createHarness({
      createRenderer: vi.fn(() => {
        throw new RendererInitializationError('unsupported_webgl2', 'unsupported_webgl2');
      }),
    });
    const app = new RuntimeApp({
      root: harness.root,
      windowRef: window,
      documentRef: document,
      dependencies: harness.dependencies,
    });

    await app.start();

    expect(app.state).toMatchObject({
      mode: 'fallback',
      error: { code: 'unsupported_webgl2' },
    });
    expect(harness.input.start).not.toHaveBeenCalled();
    expect(harness.requestedFrames).toHaveLength(0);
    expect(harness.root.textContent).toContain('unsupported_webgl2');
  });

  it('consumes semantic action completion and progresses back to interactive idle', async () => {
    const harness = createHarness();
    harness.input.snapshot
      .mockReturnValueOnce({
        held: EMPTY_INPUT.held,
        pressed: { primaryAction: true },
      })
      .mockReturnValue(EMPTY_INPUT);
    harness.animation.update
      .mockReturnValueOnce([{ type: 'actionCompleted' }])
      .mockReturnValue([]);

    const app = new RuntimeApp({
      root: harness.root,
      windowRef: window,
      documentRef: document,
      dependencies: harness.dependencies,
    });

    await app.start();
    harness.requestedFrames[0]?.(16);

    expect(harness.root.getAttribute('data-state')).toBe('returnToIdle');

    harness.requestedFrames[1]?.(32);
    expect(harness.root.getAttribute('data-state')).toBe('interactiveIdle');
  });

  it('preserves held forward movement when semantic action completion is consumed', async () => {
    const harness = createHarness();
    const actionWhileMoving: InputSnapshot = {
      held: {
        ...EMPTY_INPUT.held,
        moveForward: true,
      },
      pressed: { primaryAction: true },
    };
    harness.input.snapshot.mockReturnValue(actionWhileMoving);
    harness.animation.update
      .mockReturnValueOnce([{ type: 'actionCompleted' }])
      .mockReturnValue([]);

    const app = new RuntimeApp({
      root: harness.root,
      windowRef: window,
      documentRef: document,
      dependencies: harness.dependencies,
    });

    await app.start();
    harness.requestedFrames[0]?.(16);

    expect(harness.root.getAttribute('data-state')).toBe('move');
  });

  it('dispose stops input and animation-frame side effects idempotently', async () => {
    const harness = createHarness();
    const app = new RuntimeApp({
      root: harness.root,
      windowRef: window,
      documentRef: document,
      dependencies: harness.dependencies,
    });

    await app.start();
    const scheduledFrame = harness.requestedFrames[0];
    expect(scheduledFrame).toBeDefined();

    app.dispose();
    app.dispose();

    expect(harness.input.stop).toHaveBeenCalledTimes(1);
    expect(harness.cancelFrame).toHaveBeenCalledTimes(1);
    expect(harness.rendererDispose).toHaveBeenCalledTimes(1);
    expect(harness.animation.dispose).toHaveBeenCalledTimes(1);

    scheduledFrame?.(16);
    expect(harness.input.snapshot).not.toHaveBeenCalled();
    expect(harness.rendererRender).not.toHaveBeenCalled();
  });
});
