import test from 'node:test';
import assert from 'node:assert/strict';

const metrics = await import('./task13c-metrics.mjs').catch(() => null);

test('Task 13C metrics module exists before validation can be green', () => {
  assert.ok(metrics, 'task13c-metrics.mjs must exist');
});

test('summarizeFrameTimes reports median and p95 runtime frame time', { skip: !metrics }, () => {
  const summary = metrics.summarizeFrameTimes([16, 17, 16, 18, 17]);
  assert.equal(summary.sampleCount, 5);
  assert.equal(summary.medianFrameMs, 17);
  assert.equal(summary.p95FrameMs, 18);
  assert.ok(summary.medianFps > 58 && summary.medianFps < 59);
});

test('evaluateRuntimePolicy preserves the approved 60/45/30 thresholds', { skip: !metrics }, () => {
  assert.deepEqual(metrics.evaluateRuntimePolicy(60), {
    primaryTargetPass: true,
    degradationReview: false,
    minimumInteractivePass: true,
  });
  assert.deepEqual(metrics.evaluateRuntimePolicy(44.9), {
    primaryTargetPass: false,
    degradationReview: true,
    minimumInteractivePass: true,
  });
  assert.deepEqual(metrics.evaluateRuntimePolicy(29.9), {
    primaryTargetPass: false,
    degradationReview: true,
    minimumInteractivePass: false,
  });
});

test('memory growth is measured relative to the settled baseline', { skip: !metrics }, () => {
  assert.equal(metrics.memoryGrowthRatio(100, 110), 0.1);
  assert.equal(metrics.memoryGrowthRatio(0, 110), null);
  assert.equal(metrics.memoryGrowthRatio(null, 110), null);
});
