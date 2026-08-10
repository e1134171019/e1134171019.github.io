import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const SOURCE_URL =
  'https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf/Models/CesiumMan/glTF-Binary/CesiumMan.glb';
const EXPECTED_SIZE = 438044;
const EXPECTED_GIT_BLOB_SHA1 = '8586c4e6a59bf8ef585c2a685c50a80d28503216';
const EXPECTED_SHA256 = 'b7001eaeea8254bd44773bcd247e78696d94169388fbb2a1800fc69434e777d9';
const OUTPUT_PATH = path.resolve('public/assets/cesium-man.glb');

function digest(algorithm, data) {
  return createHash(algorithm).update(data).digest('hex');
}

function gitBlobSha1(data) {
  return digest('sha1', Buffer.concat([Buffer.from(`blob ${data.length}\0`), data]));
}

function verify(data) {
  if (data.length !== EXPECTED_SIZE) {
    throw new Error(`CesiumMan byte length mismatch: ${data.length} !== ${EXPECTED_SIZE}`);
  }
  const sha1 = gitBlobSha1(data);
  if (sha1 !== EXPECTED_GIT_BLOB_SHA1) {
    throw new Error(`CesiumMan Git blob SHA-1 mismatch: ${sha1}`);
  }
  const sha256 = digest('sha256', data);
  if (sha256 !== EXPECTED_SHA256) {
    throw new Error(`CesiumMan SHA-256 mismatch: ${sha256}`);
  }
  if (data.subarray(0, 4).toString('ascii') !== 'glTF' || data.readUInt32LE(4) !== 2) {
    throw new Error('CesiumMan is not a valid glTF 2.0 binary container');
  }
  return sha256;
}

async function existingVerifiedAsset() {
  try {
    const data = await readFile(OUTPUT_PATH);
    verify(data);
    return data;
  } catch {
    return null;
  }
}

const existing = await existingVerifiedAsset();
if (existing) {
  console.log(`CesiumMan already materialized and verified: ${OUTPUT_PATH}`);
  process.exit(0);
}

const response = await fetch(SOURCE_URL, { redirect: 'follow' });
if (!response.ok) {
  throw new Error(`CesiumMan download failed: HTTP ${response.status}`);
}

const data = Buffer.from(await response.arrayBuffer());
const sha256 = verify(data);
await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
await writeFile(OUTPUT_PATH, data);
console.log(`CesiumMan materialized: ${OUTPUT_PATH}`);
console.log(`bytes=${data.length} sha256=${sha256}`);
