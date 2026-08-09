import type { AnimationClip, Object3D } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import type { RuntimeAssetManifest } from './AssetManifest';

export interface LoadedGltfBoundaryResult {
  readonly scene: Object3D;
  readonly animations: AnimationClip[];
}

export interface GltfLoaderBoundary {
  loadAsync(url: string): Promise<LoadedGltfBoundaryResult>;
}

export interface RuntimeCharacterAsset {
  readonly root: Object3D;
  readonly clips: AnimationClip[];
  readonly manifest: RuntimeAssetManifest;
}

export class AssetLoadError extends Error {
  readonly code = 'asset_load_failed' as const;
  readonly manifest: RuntimeAssetManifest;

  constructor(manifest: RuntimeAssetManifest, cause: unknown) {
    super('asset_load_failed', { cause });
    this.name = 'AssetLoadError';
    this.manifest = manifest;
  }
}

export async function loadRuntimeCharacterAsset(
  manifest: RuntimeAssetManifest,
  loader: GltfLoaderBoundary = new GLTFLoader(),
): Promise<RuntimeCharacterAsset> {
  try {
    const gltf = await loader.loadAsync(manifest.runtimeUrl);

    return {
      root: gltf.scene,
      clips: gltf.animations,
      manifest,
    };
  } catch (cause) {
    throw new AssetLoadError(manifest, cause);
  }
}
