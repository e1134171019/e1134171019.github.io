import {
  AnimationClip,
  AnimationMixer,
  LoopOnce,
  LoopRepeat,
  type AnimationAction,
  type Object3D,
} from 'three';
import type { CharacterDesiredState } from '../state/CharacterState';

export type CharacterAnimationState = 'idle' | 'walk' | 'turn' | 'action' | 'none';
export type AnimationTransitionKind = 'started' | 'crossfade' | 'unchanged' | 'none';

export interface SemanticAnimationSelection {
  readonly clip: AnimationClip | null;
  readonly actualAnimationState: CharacterAnimationState;
  readonly usedFallback: boolean;
}

export interface AnimationTransitionResult {
  readonly desiredState: CharacterDesiredState;
  readonly actualAnimationState: CharacterAnimationState;
  readonly selectedClipName: string | null;
  readonly usedFallback: boolean;
  readonly transition: AnimationTransitionKind;
}

export interface AnimationCoordinatorOptions {
  readonly mixer?: AnimationMixer;
  readonly crossFadeDuration?: number;
}

const DEFAULT_CROSS_FADE_DURATION = 0.2;

const SEMANTIC_CANDIDATES: Readonly<Record<Exclude<CharacterAnimationState, 'none'>, readonly string[]>> =
  Object.freeze({
    idle: Object.freeze(['idle', 'stand', 'standing', 'breath', 'breathing']),
    walk: Object.freeze(['walk', 'walking', 'locomotion', 'move', 'run', 'running']),
    turn: Object.freeze(['turn', 'turning', 'rotate', 'rotation', 'pivot']),
    action: Object.freeze(['action', 'gesture', 'interact', 'interaction', 'wave']),
  });

function semanticForDesiredState(desiredState: CharacterDesiredState): Exclude<CharacterAnimationState, 'none'> {
  switch (desiredState) {
    case 'move':
      return 'walk';
    case 'turn':
      return 'turn';
    case 'action':
      return 'action';
    case 'presentationIdle':
    case 'interactiveIdle':
    case 'stop':
    case 'returnToIdle':
      return 'idle';
  }
}

function normalizedClipName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function findSemanticClip(
  clips: readonly AnimationClip[],
  semantic: Exclude<CharacterAnimationState, 'none'>,
): AnimationClip | null {
  const candidates = SEMANTIC_CANDIDATES[semantic];
  const normalized = clips.map((clip) => ({
    clip,
    name: normalizedClipName(clip.name),
  }));

  for (const candidate of candidates) {
    const exact = normalized.find(({ name }) => name === candidate);
    if (exact) {
      return exact.clip;
    }
  }

  for (const candidate of candidates) {
    const tokenMatch = normalized.find(({ name }) => name.split(' ').includes(candidate));
    if (tokenMatch) {
      return tokenMatch.clip;
    }
  }

  return null;
}

export function selectSemanticAnimationClip(
  clips: readonly AnimationClip[],
  desiredState: CharacterDesiredState,
): SemanticAnimationSelection {
  const desiredAnimationState = semanticForDesiredState(desiredState);
  const desiredClip = findSemanticClip(clips, desiredAnimationState);

  if (desiredClip) {
    return {
      clip: desiredClip,
      actualAnimationState: desiredAnimationState,
      usedFallback: false,
    };
  }

  if (desiredAnimationState !== 'idle') {
    const idleClip = findSemanticClip(clips, 'idle');
    if (idleClip) {
      return {
        clip: idleClip,
        actualAnimationState: 'idle',
        usedFallback: true,
      };
    }
  }

  return {
    clip: null,
    actualAnimationState: 'none',
    usedFallback: true,
  };
}

function configureAction(action: AnimationAction, state: CharacterAnimationState): void {
  if (state === 'action') {
    action.setLoop(LoopOnce, 1);
    action.clampWhenFinished = true;
    return;
  }

  action.setLoop(LoopRepeat, Number.POSITIVE_INFINITY);
  action.clampWhenFinished = false;
}

export class AnimationCoordinator {
  private readonly mixer: AnimationMixer;
  private readonly clips: readonly AnimationClip[];
  private readonly crossFadeDuration: number;
  private currentAction: AnimationAction | null = null;
  private currentClip: AnimationClip | null = null;
  private currentState: CharacterAnimationState = 'none';

  constructor(root: Object3D, clips: readonly AnimationClip[], options: AnimationCoordinatorOptions = {}) {
    this.mixer = options.mixer ?? new AnimationMixer(root);
    this.clips = [...clips];
    this.crossFadeDuration = Math.max(0, options.crossFadeDuration ?? DEFAULT_CROSS_FADE_DURATION);
  }

  get actualAnimationState(): CharacterAnimationState {
    return this.currentState;
  }

  transitionTo(desiredState: CharacterDesiredState): AnimationTransitionResult {
    const selection = selectSemanticAnimationClip(this.clips, desiredState);

    if (!selection.clip) {
      return {
        desiredState,
        actualAnimationState: 'none',
        selectedClipName: null,
        usedFallback: selection.usedFallback,
        transition: 'none',
      };
    }

    if (this.currentClip === selection.clip) {
      this.currentState = selection.actualAnimationState;
      return {
        desiredState,
        actualAnimationState: selection.actualAnimationState,
        selectedClipName: selection.clip.name,
        usedFallback: selection.usedFallback,
        transition: 'unchanged',
      };
    }

    const nextAction = this.mixer.clipAction(selection.clip);
    configureAction(nextAction, selection.actualAnimationState);
    nextAction.reset().play();

    const transition: AnimationTransitionKind = this.currentAction ? 'crossfade' : 'started';
    if (this.currentAction) {
      this.currentAction.crossFadeTo(nextAction, this.crossFadeDuration, false);
    }

    this.currentAction = nextAction;
    this.currentClip = selection.clip;
    this.currentState = selection.actualAnimationState;

    return {
      desiredState,
      actualAnimationState: selection.actualAnimationState,
      selectedClipName: selection.clip.name,
      usedFallback: selection.usedFallback,
      transition,
    };
  }

  update(deltaTime: number): void {
    if (!Number.isFinite(deltaTime) || deltaTime <= 0) {
      return;
    }

    this.mixer.update(deltaTime);
  }
}
