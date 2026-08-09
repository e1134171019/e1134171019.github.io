import {
  getInputActionForCode,
  isContinuousInputAction,
  type ContinuousInputAction,
  type DiscreteInputAction,
  type HeldInputState,
  type InputSnapshot,
} from './InputActions';

function emptyHeldState(): Record<ContinuousInputAction, boolean> {
  return {
    moveForward: false,
    moveBackward: false,
    turnLeft: false,
    turnRight: false,
  };
}

export class KeyboardInput {
  private started = false;
  private readonly downCodes = new Set<string>();
  private readonly pressedEdges = new Set<DiscreteInputAction>();

  public constructor(
    private readonly target: Window,
    private readonly document: Document,
  ) {}

  public start(): void {
    if (this.started) {
      return;
    }

    this.started = true;
    this.target.addEventListener('keydown', this.handleKeyDown);
    this.target.addEventListener('keyup', this.handleKeyUp);
    this.target.addEventListener('blur', this.handleBlur);
    this.document.addEventListener('visibilitychange', this.handleVisibilityChange);
  }

  public stop(): void {
    if (this.started) {
      this.target.removeEventListener('keydown', this.handleKeyDown);
      this.target.removeEventListener('keyup', this.handleKeyUp);
      this.target.removeEventListener('blur', this.handleBlur);
      this.document.removeEventListener('visibilitychange', this.handleVisibilityChange);
      this.started = false;
    }

    this.clearState();
  }

  public snapshot(): InputSnapshot {
    const rawHeld = emptyHeldState();

    for (const code of this.downCodes) {
      const action = getInputActionForCode(code);
      if (action && isContinuousInputAction(action)) {
        rawHeld[action] = true;
      }
    }

    const movementConflict = rawHeld.moveForward && rawHeld.moveBackward;
    const turnConflict = rawHeld.turnLeft && rawHeld.turnRight;

    const held: HeldInputState = {
      moveForward: movementConflict ? false : rawHeld.moveForward,
      moveBackward: movementConflict ? false : rawHeld.moveBackward,
      turnLeft: turnConflict ? false : rawHeld.turnLeft,
      turnRight: turnConflict ? false : rawHeld.turnRight,
    };

    const pressed = {
      primaryAction: this.pressedEdges.has('primaryAction'),
    } as const;

    this.pressedEdges.clear();

    return { held, pressed };
  }

  private readonly handleKeyDown = (event: KeyboardEvent): void => {
    if (this.isEditableTarget(event.target)) {
      return;
    }

    const action = getInputActionForCode(event.code);
    if (!action) {
      return;
    }

    event.preventDefault();

    const wasAlreadyDown = this.downCodes.has(event.code);
    this.downCodes.add(event.code);

    if (!isContinuousInputAction(action) && !event.repeat && !wasAlreadyDown) {
      this.pressedEdges.add(action);
    }
  };

  private readonly handleKeyUp = (event: KeyboardEvent): void => {
    const action = getInputActionForCode(event.code);
    if (!action) {
      return;
    }

    if (!this.isEditableTarget(event.target)) {
      event.preventDefault();
    }

    this.downCodes.delete(event.code);
  };

  private readonly handleBlur = (): void => {
    this.clearState();
  };

  private readonly handleVisibilityChange = (): void => {
    if (this.document.visibilityState === 'hidden') {
      this.clearState();
    }
  };

  private clearState(): void {
    this.downCodes.clear();
    this.pressedEdges.clear();
  }

  private isEditableTarget(target: EventTarget | null): boolean {
    if (!target || typeof target !== 'object' || !('nodeType' in target)) {
      return false;
    }

    const element = target as HTMLElement;
    const tagName = typeof element.tagName === 'string' ? element.tagName.toLowerCase() : '';

    return (
      tagName === 'input' ||
      tagName === 'textarea' ||
      tagName === 'select' ||
      element.isContentEditable === true
    );
  }
}
