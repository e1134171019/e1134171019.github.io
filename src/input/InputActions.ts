export const CONTINUOUS_INPUT_ACTIONS = [
  'moveForward',
  'moveBackward',
  'turnLeft',
  'turnRight',
] as const;

export const DISCRETE_INPUT_ACTIONS = ['primaryAction'] as const;

export type ContinuousInputAction = (typeof CONTINUOUS_INPUT_ACTIONS)[number];
export type DiscreteInputAction = (typeof DISCRETE_INPUT_ACTIONS)[number];
export type InputAction = ContinuousInputAction | DiscreteInputAction;

export type HeldInputState = Readonly<Record<ContinuousInputAction, boolean>>;
export type PressedInputState = Readonly<Record<DiscreteInputAction, boolean>>;

export interface InputSnapshot {
  readonly held: HeldInputState;
  readonly pressed: PressedInputState;
}

export const DEFAULT_KEY_BINDINGS = {
  KeyW: 'moveForward',
  ArrowUp: 'moveForward',
  KeyS: 'moveBackward',
  ArrowDown: 'moveBackward',
  KeyA: 'turnLeft',
  ArrowLeft: 'turnLeft',
  KeyD: 'turnRight',
  ArrowRight: 'turnRight',
  KeyE: 'primaryAction',
} as const satisfies Readonly<Record<string, InputAction>>;

const CONTINUOUS_ACTION_SET = new Set<InputAction>(CONTINUOUS_INPUT_ACTIONS);

export function getInputActionForCode(code: string): InputAction | undefined {
  return DEFAULT_KEY_BINDINGS[code as keyof typeof DEFAULT_KEY_BINDINGS];
}

export function isContinuousInputAction(action: InputAction): action is ContinuousInputAction {
  return CONTINUOUS_ACTION_SET.has(action);
}
