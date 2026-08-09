import type { Object3D } from 'three';
import type { InputSnapshot } from '../input/InputActions';
import type { CharacterDesiredState } from '../state/CharacterState';

export interface CharacterPlanarPosition {
  readonly x: number;
  readonly z: number;
}

export interface CharacterMotionState {
  readonly position: CharacterPlanarPosition;
  readonly yaw: number;
}

export interface CharacterMotionSnapshot extends CharacterMotionState {
  readonly desiredState: CharacterDesiredState;
  readonly actionIntent: boolean;
  readonly appliedDeltaTime: number;
}

export interface CharacterMotionConfig {
  readonly moveSpeed: number;
  readonly turnSpeed: number;
  readonly maxDeltaTime: number;
}

export const DEFAULT_CHARACTER_MOTION_CONFIG: CharacterMotionConfig = Object.freeze({
  moveSpeed: 2.5,
  turnSpeed: Math.PI,
  maxDeltaTime: 0.1,
});

function clampDeltaTime(deltaTime: number, maxDeltaTime: number): number {
  if (!Number.isFinite(deltaTime) || deltaTime <= 0) {
    return 0;
  }

  return Math.min(deltaTime, Math.max(0, maxDeltaTime));
}

function movementAxis(input: InputSnapshot): number {
  if (input.held.moveForward === input.held.moveBackward) {
    return 0;
  }

  return input.held.moveForward ? 1 : -1;
}

function turnAxis(input: InputSnapshot): number {
  if (input.held.turnLeft === input.held.turnRight) {
    return 0;
  }

  return input.held.turnLeft ? 1 : -1;
}

function normalizeYaw(yaw: number): number {
  return Math.atan2(Math.sin(yaw), Math.cos(yaw));
}

export function stepCharacterMotion(
  state: CharacterMotionState,
  desiredState: CharacterDesiredState,
  input: InputSnapshot,
  deltaTime: number,
  config: CharacterMotionConfig = DEFAULT_CHARACTER_MOTION_CONFIG,
): CharacterMotionSnapshot {
  const appliedDeltaTime = clampDeltaTime(deltaTime, config.maxDeltaTime);
  const locomotionEnabled = desiredState === 'move' || desiredState === 'turn';
  const turn = locomotionEnabled ? turnAxis(input) : 0;
  const yaw = normalizeYaw(state.yaw + turn * config.turnSpeed * appliedDeltaTime);

  let x = state.position.x;
  let z = state.position.z;

  if (desiredState === 'move') {
    const movement = movementAxis(input);
    const displacement = movement * config.moveSpeed * appliedDeltaTime;

    x += -Math.sin(yaw) * displacement;
    z += -Math.cos(yaw) * displacement;
  }

  return {
    position: { x, z },
    yaw,
    desiredState,
    actionIntent: desiredState === 'action',
    appliedDeltaTime,
  };
}

export function applyCharacterMotion(root: Object3D, motion: CharacterMotionState): void {
  root.position.x = motion.position.x;
  root.position.z = motion.position.z;
  root.rotation.y = motion.yaw;
}
