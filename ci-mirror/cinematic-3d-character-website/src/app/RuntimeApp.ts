import { Vector3, type AnimationClip, type Object3D } from 'three';
import {
  AnimationCoordinator,
  type AnimationTransitionResult,
} from '../character/AnimationCoordinator';
import {
  applyCharacterMotion,
  stepCharacterMotion,
  type CharacterMotionState,
} from '../character/CharacterController';
import {
  CharacterCamera,
  type CharacterCameraConfig,
  type CharacterCameraSnapshot,
} from '../camera/CharacterCamera';
import { AssetLoadError, loadRuntimeCharacterAsset, type RuntimeCharacterAsset } from '../assets/AssetLoader';
import { TEST_CHARACTER_ASSET_MANIFEST, type RuntimeAssetManifest } from '../assets/AssetManifest';
import { KeyboardInput } from '../input/KeyboardInput';
import type { InputSnapshot } from '../input/InputActions';
import { PerformanceMonitor } from '../quality/PerformanceMonitor';
import {
  evaluateQualityPolicy,
  type QualityLevel,
  type QualityPolicyConfig,
} from '../quality/QualityPolicy';
import {
  createRendererHandle,
  RendererInitializationError,
  type RendererBootstrapOptions,
  type RendererHandle,
} from '../scene/Renderer';
import {
  reduceCharacterState,
  type CharacterDesiredState,
} from '../state/CharacterState';
import {
  reduceRuntimeState,
  type RuntimeState,
} from '../state/RuntimeState';
import { renderRuntimeOverlay } from '../ui/RuntimeOverlay';

export interface RuntimeInputPort {
  start(): void;
  stop(): void;
  snapshot(): InputSnapshot;
}

export interface RuntimeAnimationPort {
  transitionTo(desiredState: CharacterDesiredState): AnimationTransitionResult;
  update(deltaTime: number): void;
}

export interface RuntimeCameraPort {
  update(input: Parameters<CharacterCamera['update']>[0]): CharacterCameraSnapshot;
}

export interface RuntimeAppDependencies {
  readonly createRenderer: (options: RendererBootstrapOptions) => RendererHandle;
  readonly loadAsset: (manifest: RuntimeAssetManifest) => Promise<RuntimeCharacterAsset>;
  readonly createInput: (windowRef: Window, documentRef: Document) => RuntimeInputPort;
  readonly createAnimation: (
    root: Object3D,
    clips: readonly AnimationClip[],
  ) => RuntimeAnimationPort;
  readonly createCamera: (root: Object3D) => RuntimeCameraPort;
  readonly requestFrame: (callback: FrameRequestCallback) => number;
  readonly cancelFrame: (handle: number) => void;
  readonly now: () => number;
}

export interface RuntimeAppOptions {
  readonly root: HTMLElement;
  readonly windowRef: Window;
  readonly documentRef: Document;
  readonly manifest?: RuntimeAssetManifest;
  readonly dependencies?: Partial<RuntimeAppDependencies>;
}

const RUNTIME_CAMERA_CONFIG: CharacterCameraConfig = Object.freeze({
  followDistance: 5,
  followHeight: 2.5,
  presentationDistance: 4,
  presentationHeight: 2.1,
  upperBodyTargetHeight: 1.55,
  orbitHeight: 1.9,
  orbitMinRadius: 2,
  orbitMaxRadius: 6,
  damping: 8,
  maxInterpolationAlpha: 0.35,
});

const RUNTIME_QUALITY_POLICY: QualityPolicyConfig = Object.freeze({
  primaryTargetFps: 60,
  degradationTriggerFps: 45,
  minimumInteractiveFps: 30,
  requiredSustainedSamples: 120,
});

const PERFORMANCE_FRAME_WINDOW = 120;
const PERFORMANCE_MEMORY_WINDOW = 10;

function initialCameraPose(root: Object3D) {
  const position = root.position.clone().add(new Vector3(0, 2.1, 4));
  const target = root.position.clone().add(new Vector3(0, 1.55, 0));
  return { position, target };
}

function defaultDependencies(
  windowRef: Window,
  documentRef: Document,
): RuntimeAppDependencies {
  return {
    createRenderer: createRendererHandle,
    loadAsset: loadRuntimeCharacterAsset,
    createInput: (target, document) => new KeyboardInput(target, document),
    createAnimation: (root, clips) => new AnimationCoordinator(root, clips),
    createCamera: (root) =>
      new CharacterCamera(RUNTIME_CAMERA_CONFIG, initialCameraPose(root)),
    requestFrame: (callback) => windowRef.requestAnimationFrame(callback),
    cancelFrame: (handle) => windowRef.cancelAnimationFrame(handle),
    now: () => windowRef.performance.now(),
  };
}

function resolveRuntimeFailure(error: unknown): {
  readonly code:
    | 'unsupported_webgl2'
    | 'renderer_initialization_failed'
    | 'asset_load_failed'
    | 'runtime_failure';
  readonly message: string;
} {
  if (error instanceof RendererInitializationError) {
    return { code: error.code, message: error.message };
  }

  if (error instanceof AssetLoadError) {
    return { code: error.code, message: error.message };
  }

  return {
    code: 'runtime_failure',
    message: error instanceof Error ? error.message : 'runtime_failure',
  };
}

function viewportSize(root: HTMLElement, windowRef: Window): {
  readonly width: number;
  readonly height: number;
} {
  return {
    width: Math.max(1, root.clientWidth || windowRef.innerWidth || 1),
    height: Math.max(1, root.clientHeight || windowRef.innerHeight || 1),
  };
}

export class RuntimeApp {
  private readonly root: HTMLElement;
  private readonly windowRef: Window;
  private readonly documentRef: Document;
  private readonly manifest: RuntimeAssetManifest;
  private readonly dependencies: RuntimeAppDependencies;

  private runtimeState: RuntimeState = { mode: 'loading' };
  private desiredState: CharacterDesiredState = 'presentationIdle';
  private motionState: CharacterMotionState = {
    position: { x: 0, z: 0 },
    yaw: 0,
  };
  private qualityLevel: QualityLevel = 'high';

  private sceneHost: HTMLElement | null = null;
  private overlayHost: HTMLElement | null = null;
  private rendererHandle: RendererHandle | null = null;
  private characterRoot: Object3D | null = null;
  private input: RuntimeInputPort | null = null;
  private animation: RuntimeAnimationPort | null = null;
  private cameraController: RuntimeCameraPort | null = null;
  private performanceMonitor: PerformanceMonitor | null = null;
  private frameRequestId: number | null = null;
  private lastFrameTimestampMs: number | null = null;

  private started = false;
  private disposed = false;
  private inputStarted = false;
  private resizeRegistered = false;
  private running = false;

  public constructor(options: RuntimeAppOptions) {
    this.root = options.root;
    this.windowRef = options.windowRef;
    this.documentRef = options.documentRef;
    this.manifest = options.manifest ?? TEST_CHARACTER_ASSET_MANIFEST;
    this.dependencies = {
      ...defaultDependencies(options.windowRef, options.documentRef),
      ...options.dependencies,
    };
  }

  public get state(): RuntimeState {
    return this.runtimeState;
  }

  public async start(): Promise<void> {
    if (this.started || this.disposed) {
      return;
    }

    this.started = true;
    this.mountShell();
    this.updateOverlay();

    try {
      const viewport = viewportSize(this.root, this.windowRef);
      this.rendererHandle = this.dependencies.createRenderer({
        container: this.requireSceneHost(),
        width: viewport.width,
        height: viewport.height,
        pixelRatio: Math.max(1, this.windowRef.devicePixelRatio || 1),
      });
      this.registerResize();

      const asset = await this.dependencies.loadAsset(this.manifest);
      if (this.disposed) {
        return;
      }

      this.characterRoot = asset.root;
      this.rendererHandle.scene.add(asset.root);
      this.motionState = {
        position: {
          x: asset.root.position.x,
          z: asset.root.position.z,
        },
        yaw: asset.root.rotation.y,
      };

      this.input = this.dependencies.createInput(this.windowRef, this.documentRef);
      this.animation = this.dependencies.createAnimation(asset.root, asset.clips);
      this.cameraController = this.dependencies.createCamera(asset.root);
      this.performanceMonitor = new PerformanceMonitor({
        maxFrameSamples: PERFORMANCE_FRAME_WINDOW,
        maxMemorySamples: PERFORMANCE_MEMORY_WINDOW,
        startupStartedAtMs: this.dependencies.now(),
      });

      this.animation.transitionTo('presentationIdle');
      this.runtimeState = reduceRuntimeState(this.runtimeState, { type: 'assetsReady' });
      this.updateOverlay();

      this.input.start();
      this.inputStarted = true;
      this.desiredState = reduceCharacterState(this.desiredState, {
        type: 'interactionEnabled',
      });
      this.runtimeState = reduceRuntimeState(this.runtimeState, {
        type: 'interactionStarted',
      });
      this.performanceMonitor.markInteractive(this.dependencies.now());
      this.running = true;
      this.updateOverlay();
      this.scheduleFrame();
    } catch (error) {
      if (!this.disposed) {
        this.enterFallback(error);
      }
    }
  }

  public dispose(): void {
    if (this.disposed) {
      return;
    }

    this.disposed = true;
    this.releaseRuntimeSideEffects();
    this.root.replaceChildren();
    this.root.classList.remove('runtime-app');
  }

  private mountShell(): void {
    this.root.classList.add('runtime-app');
    this.root.tabIndex = 0;
    this.root.setAttribute('aria-label', '即時 3D 角色互動區域');

    const sceneHost = this.documentRef.createElement('div');
    sceneHost.className = 'runtime-app__scene';
    sceneHost.setAttribute('aria-hidden', 'true');

    const overlayHost = this.documentRef.createElement('div');
    overlayHost.className = 'runtime-app__overlay';

    this.root.replaceChildren(sceneHost, overlayHost);
    this.sceneHost = sceneHost;
    this.overlayHost = overlayHost;
  }

  private requireSceneHost(): HTMLElement {
    if (!this.sceneHost) {
      throw new Error('runtime_scene_host_missing');
    }

    return this.sceneHost;
  }

  private registerResize(): void {
    if (this.resizeRegistered) {
      return;
    }

    this.windowRef.addEventListener('resize', this.handleResize);
    this.resizeRegistered = true;
  }

  private readonly handleResize = (): void => {
    if (!this.rendererHandle) {
      return;
    }

    const viewport = viewportSize(this.root, this.windowRef);
    this.rendererHandle.resize(viewport.width, viewport.height);
  };

  private scheduleFrame(): void {
    if (!this.running || this.frameRequestId !== null) {
      return;
    }

    this.frameRequestId = this.dependencies.requestFrame(this.handleFrame);
  }

  private readonly handleFrame: FrameRequestCallback = (timestampMs): void => {
    this.frameRequestId = null;

    if (!this.running || this.disposed || this.runtimeState.mode !== 'interactive') {
      return;
    }

    try {
      const deltaTime =
        this.lastFrameTimestampMs === null
          ? 0
          : Math.max(0, (timestampMs - this.lastFrameTimestampMs) / 1000);
      const frameTimeMs =
        this.lastFrameTimestampMs === null
          ? null
          : Math.max(0, timestampMs - this.lastFrameTimestampMs);
      this.lastFrameTimestampMs = timestampMs;

      this.stepFrame(deltaTime, frameTimeMs);
      this.scheduleFrame();
    } catch (error) {
      this.enterFallback(error);
    }
  };

  private stepFrame(deltaTime: number, frameTimeMs: number | null): void {
    const input = this.requireInput().snapshot();
    this.desiredState = reduceCharacterState(this.desiredState, {
      type: 'input',
      input,
    });

    const motion = stepCharacterMotion(
      this.motionState,
      this.desiredState,
      input,
      deltaTime,
    );
    this.motionState = {
      position: motion.position,
      yaw: motion.yaw,
    };
    applyCharacterMotion(this.requireCharacterRoot(), motion);

    this.requireAnimation().transitionTo(this.desiredState);
    this.requireAnimation().update(deltaTime);

    const characterPosition = this.requireCharacterRoot().position;
    const camera = this.requireCamera().update({
      mode: 'follow',
      characterPosition,
      characterYaw: this.motionState.yaw,
      deltaTime,
    });
    this.applyCamera(camera);

    if (frameTimeMs !== null && frameTimeMs > 0) {
      this.requirePerformanceMonitor().recordFrameTime(frameTimeMs);
      // Task 11 samples the approved policy. It deliberately does not claim a
      // degradation action until an eligible character-safe target is wired.
      evaluateQualityPolicy(
        this.qualityLevel,
        this.requirePerformanceMonitor().snapshot(),
        RUNTIME_QUALITY_POLICY,
      );
    }

    const renderer = this.requireRenderer();
    renderer.renderer.render(renderer.scene, renderer.camera);
    this.updateOverlay();
  }

  private applyCamera(snapshot: CharacterCameraSnapshot): void {
    const renderer = this.requireRenderer();
    renderer.camera.position.copy(snapshot.position);
    renderer.camera.lookAt(snapshot.target);
  }

  private updateOverlay(): void {
    if (!this.overlayHost) {
      return;
    }

    const overlay = renderRuntimeOverlay(this.documentRef, {
      state: this.runtimeState,
      loadingProgress: this.runtimeState.mode === 'loading' ? null : undefined,
      interactionFocused: this.documentRef.hasFocus(),
      qualityLevel: this.qualityLevel,
    });

    this.overlayHost.replaceChildren(overlay);
  }

  private enterFallback(error: unknown): void {
    const failure = resolveRuntimeFailure(error);
    this.runtimeState = reduceRuntimeState(this.runtimeState, {
      type: 'runtimeError',
      code: failure.code,
      message: failure.message,
    });
    this.releaseRuntimeSideEffects();
    this.updateOverlay();
  }

  private releaseRuntimeSideEffects(): void {
    this.running = false;

    if (this.frameRequestId !== null) {
      this.dependencies.cancelFrame(this.frameRequestId);
      this.frameRequestId = null;
    }

    if (this.inputStarted) {
      this.input?.stop();
      this.inputStarted = false;
    }

    if (this.resizeRegistered) {
      this.windowRef.removeEventListener('resize', this.handleResize);
      this.resizeRegistered = false;
    }

    if (this.characterRoot?.parent) {
      this.characterRoot.parent.remove(this.characterRoot);
    }

    if (this.rendererHandle) {
      this.rendererHandle.dispose();
      this.rendererHandle = null;
    }

    this.lastFrameTimestampMs = null;
  }

  private requireRenderer(): RendererHandle {
    if (!this.rendererHandle) {
      throw new Error('renderer_not_initialized');
    }
    return this.rendererHandle;
  }

  private requireCharacterRoot(): Object3D {
    if (!this.characterRoot) {
      throw new Error('character_not_loaded');
    }
    return this.characterRoot;
  }

  private requireInput(): RuntimeInputPort {
    if (!this.input) {
      throw new Error('input_not_initialized');
    }
    return this.input;
  }

  private requireAnimation(): RuntimeAnimationPort {
    if (!this.animation) {
      throw new Error('animation_not_initialized');
    }
    return this.animation;
  }

  private requireCamera(): RuntimeCameraPort {
    if (!this.cameraController) {
      throw new Error('camera_not_initialized');
    }
    return this.cameraController;
  }

  private requirePerformanceMonitor(): PerformanceMonitor {
    if (!this.performanceMonitor) {
      throw new Error('performance_monitor_not_initialized');
    }
    return this.performanceMonitor;
  }
}
