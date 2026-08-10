import { describe, expect, it } from 'vitest';
import { isInteractiveRuntimeMode } from '../app/RuntimeContracts';
import type { InputSnapshot } from '../input/InputActions';
import { reduceCharacterState } from './CharacterState';
import { reduceRuntimeState } from './RuntimeState';

function input(
  held: Partial<InputSnapshot['held']> = {},
  pressed: Partial<InputSnapshot['pressed']> = {},
): InputSnapshot {
  return {
    held: {
      moveForward: false,
      moveBackward: false,
      turnLeft: false,
      turnRight: false,
      ...held,
    },
    pressed: {
      primaryAction: false,
      ...pressed,
    },
  };
}

describe('runtime contracts', () => {
  it('treats only interactive mode as interactive', () => {
    expect(isInteractiveRuntimeMode('interactive')).toBe(true);
    expect(isInteractiveRuntimeMode('loading')).toBe(false);
    expect(isInteractiveRuntimeMode('fallback')).toBe(false);
  });
});

describe('CharacterState', () => {
  it('requires interaction enablement before named input can drive the character', () => {
    const forward = input({ moveForward: true });

    expect(reduceCharacterState('presentationIdle', { type: 'input', input: forward })).toBe(
      'presentationIdle',
    );
    expect(reduceCharacterState('presentationIdle', { type: 'interactionEnabled' })).toBe(
      'interactiveIdle',
    );
    expect(reduceCharacterState('interactiveIdle', { type: 'input', input: forward })).toBe('move');
  });

  it('gives primary action precedence over compatible locomotion for the decision tick', () => {
    const actionWhileMoving = input({ moveForward: true, turnRight: true }, { primaryAction: true });

    expect(reduceCharacterState('move', { type: 'input', input: actionWhileMoving })).toBe('action');
  });

  it('keeps action active until an explicit completion event', () => {
    expect(reduceCharacterState('action', { type: 'input', input: input() })).toBe('action');
    expect(
      reduceCharacterState('action', {
        type: 'actionCompleted',
        input: input(),
      }),
    ).toBe('returnToIdle');
  });

  it('resumes held locomotion immediately after action completion', () => {
    expect(
      reduceCharacterState('action', {
        type: 'actionCompleted',
        input: input({ moveForward: true, turnRight: true }),
      }),
    ).toBe('move');
  });

  it('classifies compatible movement plus turn as move while preserving a deterministic coarse state', () => {
    expect(
      reduceCharacterState('interactiveIdle', {
        type: 'input',
        input: input({ moveForward: true, turnRight: true }),
      }),
    ).toBe('move');
  });

  it('treats opposing held pairs as neutral defensively', () => {
    expect(
      reduceCharacterState('interactiveIdle', {
        type: 'input',
        input: input({ moveForward: true, moveBackward: true, turnLeft: true, turnRight: true }),
      }),
    ).toBe('interactiveIdle');
  });

  it('progresses explicit stop and return-to-idle states after locomotion input ends', () => {
    expect(reduceCharacterState('move', { type: 'input', input: input() })).toBe('stop');
    expect(reduceCharacterState('stop', { type: 'input', input: input() })).toBe('returnToIdle');
    expect(reduceCharacterState('returnToIdle', { type: 'input', input: input() })).toBe(
      'interactiveIdle',
    );
  });

  it('can return any desired state to presentation idle explicitly', () => {
    expect(reduceCharacterState('action', { type: 'presentationEnabled' })).toBe('presentationIdle');
  });
});

describe('RuntimeState', () => {
  it('moves from loading to presentation only when assets are ready', () => {
    expect(reduceRuntimeState({ mode: 'loading' }, { type: 'assetsReady' })).toEqual({
      mode: 'presentation',
    });
  });

  it('moves from presentation to interactive on explicit interaction start', () => {
    expect(reduceRuntimeState({ mode: 'presentation' }, { type: 'interactionStarted' })).toEqual({
      mode: 'interactive',
    });
  });

  it('enters explicit typed fallback from any normal state on runtime error', () => {
    expect(
      reduceRuntimeState(
        { mode: 'interactive' },
        {
          type: 'runtimeError',
          code: 'renderer_initialization_failed',
          message: 'WebGL renderer could not initialize.',
        },
      ),
    ).toEqual({
      mode: 'fallback',
      error: {
        code: 'renderer_initialization_failed',
        message: 'WebGL renderer could not initialize.',
      },
    });
  });

  it('keeps fallback fail-closed for normal lifecycle events', () => {
    const fallback = {
      mode: 'fallback' as const,
      error: {
        code: 'runtime_failure' as const,
        message: 'Runtime failed.',
      },
    };

    expect(reduceRuntimeState(fallback, { type: 'assetsReady' })).toEqual(fallback);
    expect(reduceRuntimeState(fallback, { type: 'interactionStarted' })).toEqual(fallback);
  });
});
