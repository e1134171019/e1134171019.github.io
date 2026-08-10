import type { PerformanceEvidenceSnapshot } from './PerformanceMonitor';

export type QualityLevel = 'high' | 'balanced' | 'minimumInteractive';
export type QualityRecommendation = 'hold' | 'degrade' | 'review';
export type DegradationTarget = 'optionalEffects' | 'environment';
export type QualityEvidenceStatus =
  | 'withinPolicy'
  | 'insufficientSustainedWindow'
  | 'degradationLimitReached'
  | 'belowInteractiveFloor';

export interface QualityPolicyConfig {
  readonly primaryTargetFps: number;
  readonly degradationTriggerFps: number;
  readonly minimumInteractiveFps: number;
  readonly requiredSustainedSamples: number;
}

export interface QualityPolicyDecision {
  readonly recommendation: QualityRecommendation;
  readonly nextLevel: QualityLevel;
  readonly degradationTarget: DegradationTarget | null;
  readonly characterFidelityProtected: true;
  readonly primaryTargetMet: boolean;
  readonly minimumInteractiveFloorMet: boolean | null;
  readonly evidenceStatus: QualityEvidenceStatus;
}

function requireFinitePositive(value: number, name: string): number {
  if (!Number.isFinite(value) || value <= 0) {
    throw new RangeError(`${name} must be finite and positive`);
  }

  return value;
}

function requirePositiveInteger(value: number, name: string): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new RangeError(`${name} must be a positive integer`);
  }

  return value;
}

function validateConfig(config: QualityPolicyConfig): QualityPolicyConfig {
  const primaryTargetFps = requireFinitePositive(
    config.primaryTargetFps,
    'primaryTargetFps',
  );
  const degradationTriggerFps = requireFinitePositive(
    config.degradationTriggerFps,
    'degradationTriggerFps',
  );
  const minimumInteractiveFps = requireFinitePositive(
    config.minimumInteractiveFps,
    'minimumInteractiveFps',
  );
  const requiredSustainedSamples = requirePositiveInteger(
    config.requiredSustainedSamples,
    'requiredSustainedSamples',
  );

  if (
    primaryTargetFps < degradationTriggerFps ||
    degradationTriggerFps < minimumInteractiveFps
  ) {
    throw new RangeError(
      'FPS thresholds must satisfy primary >= degradation >= minimum',
    );
  }

  return {
    primaryTargetFps,
    degradationTriggerFps,
    minimumInteractiveFps,
    requiredSustainedSamples,
  };
}

function baseDecision(
  currentLevel: QualityLevel,
  snapshot: PerformanceEvidenceSnapshot,
  config: QualityPolicyConfig,
): Pick<
  QualityPolicyDecision,
  'characterFidelityProtected' | 'primaryTargetMet' | 'minimumInteractiveFloorMet'
> & { readonly currentLevel: QualityLevel } {
  return {
    currentLevel,
    characterFidelityProtected: true,
    primaryTargetMet:
      snapshot.medianFps !== null && snapshot.medianFps >= config.primaryTargetFps,
    minimumInteractiveFloorMet:
      snapshot.medianFps === null
        ? null
        : snapshot.medianFps >= config.minimumInteractiveFps,
  };
}

export function evaluateQualityPolicy(
  currentLevel: QualityLevel,
  snapshot: PerformanceEvidenceSnapshot,
  rawConfig: QualityPolicyConfig,
): QualityPolicyDecision {
  const config = validateConfig(rawConfig);
  const base = baseDecision(currentLevel, snapshot, config);
  const recentFps = snapshot.fpsSamples.slice(-config.requiredSustainedSamples);

  if (recentFps.length < config.requiredSustainedSamples) {
    return {
      ...base,
      recommendation: 'hold',
      nextLevel: currentLevel,
      degradationTarget: null,
      evidenceStatus: 'insufficientSustainedWindow',
    };
  }

  const sustainedBelowTrigger = recentFps.every(
    (fps) => fps < config.degradationTriggerFps,
  );

  if (base.minimumInteractiveFloorMet === false) {
    return {
      ...base,
      recommendation: 'review',
      nextLevel: currentLevel,
      degradationTarget: null,
      evidenceStatus: 'belowInteractiveFloor',
    };
  }

  if (!sustainedBelowTrigger) {
    return {
      ...base,
      recommendation: 'hold',
      nextLevel: currentLevel,
      degradationTarget: null,
      evidenceStatus: 'withinPolicy',
    };
  }

  if (currentLevel === 'high') {
    return {
      ...base,
      recommendation: 'degrade',
      nextLevel: 'balanced',
      degradationTarget: 'optionalEffects',
      evidenceStatus: 'withinPolicy',
    };
  }

  if (currentLevel === 'balanced') {
    return {
      ...base,
      recommendation: 'degrade',
      nextLevel: 'minimumInteractive',
      degradationTarget: 'environment',
      evidenceStatus: 'withinPolicy',
    };
  }

  return {
    ...base,
    recommendation: 'review',
    nextLevel: 'minimumInteractive',
    degradationTarget: null,
    evidenceStatus: 'degradationLimitReached',
  };
}
