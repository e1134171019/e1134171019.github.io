import { AnimationClip, Group } from 'three';
import { describe, expect, it, vi } from 'vitest';
import {
  AssetLoadError,
  loadRuntimeCharacterAsset,
  type GltfLoaderBoundary,
} from './AssetLoader';
import { TEST_CHARACTER_ASSET_MANIFEST } from './AssetManifest';

describe('provenance-tracked runtime GLB loading', () => {
  it('loads the manifest URL through the injected boundary and preserves the exact provenance manifest', async () => {
    const root = new Group();
    const clips = [new AnimationClip('fixture-clip', 1, [])];
    const loadAsync = vi.fn().mockResolvedValue({ scene: root, animations: clips });
    const loader: GltfLoaderBoundary = { loadAsync };

    const asset = await loadRuntimeCharacterAsset(TEST_CHARACTER_ASSET_MANIFEST, loader);

    expect(loadAsync).toHaveBeenCalledOnce();
    expect(loadAsync).toHaveBeenCalledWith(TEST_CHARACTER_ASSET_MANIFEST.runtimeUrl);
    expect(asset.root).toBe(root);
    expect(asset.clips).toBe(clips);
    expect(asset.manifest).toBe(TEST_CHARACTER_ASSET_MANIFEST);
    expect(asset.manifest.finalAsset).toBe(false);
    expect(asset.manifest.equivalentToFinal).toBe(false);
    expect(asset.manifest.assetClass).toBe(TEST_CHARACTER_ASSET_MANIFEST.assetClass);
    expect(asset.manifest.provenance.sha256).toBe(
      TEST_CHARACTER_ASSET_MANIFEST.provenance.sha256,
    );
  });

  it('maps loader rejection to a typed asset_load_failed error instead of returning undefined', async () => {
    const sourceError = new Error('fixture fetch failed');
    const loader: GltfLoaderBoundary = {
      loadAsync: vi.fn().mockRejectedValue(sourceError),
    };

    const promise = loadRuntimeCharacterAsset(TEST_CHARACTER_ASSET_MANIFEST, loader);

    await expect(promise).rejects.toBeInstanceOf(AssetLoadError);
    await expect(promise).rejects.toMatchObject({
      code: 'asset_load_failed',
      message: 'asset_load_failed',
      manifest: TEST_CHARACTER_ASSET_MANIFEST,
      cause: sourceError,
    });
  });
});
