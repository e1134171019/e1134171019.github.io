import { readFileSync, writeFileSync } from 'node:fs';

const baseline = JSON.parse(
  readFileSync('dist-task13b-baseline/task13b-bundle-evidence.json', 'utf8'),
);
const split = JSON.parse(
  readFileSync('dist-task13b-split/task13b-bundle-evidence.json', 'utf8'),
);

const baselineRendered = Object.values(baseline.totals.categoryRenderedBytes).reduce(
  (sum, value) => sum + Number(value),
  0,
);
const threeRendered = Number(baseline.totals.categoryRenderedBytes.three ?? 0);
const threeRenderedShare = baselineRendered > 0 ? threeRendered / baselineRendered : 0;

const delta = {
  codeBytes: split.totals.codeBytes - baseline.totals.codeBytes,
  gzipBytes: split.totals.gzipBytes - baseline.totals.gzipBytes,
  brotliBytes: split.totals.brotliBytes - baseline.totals.brotliBytes,
  chunkCount: split.chunks.length - baseline.chunks.length,
};

const report = {
  schemaVersion: 1,
  sourceCarrierCommit: baseline.sourceCarrierCommit,
  baseline: {
    totals: baseline.totals,
    chunkCount: baseline.chunks.length,
    chunks: baseline.chunks.map(({ fileName, codeBytes, gzipBytes, brotliBytes, categoryRenderedBytes }) => ({
      fileName,
      codeBytes,
      gzipBytes,
      brotliBytes,
      categoryRenderedBytes,
    })),
  },
  threeComposition: {
    renderedBytes: threeRendered,
    renderedShare: threeRenderedShare,
  },
  splitExperiment: {
    totals: split.totals,
    chunkCount: split.chunks.length,
    chunks: split.chunks.map(({ fileName, codeBytes, gzipBytes, brotliBytes, categoryRenderedBytes }) => ({
      fileName,
      codeBytes,
      gzipBytes,
      brotliBytes,
      categoryRenderedBytes,
    })),
    deltaVsBaseline: delta,
  },
  interpretationRules: {
    warningIsNotFailure: true,
    doNotRaiseWarningLimitToHideFinding: true,
    splitMustNotBeCalledPayloadReductionUnlessTotalCompressedBytesDecrease: true,
    splitRequiresRuntimeSmokeBeforeAdoption: true,
  },
};

writeFileSync('task13b-bundle-comparison.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
