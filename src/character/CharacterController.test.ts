import { describe, expect, it } from 'vitest';
import { Object3D } from 'three';
import type { InputSnapshot } from '../input/InputActions';
import {
  applyCharacterMotion,
  DEFAULT_CHARACTER_MOTION_CONFIG,
  stepCharacterMotion,
  type CharacterMotionState,
} from './CharacterController';

const EMPTY_INPUT: InputSnapshot = {
  held: {
    moveForward: false,
    moveBackward: false,
    turnLeft: false,
    turnRight: false,
  },
  pressed: {
    primaryAction: false,
  },
};

function input(
  held: Partial<InputSnapshot['held']> = {},
  pressed: Partial<InputSnapshot['pressed']> = {},
): InputSnapshot {
  return {
    held: {
      ...EMPTY_INPUT.held,
      ...held,
    },
    pressed: {
      ...EMPTY_INPUT.pressed,
      ...pressed,
    },
  };
}

const ORIGIN: CharacterMotionState = {
  position: { x: 0, z: 0 },
  yaw: 0,
};

describe('stepCharacterMotion', () => {
  it('moves forward in local character space when yaw is zero', () => {
    const motion = stepCharacterMotion(
      ORIGIN,
      'move',
      input({ moveForward: true }),
      0.1,
    );

    expect(motion.position.x).toBeCloseTo(0);
    expect(motion.position.z).toBeLessThan(0);
    expect(motion.actionIntent).toBe(false);
  });

  it('turns left and right with deterministic yaw direction', () => {
    const left = stepCharacterMotion(ORIGIN, 'turn', input({ turnLeft: true }), 0.1);
    const right = stepCharacterMotion(ORIGIN, 'turn', input({ turnRight: true }), 0.1);

    expect(left.yaw).toBeGreaterThan(0);
    expect(right.yaw).toBeLessThan(0);
    expect(Math.abs(left.yaw)).toBeCloseTo(Math.abs(right.yaw));
  });

  it('does not mutate transform in idle or action states and keeps action intent state-owned', () => {
    const idle = stepCharacterMotion(
      ORIGIN,
      'interactiveIdle',
      input({ moveForward: true, turnLeft: true }),
      0.1,
    );
    const action = stepCharacterMotion(
      ORIGIN,
      'action',
      input({ moveForward: true, turnLeft: true }),
      0.1,
    );

    expect(idle.position).toEqual(ORIGIN.position);
    expect(idle.yaw).toBe(ORIGIN.yaw);
    expect(idle.actionIntent).toBe(false);

    expect(action.position).toEqual(ORIGIN.position);
    expect(action.yaw).toBe(ORIGIN.yaw);
    expect(action.actionIntent).toBe(true);
  });

  it('clamps delta time so a long background-tab frame cannot teleport the character', () => {
    const forward = input({ moveForward: true });
    const clamped = stepCharacterMotion(
      ORIGIN,
      'move',
      forward,
      DEFAULT_CHARACTER_MOTION_CONFIG.maxDeltaTime,
    );
    const hugeFrame = stepCharacterMotion(ORIGIN, 'move', forward, 10);

    expect(hugeFrame.position.x).toBeCloseTo(clamped.position.x);
    expect(hugeFrame.position.z).toBeCloseTo(clamped.position.z);
    expect(hugeFrame.appliedDeltaTime).toBe(DEFAULT_CHARACTER_MOTION_CONFIG.maxDeltaTime);
  });

  it('can turn while moving because desired state remains coarse and named input preserves both intents', () => {
    const motion = stepCharacterMotion(
      ORIGIN,
      'move',
      input({ moveForward: true, turnLeft: true }),
      0.1,
    );

    expect(motion.yaw).toBeGreaterThan(0);
    expect(motion.position.x).toBeLessThan(0);
    expect(motion.position.z).toBeLessThan(0);
  });
});

describe('applyCharacterMotion', () => {
  it('applies only controlled x/z position and yaw to a Three.js Object3D root', () => {
    const root = new Object3D();
    root.position.set(5, 2.5, 6);
    root.rotation.set(0.25, 0.5, -0.1);

    const motion = stepCharacterMotion(
      { position: { x: 1, z: 2 }, yaw: 0 },
      'move',
      input({ moveForward: true }),
      0.1,
    );

    applyCharacterMotion(root, motion);

    expect(root.position.x).toBeCloseTo(motion.position.x);
    expect(root.position.z).toBeCloseTo(motion.position.z);
    expect(root.position.y).toBeCloseTo(2.5);
    expect(root.rotation.y).toBeCloseTo(motion.yaw);
    expect(root.rotation.x).toBeCloseTo(0.25);
    expect(root.rotation.z).toBeCloseTo(-0.1);
  });
});
