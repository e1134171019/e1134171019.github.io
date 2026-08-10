export type RuntimeAssetClass = 'nonfinal_test_fixture' | 'open_source_character_candidate';

export interface RuntimeAssetProvenance {
  readonly assetTitle: string;
  readonly sourceUrl: string;
  readonly sourceOwner: string;
  readonly sourceRepository: string;
  readonly sourceRepositoryCommit: string;
  readonly sourcePath: string;
  readonly sourceBlobSha1: string;
  readonly licenseSpdx: string;
  readonly attribution: string;
  readonly materializedAt: string;
  readonly byteLength: number;
  readonly sha256: string;
}

export interface RuntimeAssetManifest {
  readonly assetId: string;
  readonly runtimeUrl: string;
  readonly assetClass: RuntimeAssetClass;
  readonly finalAsset: false;
  readonly equivalentToFinal: false;
  readonly adaptations: readonly string[];
  readonly provenance: RuntimeAssetProvenance;
}

export const BOX_TEST_ASSET_MANIFEST = {
  assetId: 'khronos-box-nonfinal-loader-fixture',
  runtimeUrl: '/assets/test-character.glb',
  assetClass: 'nonfinal_test_fixture',
  finalAsset: false,
  equivalentToFinal: false,
  adaptations: [],
  provenance: {
    assetTitle: 'Box',
    sourceUrl:
      'https://github.com/KhronosGroup/glTF-Sample-Assets/blob/2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf/Models/Box/glTF-Binary/Box.glb',
    sourceOwner: 'Cesium',
    sourceRepository: 'KhronosGroup/glTF-Sample-Assets',
    sourceRepositoryCommit: '2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf',
    sourcePath: 'Models/Box/glTF-Binary/Box.glb',
    sourceBlobSha1: '95ec886b6b92b134291fd41d34ac9d5349306e0a',
    licenseSpdx: 'CC-BY-4.0',
    attribution: 'Cesium, 2017; distributed through KhronosGroup/glTF-Sample-Assets',
    materializedAt: '2026-08-10T01:58:13+08:00',
    byteLength: 1664,
    sha256: 'ed52f7192b8311d700ac0ce80644e3852cd01537e4d62241b9acba023da3d54e',
  },
} as const satisfies RuntimeAssetManifest;

export const CESIUM_MAN_FALLBACK_ASSET_MANIFEST = {
  assetId: 'khronos-cesium-man-open-source-candidate',
  runtimeUrl: '/assets/cesium-man.glb',
  assetClass: 'open_source_character_candidate',
  finalAsset: false,
  equivalentToFinal: false,
  adaptations: [
    'materialized from an exact upstream commit with byte-length, Git blob SHA-1, and SHA-256 verification',
    'single unnamed source animation intentionally remains unmapped to semantic idle/walk/action states',
  ],
  provenance: {
    assetTitle: 'CesiumMan',
    sourceUrl:
      'https://github.com/KhronosGroup/glTF-Sample-Assets/blob/2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf/Models/CesiumMan/glTF-Binary/CesiumMan.glb',
    sourceOwner: 'Cesium',
    sourceRepository: 'KhronosGroup/glTF-Sample-Assets',
    sourceRepositoryCommit: '2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf',
    sourcePath: 'Models/CesiumMan/glTF-Binary/CesiumMan.glb',
    sourceBlobSha1: '8586c4e6a59bf8ef585c2a685c50a80d28503216',
    licenseSpdx: 'CC-BY-4.0',
    attribution:
      'Cesium, 2017; distributed through KhronosGroup/glTF-Sample-Assets; Cesium trademark/logo limitations remain applicable',
    materializedAt: '2026-08-10T09:53:06Z',
    byteLength: 438044,
    sha256: 'b7001eaeea8254bd44773bcd247e78696d94169388fbb2a1800fc69434e777d9',
  },
} as const satisfies RuntimeAssetManifest;

export const OPEN_SOURCE_CHARACTER_ASSET_MANIFEST = {
  assetId: 'quaternius-man-in-suit-open-source-candidate',
  runtimeUrl: '/assets/quaternius-man-in-suit.glb',
  assetClass: 'open_source_character_candidate',
  finalAsset: false,
  equivalentToFinal: false,
  adaptations: [
    'uses the unmodified Quaternius Man in Suit GLB mirrored at an exact public GitHub commit after Poly Pizza provenance and CC0 were independently checked',
    'materialized with byte-length, Git blob SHA-1, SHA-256, and glTF 2.0 container verification',
    'embedded Idle/Walk/Run clips are eligible for the existing semantic animation selector; Punch is preserved but is not forcibly remapped to the generic action semantic',
    'the previously verified CesiumMan candidate remains available as an explicit fallback manifest',
  ],
  provenance: {
    assetTitle: 'Man in Suit',
    sourceUrl: 'https://poly.pizza/m/mQnGoME1ez',
    sourceOwner: 'Quaternius',
    sourceRepository: 'schulerj89/vanta-city',
    sourceRepositoryCommit: 'a3fbd53398d6712742f34170a54cb450c90b1f80',
    sourcePath: 'public/assets/characters/animated-men/raze-suit.glb',
    sourceBlobSha1: 'd5309cdc6ace341f308ee7525637701587926c59',
    licenseSpdx: 'CC0-1.0',
    attribution:
      'Quaternius, Man in Suit from Animated Men Pack, CC0 1.0; unmodified browser-ready GLB mirrored by schulerj89/vanta-city at the pinned commit',
    materializedAt: '2026-08-10T10:39:04Z',
    byteLength: 583416,
    sha256: '31ff1539e7a9a209d4eb1107e696d798fedc7e35d84a58bbabfdc0f1b8b73763',
  },
} as const satisfies RuntimeAssetManifest;

// RuntimeApp imports this legacy symbol as its default asset selection.
// Keep the symbol stable while the selected candidate changes underneath it.
export const TEST_CHARACTER_ASSET_MANIFEST = OPEN_SOURCE_CHARACTER_ASSET_MANIFEST;
