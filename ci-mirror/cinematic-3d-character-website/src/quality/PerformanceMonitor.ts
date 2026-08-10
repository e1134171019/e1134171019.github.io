export interface PerformanceMonitorConfig {
  readonly maxFrameSamples: number;
  readonly maxMemorySamples: number;
  readonly startupStartedAtMs: number;
}

export interface PerformanceEvidenceSnapshot {
  readonly frameTimesMs: readonly number[];
  readonly fpsSamples: readonly number[];
  readonly medianFrameTimeMs: number | null;
  readonly medianFps: number | null;
  readonly startupToInteractiveMs: number | null;
  readonly memoryGrowthRatio: number | null;
}

function requirePositiveInteger(value: number, name: string): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new RangeError(`${name} must be a positive integer`);
  }

  return value;
}

function requireFiniteNonNegative(value: number, name: string): number {
  if (!Number.isFinite(value) || value < 0) {
    throw new RangeError(`${name} must be finite and non-negative`);
  }

  return value;
}

function requireFinitePositive(value: number, name: string): number {
  if (!Number.isFinite(value) || value <= 0) {
    throw new RangeError(`${name} must be finite and positive`);
  }

  return value;
}

function pushBounded(samples: number[], value: number, maximum: number): void {
  samples.push(value);

  if (samples.length > maximum) {
    samples.splice(0, samples.length - maximum);
  }
}

function median(samples: readonly number[]): number | null {
  if (samples.length === 0) {
    return null;
  }

  const sorted = [...samples].sort((a, b) => a - b);
  const midpoint = Math.floor(sorted.length / 2);
  const upper = sorted[midpoint];

  if (upper === undefined) {
    return null;
  }

  if (sorted.length % 2 === 1) {
    return upper;
  }

  const lower = sorted[midpoint - 1];
  return lower === undefined ? upper : (lower + upper) / 2;
}

export class PerformanceMonitor {
  private readonly maxFrameSamples: number;
  private readonly maxMemorySamples: number;
  private readonly startupStartedAtMs: number;
  private readonly frameTimesMs: number[] = [];
  private readonly memoryBytes: number[] = [];
  private interactiveAtMs: number | null = null;

  public constructor(config: PerformanceMonitorConfig) {
    this.maxFrameSamples = requirePositiveInteger(
      config.maxFrameSamples,
      'maxFrameSamples',
    );
    this.maxMemorySamples = requirePositiveInteger(
      config.maxMemorySamples,
      'maxMemorySamples',
    );
    this.startupStartedAtMs = requireFiniteNonNegative(
      config.startupStartedAtMs,
      'startupStartedAtMs',
    );
  }

  public recordFrameTime(frameTimeMs: number): void {
    pushBounded(
      this.frameTimesMs,
      requireFinitePositive(frameTimeMs, 'frameTimeMs'),
      this.maxFrameSamples,
    );
  }

  public markInteractive(atMs: number): void {
    const interactiveAtMs = requireFiniteNonNegative(atMs, 'atMs');

    if (interactiveAtMs < this.startupStartedAtMs) {
      throw new RangeError('atMs must not precede startupStartedAtMs');
    }

    this.interactiveAtMs = interactiveAtMs;
  }

  public recordMemoryBytes(bytes: number): void {
    pushBounded(
      this.memoryBytes,
      requireFinitePositive(bytes, 'bytes'),
      this.maxMemorySamples,
    );
  }

  public snapshot(): PerformanceEvidenceSnapshot {
    const frameTimesMs = [...this.frameTimesMs];
    const fpsSamples = frameTimesMs.map((frameTimeMs) => 1000 / frameTimeMs);
    const firstMemorySample = this.memoryBytes[0];
    const lastMemorySample = this.memoryBytes.at(-1);
    const memoryGrowthRatio =
      this.memoryBytes.length >= 2 &&
      firstMemorySample !== undefined &&
      lastMemorySample !== undefined
        ? (lastMemorySample - firstMemorySample) / firstMemorySample
        : null;

    return {
      frameTimesMs,
      fpsSamples,
      medianFrameTimeMs: median(frameTimesMs),
      medianFps: median(fpsSamples),
      startupToInteractiveMs:
        this.interactiveAtMs === null
          ? null
          : this.interactiveAtMs - this.startupStartedAtMs,
      memoryGrowthRatio,
    };
  }
}
