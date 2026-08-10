import { describe, expect, it } from 'vitest';
import { PerformanceMonitor } from './PerformanceMonitor';
import {
  evaluateQualityPolicy,
  type QualityPolicyConfig,
} from './QualityPolicy';

const POLICY: QualityPolicyConfig = {
  primaryTargetFps: 60,
  degradationTriggerFps: 45,
  minimumInteractiveFps: 30,
  requiredSustainedSamples: 4,
};

function monitorWithFpsSamples(samples: readonly number[]): PerformanceMonitor {
  const monitor = new PerformanceMonitor({
    maxFrameSamples: 4,
    maxMemorySamples: 4,
    startupStartedAtMs: 100,
  });

  for (const fps of samples) {
    monitor.recordFrameTime(1000 / fps);
  }

  return monitor;
}

describe('quality degradation policy', () => {
  it('requests effects-first degradation after a complete sustained window below 45 FPS', () => {
    const snapshot = monitorWithFpsSamples([40, 41, 42, 44]).snapshot();
    const decision = evaluateQualityPolicy('high', snapshot, POLICY);

    expect(decision.recommendation).toBe('degrade');
    expect(decision.nextLevel).toBe('balanced');
    expect(decision.degradationTarget).toBe('optionalEffects');
    expect(decision.characterFidelityProtected).toBe(true);
    expect(decision.primaryTargetMet).toBe(false);
    expect(decision.minimumInteractiveFloorMet).toBe(true);
  });

  it('does not call a partial rolling window sustained evidence', () => {
    const snapshot = monitorWithFpsSamples([40, 41, 42]).snapshot();
    const decision = evaluateQualityPolicy('high', snapshot, POLICY);

    expect(decision.recommendation).toBe('hold');
    expect(decision.evidenceStatus).toBe('insufficientSustainedWindow');
  });

  it('degrades secondary environment after effects before touching character fidelity', () => {
    const snapshot = monitorWithFpsSamples([38, 39, 40, 41]).snapshot();
    const decision = evaluateQualityPolicy('balanced', snapshot, POLICY);

    expect(decision.recommendation).toBe('degrade');
    expect(decision.nextLevel).toBe('minimumInteractive');
    expect(decision.degradationTarget).toBe('environment');
    expect(decision.characterFidelityProtected).toBe(true);
  });

  it('treats 30 FPS as an interactive floor rather than primary success', () => {
    const snapshot = monitorWithFpsSamples([30, 30, 30, 30]).snapshot();
    const decision = evaluateQualityPolicy('minimumInteractive', snapshot, POLICY);

    expect(decision.minimumInteractiveFloorMet).toBe(true);
    expect(decision.primaryTargetMet).toBe(false);
    expect(decision.recommendation).toBe('review');
    expect(decision.evidenceStatus).toBe('degradationLimitReached');
  });

  it('reports performance below 30 FPS as below the minimum interactive floor', () => {
    const snapshot = monitorWithFpsSamples([25, 26, 27, 28]).snapshot();
    const decision = evaluateQualityPolicy('minimumInteractive', snapshot, POLICY);

    expect(decision.minimumInteractiveFloorMet).toBe(false);
    expect(decision.recommendation).toBe('review');
    expect(decision.evidenceStatus).toBe('belowInteractiveFloor');
  });
});

describe('PerformanceMonitor', () => {
  it('keeps bounded frame samples and exposes median FPS and frame time', () => {
    const monitor = new PerformanceMonitor({
      maxFrameSamples: 3,
      maxMemorySamples: 2,
      startupStartedAtMs: 100,
    });

    monitor.recordFrameTime(10);
    monitor.recordFrameTime(20);
    monitor.recordFrameTime(25);
    monitor.recordFrameTime(50);

    const snapshot = monitor.snapshot();

    expect(snapshot.frameTimesMs).toEqual([20, 25, 50]);
    expect(snapshot.medianFrameTimeMs).toBe(25);
    expect(snapshot.medianFps).toBe(40);
  });

  it('measures startup-to-interactive without inventing a value before the mark exists', () => {
    const monitor = new PerformanceMonitor({
      maxFrameSamples: 3,
      maxMemorySamples: 2,
      startupStartedAtMs: 100,
    });

    expect(monitor.snapshot().startupToInteractiveMs).toBeNull();

    monitor.markInteractive(650);

    expect(monitor.snapshot().startupToInteractiveMs).toBe(550);
  });

  it('keeps unsupported memory evidence null instead of treating it as zero', () => {
    const monitor = new PerformanceMonitor({
      maxFrameSamples: 3,
      maxMemorySamples: 3,
      startupStartedAtMs: 100,
    });

    expect(monitor.snapshot().memoryGrowthRatio).toBeNull();

    monitor.recordMemoryBytes(100);
    monitor.recordMemoryBytes(110);
    monitor.recordMemoryBytes(120);

    expect(monitor.snapshot().memoryGrowthRatio).toBeCloseTo(0.2);
  });
});
