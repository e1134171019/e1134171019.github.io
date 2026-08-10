function finitePositive(values) {
  return values.filter((value) => Number.isFinite(value) && value > 0);
}

function percentile(sortedValues, fraction) {
  if (sortedValues.length === 0) return null;
  const index = Math.max(0, Math.ceil(fraction * sortedValues.length) - 1);
  return sortedValues[index];
}

export function summarizeFrameTimes(frameTimesMs) {
  const sorted = finitePositive(frameTimesMs).sort((a, b) => a - b);
  if (sorted.length === 0) {
    return {
      sampleCount: 0,
      medianFrameMs: null,
      p95FrameMs: null,
      medianFps: null,
    };
  }

  const midpoint = Math.floor(sorted.length / 2);
  const medianFrameMs =
    sorted.length % 2 === 0
      ? (sorted[midpoint - 1] + sorted[midpoint]) / 2
      : sorted[midpoint];

  return {
    sampleCount: sorted.length,
    medianFrameMs,
    p95FrameMs: percentile(sorted, 0.95),
    medianFps: 1000 / medianFrameMs,
  };
}

export function evaluateRuntimePolicy(fps) {
  const validFps = Number.isFinite(fps) ? fps : 0;
  return {
    primaryTargetPass: validFps >= 60,
    degradationReview: validFps < 45,
    minimumInteractivePass: validFps >= 30,
  };
}

export function memoryGrowthRatio(baselineBytes, finalBytes) {
  if (
    !Number.isFinite(baselineBytes) ||
    !Number.isFinite(finalBytes) ||
    baselineBytes <= 0
  ) {
    return null;
  }

  return (finalBytes - baselineBytes) / baselineBytes;
}
