import { describe, expect, it } from 'vitest';
import { isInteractiveRuntimeMode } from '../app/RuntimeContracts';

describe('runtime contracts', () => {
  it('treats only interactive mode as interactive', () => {
    expect(isInteractiveRuntimeMode('interactive')).toBe(true);
    expect(isInteractiveRuntimeMode('loading')).toBe(false);
    expect(isInteractiveRuntimeMode('fallback')).toBe(false);
  });
});
