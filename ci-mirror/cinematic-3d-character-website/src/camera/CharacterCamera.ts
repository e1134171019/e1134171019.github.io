import { Vector3 } from 'three';

export type CharacterCameraMode = 'presentation' | 'follow' | 'orbit';

export interface CharacterCameraPose {
  readonly position: Vector3;
  readonly target: Vector3;
}

export interface CharacterCameraSnapshot extends CharacterCameraPose {
  readonly mode: CharacterCameraMode;
}

export interface CharacterCameraConfig {
  readonly followDistance: number;
  readonly followHeight: number;
  readonly presentationDistance: number;
  readonly presentationHeight: number;
  readonly upperBodyTargetHeight: number;
  readonly orbitHeight: number;
  readonly orbitMinRadius: number;
  readonly orbitMaxRadius: number;
  readonly damping: number;
  readonly maxInterpolationAlpha: number;
}

export interface CharacterOrbitInput {
  readonly azimuth: number;
  readonly radius: number;
}

export interface CharacterCameraGoalInput {
  readonly mode: CharacterCameraMode;
  readonly characterPosition: Vector3;
  readonly characterYaw: number;
  readonly orbit?: CharacterOrbitInput;
}

export interface CharacterCameraUpdateInput extends CharacterCameraGoalInput {
  readonly deltaTime: number;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function normalizedRange(first: number, second: number): readonly [number, number] {
  return first <= second ? [first, second] : [second, first];
}

function characterForward(yaw: number): Vector3 {
  return new Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
}

function upperBodyTarget(position: Vector3, height: number): Vector3 {
  return position.clone().add(new Vector3(0, height, 0));
}

export function resolveCharacterCameraGoal(
  input: CharacterCameraGoalInput,
  config: CharacterCameraConfig,
): CharacterCameraPose {
  const target = upperBodyTarget(input.characterPosition, config.upperBodyTargetHeight);
  const forward = characterForward(input.characterYaw);

  if (input.mode === 'follow') {
    const position = input.characterPosition
      .clone()
      .addScaledVector(forward, -config.followDistance);
    position.y += config.followHeight;

    return { position, target };
  }

  if (input.mode === 'orbit') {
    const [minimumRadius, maximumRadius] = normalizedRange(
      config.orbitMinRadius,
      config.orbitMaxRadius,
    );
    const requestedRadius = input.orbit?.radius ?? maximumRadius;
    const radius = clamp(requestedRadius, minimumRadius, maximumRadius);
    const azimuth = input.orbit?.azimuth ?? input.characterYaw;
    const position = input.characterPosition.clone().add(
      new Vector3(
        Math.sin(azimuth) * radius,
        config.orbitHeight,
        Math.cos(azimuth) * radius,
      ),
    );

    return { position, target };
  }

  const position = input.characterPosition
    .clone()
    .addScaledVector(forward, config.presentationDistance);
  position.y += config.presentationHeight;

  return { position, target };
}

function interpolationAlpha(
  deltaTime: number,
  damping: number,
  maxInterpolationAlpha: number,
): number {
  if (!Number.isFinite(deltaTime) || deltaTime <= 0) {
    return 0;
  }

  const safeDamping = Number.isFinite(damping) ? Math.max(0, damping) : 0;
  const alphaLimit = Number.isFinite(maxInterpolationAlpha)
    ? clamp(maxInterpolationAlpha, 0, 1)
    : 0;
  const damped = 1 - Math.exp(-safeDamping * deltaTime);

  return Math.min(damped, alphaLimit);
}

export class CharacterCamera {
  private readonly config: CharacterCameraConfig;
  private readonly position: Vector3;
  private readonly target: Vector3;

  public constructor(config: CharacterCameraConfig, initialPose: CharacterCameraPose) {
    this.config = config;
    this.position = initialPose.position.clone();
    this.target = initialPose.target.clone();
  }

  public update(input: CharacterCameraUpdateInput): CharacterCameraSnapshot {
    const goal = resolveCharacterCameraGoal(input, this.config);
    const alpha = interpolationAlpha(
      input.deltaTime,
      this.config.damping,
      this.config.maxInterpolationAlpha,
    );

    this.position.lerp(goal.position, alpha);
    this.target.lerp(goal.target, alpha);

    return {
      mode: input.mode,
      position: this.position.clone(),
      target: this.target.clone(),
    };
  }
}
