import { describe, expect, it } from 'vitest';
import {
  CESIUM_MAN_FALLBACK_ASSET_MANIFEST,
  OPEN_SOURCE_CHARACTER_ASSET_MANIFEST,
} from './AssetManifest';

describe('OPEN_SOURCE_CHARACTER_ASSET_MANIFEST', () => {
  it('pins Quaternius Man in Suit as the non-final runtime candidate', () => {
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.assetId).toBe(
      'quaternius-man-in-suit-open-source-candidate',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.runtimeUrl).toBe(
      '/assets/quaternius-man-in-suit.glb',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.assetClass).toBe(
      'open_source_character_candidate',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.finalAsset).toBe(false);
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.equivalentToFinal).toBe(false);
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sourceOwner).toBe('Quaternius');
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sourceRepository).toBe(
      'schulerj89/vanta-city',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sourceRepositoryCommit).toBe(
      'a3fbd53398d6712742f34170a54cb450c90b1f80',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sourceBlobSha1).toBe(
      'd5309cdc6ace341f308ee7525637701587926c59',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.byteLength).toBe(583416);
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.sha256).toBe(
      '31ff1539e7a9a209d4eb1107e696d798fedc7e35d84a58bbabfdc0f1b8b73763',
    );
    expect(OPEN_SOURCE_CHARACTER_ASSET_MANIFEST.provenance.licenseSpdx).toBe('CC0-1.0');
  });

  it('retains the previously verified CesiumMan candidate as an explicit fallback', () => {
    expect(CESIUM_MAN_FALLBACK_ASSET_MANIFEST.assetId).toBe(
      'khronos-cesium-man-open-source-candidate',
    );
    expect(CESIUM_MAN_FALLBACK_ASSET_MANIFEST.runtimeUrl).toBe('/assets/cesium-man.glb');
    expect(CESIUM_MAN_FALLBACK_ASSET_MANIFEST.finalAsset).toBe(false);
    expect(CESIUM_MAN_FALLBACK_ASSET_MANIFEST.equivalentToFinal).toBe(false);
    expect(CESIUM_MAN_FALLBACK_ASSET_MANIFEST.provenance.sha256).toBe(
      'b7001eaeea8254bd44773bcd247e78696d94169388fbb2a1800fc69434e777d9',
    );
  });
});
