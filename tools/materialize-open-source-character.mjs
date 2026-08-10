import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const ASSETS = [
  {
    label: 'Quaternius Man in Suit',
    sourceUrl:
      'https://raw.githubusercontent.com/schulerj89/vanta-city/a3fbd53398d6712742f34170a54cb450c90b1f80/public/assets/characters/animated-men/raze-suit.glb',
    expectedSize: 583416,
    expectedGitBlobSha1: 'd5309cdc6ace341f308ee7525637701587926c59',
    expectedSha256: '31ff1539e7a9a209d4eb1107e696d798fedc7e35d84a58bbabfdc0f1b8b73763',
    outputPath: path.resolve('public/assets/quaternius-man-in-suit.glb'),
  },
  {
    label: 'CesiumMan fallback',
    sourceUrl:
      'https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf/Models/CesiumMan/glTF-Binary/CesiumMan.glb',
    expectedSize: 438044,
    expectedGitBlobSha1: '8586c4e6a59bf8ef585c2a685c50a80d28503216',
    expectedSha256: 'b7001eaeea8254bd44773bcd247e78696d94169388fbb2a1800fc69434e777d9',
    outputPath: path.resolve('public/assets/cesium-man.glb'),
  },
];

function digest(algorithm, data) {
  return createHash(algorithm).update(data).digest('hex');
}

function gitBlobSha1(data) {
  return digest('sha1', Buffer.concat([Buffer.from(`blob ${data.length}\0`), data]));
}

function verify(asset, data) {
  if (data.length !== asset.expectedSize) {
    throw new Error(
      `${asset.label} byte length mismatch: ${data.length} !== ${asset.expectedSize}`,
    );
  }

  const sha1 = gitBlobSha1(data);
  if (sha1 !== asset.expectedGitBlobSha1) {
    throw new Error(`${asset.label} Git blob SHA-1 mismatch: ${sha1}`);
  }

  const sha256 = digest('sha256', data);
  if (sha256 !== asset.expectedSha256) {
    throw new Error(`${asset.label} SHA-256 mismatch: ${sha256}`);
  }

  if (data.subarray(0, 4).toString('ascii') !== 'glTF' || data.readUInt32LE(4) !== 2) {
    throw new Error(`${asset.label} is not a valid glTF 2.0 binary container`);
  }

  if (data.readUInt32LE(8) !== data.length) {
    throw new Error(`${asset.label} glTF declared byte length does not match the downloaded file`);
  }

  return sha256;
}

async function existingVerifiedAsset(asset) {
  try {
    const data = await readFile(asset.outputPath);
    verify(asset, data);
    return data;
  } catch {
    return null;
  }
}

async function materialize(asset) {
  const existing = await existingVerifiedAsset(asset);
  if (existing) {
    console.log(`${asset.label} already materialized and verified: ${asset.outputPath}`);
    return;
  }

  const response = await fetch(asset.sourceUrl, { redirect: 'follow' });
  if (!response.ok) {
    throw new Error(`${asset.label} download failed: HTTP ${response.status}`);
  }

  const data = Buffer.from(await response.arrayBuffer());
  const sha256 = verify(asset, data);
  await mkdir(path.dirname(asset.outputPath), { recursive: true });
  await writeFile(asset.outputPath, data);
  console.log(`${asset.label} materialized: ${asset.outputPath}`);
  console.log(`bytes=${data.length} sha256=${sha256}`);
}

for (const asset of ASSETS) {
  await materialize(asset);
}
