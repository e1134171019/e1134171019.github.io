import type { InputSnapshot } from '../input/InputActions';

export type CharacterDesiredState =
  | 'presentationIdle'
  | 'interactiveIdle'
  | 'move'
  | 'turn'
  | 'stop'
  | 'action'
  | 'returnToIdle';

export type CharacterStateEvent =
  | { readonly type: 'interactionEnabled' }
  | { readonly type: 'presentationEnabled' }
  | { readonly type: 'input'; readonly input: InputSnapshot }
  | { readonly type: 'actionCompleted'; readonly input: InputSnapshot };

function hasMovementIntent(input: InputSnapshot): boolean {
  return input.held.moveForward !== input.held.moveBackward;
}

function hasTurnIntent(input: InputSnapshot): boolean {
  return input.held.turnLeft !== input.held.turnRight;
}

function desiredStateFromInput(input: InputSnapshot, allowAction: boolean): CharacterDesiredState | null {
  if (allowAction && input.pressed.primaryAction) {
    return 'action';
  }

  if (hasMovementIntent(input)) {
    return 'move';
  }

  if (hasTurnIntent(input)) {
    return 'turn';
  }

  return null;
}

function idleProgression(state: CharacterDesiredState): CharacterDesiredState {
  switch (state) {
    case 'move':
    case 'turn':
      return 'stop';
    case 'stop':
      return 'returnToIdle';
    case 'returnToIdle':
      return 'interactiveIdle';
    default:
      return state;
  }
}

export function reduceCharacterState(
  state: CharacterDesiredState,
  event: CharacterStateEvent,
): CharacterDesiredState {
  if (event.type === 'presentationEnabled') {
    return 'presentationIdle';
  }

  if (event.type === 'interactionEnabled') {
    return state === 'presentationIdle' ? 'interactiveIdle' : state;
  }

  if (event.type === 'actionCompleted') {
    if (state !== 'action') {
      return state;
    }

    return desiredStateFromInput(event.input, false) ?? 'returnToIdle';
  }

  if (state === 'presentationIdle' || state === 'action') {
    return state;
  }

  return desiredStateFromInput(event.input, true) ?? idleProgression(state);
}
