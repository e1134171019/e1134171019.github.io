export type RuntimeAssetClass = 'nonfinal_test_fixture';

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

export const TEST_CHARACTER_ASSET_MANIFEST = {
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
