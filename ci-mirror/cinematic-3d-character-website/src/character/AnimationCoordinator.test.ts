import { AnimationClip, AnimationMixer, Object3D } from 'three';
import { describe, expect, it, vi } from 'vitest';
import {
  AnimationCoordinator,
  selectSemanticAnimationClip,
} from './AnimationCoordinator';

function clip(name: string): AnimationClip {
  return new AnimationClip(name, 1, []);
}

describe('selectSemanticAnimationClip', () => {
  it('prefers the first exact normalized semantic candidate instead of a vendor-specific single name', () => {
    const clips = [clip('Run'), clip('Walk_Cycle'), clip('Walk'), clip('Idle')];

    const selection = selectSemanticAnimationClip(clips, 'move');

    expect(selection.clip?.name).toBe('Walk');
    expect(selection.actualAnimationState).toBe('walk');
    expect(selection.usedFallback).toBe(false);
  });

  it('keeps desired and actual state separate when move has to fall back to idle', () => {
    const selection = selectSemanticAnimationClip([clip('Idle')], 'move');

    expect(selection.clip?.name).toBe('Idle');
    expect(selection.actualAnimationState).toBe('idle');
    expect(selection.usedFallback).toBe(true);
  });

  it('falls back to idle when an action clip is absent', () => {
    const selection = selectSemanticAnimationClip([clip('Idle'), clip('Walk')], 'action');

    expect(selection.clip?.name).toBe('Idle');
    expect(selection.actualAnimationState).toBe('idle');
    expect(selection.usedFallback).toBe(true);
  });
});

describe('AnimationCoordinator', () => {
  it('requests a crossfade when the selected source and target clips differ', () => {
    const root = new Object3D();
    const idle = clip('Idle');
    const walk = clip('Walk');
    const mixer = new AnimationMixer(root);
    const idleAction = mixer.clipAction(idle);
    const crossFadeTo = vi.spyOn(idleAction, 'crossFadeTo');
    const coordinator = new AnimationCoordinator(root, [idle, walk], {
      mixer,
      crossFadeDuration: 0.2,
    });

    expect(coordinator.transitionTo('interactiveIdle').transition).toBe('started');
    const result = coordinator.transitionTo('move');

    expect(result.desiredState).toBe('move');
    expect(result.actualAnimationState).toBe('walk');
    expect(result.selectedClipName).toBe('Walk');
    expect(result.transition).toBe('crossfade');
    expect(crossFadeTo).toHaveBeenCalledTimes(1);
    expect(crossFadeTo).toHaveBeenCalledWith(mixer.clipAction(walk), 0.2, false);
  });

  it('does not crash when the runtime asset has zero animation clips', () => {
    const coordinator = new AnimationCoordinator(new Object3D(), []);

    expect(() => coordinator.transitionTo('action')).not.toThrow();
    expect(coordinator.transitionTo('action')).toEqual({
      desiredState: 'action',
      actualAnimationState: 'none',
      selectedClipName: null,
      usedFallback: true,
      transition: 'none',
    });
  });
});
