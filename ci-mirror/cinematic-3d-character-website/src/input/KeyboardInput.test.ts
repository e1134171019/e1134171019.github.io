import { afterEach, describe, expect, it } from 'vitest';
import { KeyboardInput } from './KeyboardInput';

const activeInputs: KeyboardInput[] = [];

function startInput(): KeyboardInput {
  const input = new KeyboardInput(window, document);
  activeInputs.push(input);
  input.start();
  return input;
}

function key(type: 'keydown' | 'keyup', code: string, options: { repeat?: boolean } = {}): void {
  window.dispatchEvent(new KeyboardEvent(type, { code, repeat: options.repeat ?? false }));
}

afterEach(() => {
  activeInputs.splice(0).forEach((input) => input.stop());
});

describe('KeyboardInput', () => {
  it('maps physical movement bindings to named held actions', () => {
    const input = startInput();

    key('keydown', 'KeyW');
    expect(input.snapshot().held.moveForward).toBe(true);

    key('keyup', 'KeyW');
    expect(input.snapshot().held.moveForward).toBe(false);

    key('keydown', 'ArrowUp');
    expect(input.snapshot().held.moveForward).toBe(true);
  });

  it('emits primaryAction as a single press edge instead of held input', () => {
    const input = startInput();

    key('keydown', 'KeyE');
    expect(input.snapshot().pressed.primaryAction).toBe(true);
    expect(input.snapshot().pressed.primaryAction).toBe(false);

    key('keydown', 'KeyE', { repeat: true });
    expect(input.snapshot().pressed.primaryAction).toBe(false);

    key('keyup', 'KeyE');
    key('keydown', 'KeyE');
    expect(input.snapshot().pressed.primaryAction).toBe(true);
  });

  it('clears held and pending edge state when the window loses focus', () => {
    const input = startInput();

    key('keydown', 'KeyW');
    key('keydown', 'KeyE');
    window.dispatchEvent(new Event('blur'));

    const snapshot = input.snapshot();
    expect(snapshot.held.moveForward).toBe(false);
    expect(snapshot.pressed.primaryAction).toBe(false);
  });

  it('clears state when document visibility becomes hidden', () => {
    const input = startInput();
    const originalVisibilityState = Object.getOwnPropertyDescriptor(document, 'visibilityState');

    try {
      key('keydown', 'KeyD');
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        value: 'hidden',
      });
      document.dispatchEvent(new Event('visibilitychange'));

      expect(input.snapshot().held.turnRight).toBe(false);
    } finally {
      if (originalVisibilityState) {
        Object.defineProperty(document, 'visibilityState', originalVisibilityState);
      } else {
        delete (document as Document & { visibilityState?: string }).visibilityState;
      }
    }
  });

  it('neutralizes opposing continuous actions but preserves compatible simultaneous actions', () => {
    const input = startInput();

    key('keydown', 'KeyW');
    key('keydown', 'KeyS');
    let snapshot = input.snapshot();
    expect(snapshot.held.moveForward).toBe(false);
    expect(snapshot.held.moveBackward).toBe(false);

    key('keyup', 'KeyS');
    key('keydown', 'KeyD');
    snapshot = input.snapshot();
    expect(snapshot.held.moveForward).toBe(true);
    expect(snapshot.held.turnRight).toBe(true);
  });

  it('ignores mapped keys from editable targets', () => {
    const input = startInput();
    const textInput = document.createElement('input');
    document.body.append(textInput);

    try {
      textInput.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyW', bubbles: true }));
      expect(input.snapshot().held.moveForward).toBe(false);
    } finally {
      textInput.remove();
    }
  });

  it('stop removes listeners and clears current input state', () => {
    const input = startInput();

    key('keydown', 'KeyW');
    input.stop();
    expect(input.snapshot().held.moveForward).toBe(false);

    key('keydown', 'KeyW');
    expect(input.snapshot().held.moveForward).toBe(false);
  });
});
