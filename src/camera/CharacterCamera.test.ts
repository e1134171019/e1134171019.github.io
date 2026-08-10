import { describe, expect, it } from 'vitest';
import { Vector3 } from 'three';
import {
  CharacterCamera,
  resolveCharacterCameraGoal,
  type CharacterCameraConfig,
  type CharacterCameraPose,
} from './CharacterCamera';

const CONFIG: CharacterCameraConfig = {
  followDistance: 5,
  followHeight: 2.5,
  presentationDistance: 4,
  presentationHeight: 2.1,
  upperBodyTargetHeight: 1.55,
  orbitHeight: 1.9,
  orbitMinRadius: 2,
  orbitMaxRadius: 6,
  damping: 8,
  maxInterpolationAlpha: 0.35,
};

const INITIAL_POSE: CharacterCameraPose = {
  position: new Vector3(0, 2, 8),
  target: new Vector3(0, 1.5, 0),
};

describe('resolveCharacterCameraGoal', () => {
  it('places follow mode behind the character in local facing space', () => {
    const yaw = Math.PI / 2;
    const characterPosition = new Vector3(3, 0, -2);
    const goal = resolveCharacterCameraGoal(
      {
        mode: 'follow',
        characterPosition,
        characterYaw: yaw,
      },
      CONFIG,
    );

    const forward = new Vector3(-Math.sin(yaw), 0, -Math.cos(yaw));
    const characterToCamera = goal.position.clone().sub(characterPosition);

    expect(characterToCamera.dot(forward)).toBeLessThan(0);
    expect(goal.target.y).toBeCloseTo(CONFIG.upperBodyTargetHeight);
  });

  it('clamps orbit radius to configured minimum and maximum', () => {
    const characterPosition = new Vector3(0, 0, 0);

    const tooClose = resolveCharacterCameraGoal(
      {
        mode: 'orbit',
        characterPosition,
        characterYaw: 0,
        orbit: { azimuth: 0, radius: -100 },
      },
      CONFIG,
    );
    const tooFar = resolveCharacterCameraGoal(
      {
        mode: 'orbit',
        characterPosition,
        characterYaw: 0,
        orbit: { azimuth: 0, radius: 100 },
      },
      CONFIG,
    );

    const horizontalRadius = (pose: CharacterCameraPose) =>
      Math.hypot(
        pose.position.x - characterPosition.x,
        pose.position.z - characterPosition.z,
      );

    expect(horizontalRadius(tooClose)).toBeCloseTo(CONFIG.orbitMinRadius);
    expect(horizontalRadius(tooFar)).toBeCloseTo(CONFIG.orbitMaxRadius);
  });

  it('targets the character upper body in presentation mode instead of world origin', () => {
    const characterPosition = new Vector3(7, 0.4, -11);
    const goal = resolveCharacterCameraGoal(
      {
        mode: 'presentation',
        characterPosition,
        characterYaw: 0,
      },
      CONFIG,
    );

    expect(goal.target.x).toBeCloseTo(characterPosition.x);
    expect(goal.target.z).toBeCloseTo(characterPosition.z);
    expect(goal.target.y).toBeCloseTo(characterPosition.y + CONFIG.upperBodyTargetHeight);
    expect(goal.target.equals(new Vector3(0, 0, 0))).toBe(false);
  });
});

describe('CharacterCamera', () => {
  it('damps camera movement so one update cannot snap directly to a distant goal', () => {
    const controller = new CharacterCamera(CONFIG, INITIAL_POSE);
    const characterPosition = new Vector3(50, 0, -50);
    const goal = resolveCharacterCameraGoal(
      {
        mode: 'follow',
        characterPosition,
        characterYaw: 0,
      },
      CONFIG,
    );

    const before = INITIAL_POSE.position.distanceTo(goal.position);
    const pose = controller.update({
      mode: 'follow',
      characterPosition,
      characterYaw: 0,
      deltaTime: 10,
    });
    const moved = INITIAL_POSE.position.distanceTo(pose.position);
    const remaining = pose.position.distanceTo(goal.position);

    expect(moved).toBeGreaterThan(0);
    expect(moved).toBeLessThan(before);
    expect(remaining).toBeGreaterThan(0);
  });

  it('uses one controller instance to switch between presentation, follow, and orbit goals', () => {
    const controller = new CharacterCamera(CONFIG, INITIAL_POSE);
    const characterPosition = new Vector3(1, 0, 2);

    const presentation = controller.update({
      mode: 'presentation',
      characterPosition,
      characterYaw: 0,
      deltaTime: 0.016,
    });
    const follow = controller.update({
      mode: 'follow',
      characterPosition,
      characterYaw: 0,
      deltaTime: 0.016,
    });
    const orbit = controller.update({
      mode: 'orbit',
      characterPosition,
      characterYaw: 0,
      deltaTime: 0.016,
      orbit: { azimuth: Math.PI / 3, radius: 3 },
    });

    expect(presentation.mode).toBe('presentation');
    expect(follow.mode).toBe('follow');
    expect(orbit.mode).toBe('orbit');
  });
});
