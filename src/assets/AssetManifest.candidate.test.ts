import { describe, expect, it } from 'vitest';
import { OPEN_SOURCE_CHARACTER_ASSET_MANIFEST } from './AssetManifest';

describe('OPEN_SOURCE_CHARACTER_ASSET_MANIFEST', () => {
  it('pins CesiumMan as a non-final open-source character candidate', () => {
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.assetId).toBe('khronos-cesium-man-open-source-candidate');
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.runtimeUrl).toBe('/assets/cesium-man.glb');
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.assetClass).toBe('open_source_character_candidate');
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.finalAsset).toBe(false);
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.equivalentToFinal).toBe(false);
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sourceRepositoryCommit).toBe(
      '2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sourceBlobSha1).toBe(
      '8586c4e6a59bf8ef585c2a685c50a80d28503216',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.byteLength).toBe(438044);
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sha256).toBe(
      'b7001eaeea8254bd44773bcd247e78696d94169388fbb2a1800fc69434e777d9',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.licenseSpdx).toBe('CC-BY-4.0');
  });
});
