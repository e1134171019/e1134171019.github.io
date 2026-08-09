import { describe, expect, it } from 'vitest';
import { assertWebGL2Available } from './Renderer';

describe('renderer capability', () => {
  it('rejects an unavailable WebGL2 context explicitly', () => {
    expect(() => assertWebGL2Available(() => null)).toThrowError('unsupported_webgl2');
  });
});
