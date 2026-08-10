import { describe, expect, it } from 'vitest';
import type { RuntimeState } from '../state/RuntimeState';
import { renderRuntimeOverlay } from './RuntimeOverlay';

function render(
  state: RuntimeState,
  options: {
    loadingProgress?: number | null;
    interactionFocused?: boolean;
    qualityLevel?: 'high' | 'balanced' | 'minimumInteractive';
  } = {},
): HTMLElement {
  return renderRuntimeOverlay(document, {
    state,
    loadingProgress: options.loadingProgress,
    interactionFocused: options.interactionFocused ?? false,
    qualityLevel: options.qualityLevel ?? 'high',
  });
}

describe('renderRuntimeOverlay', () => {
  it('announces loading with progress text and exposes keyboard help before control starts', () => {
    const overlay = render(
      { mode: 'loading' },
      { loadingProgress: 0.42 },
    );

    expect(overlay.getAttribute('role')).toBe('status');
    expect(overlay.getAttribute('aria-live')).toBe('polite');
    expect(overlay.textContent).toContain('載入');
    expect(overlay.textContent).toContain('42%');
    expect(overlay.textContent).toContain('WASD');
    expect(overlay.textContent).toContain('方向鍵');
    expect(overlay.textContent).toContain('E');
  });

  it('keeps unknown loading progress textual instead of fabricating zero percent', () => {
    const overlay = render({ mode: 'loading' });

    expect(overlay.textContent).toContain('進度計算中');
    expect(overlay.textContent).not.toContain('0%');
  });

  it('describes presentation readiness without claiming keyboard focus is active', () => {
    const overlay = render({ mode: 'presentation' });

    expect(overlay.textContent).toContain('展示已就緒');
    expect(overlay.textContent).toContain('WASD');
    expect(overlay.textContent).not.toContain('鍵盤控制已取得焦點');
  });

  it('exposes keyboard help and explicit focus status in interactive mode', () => {
    const focused = render(
      { mode: 'interactive' },
      { interactionFocused: true },
    );
    const unfocused = render(
      { mode: 'interactive' },
      { interactionFocused: false },
    );

    expect(focused.textContent).toContain('即時控制已啟用');
    expect(focused.textContent).toContain('WASD');
    expect(focused.textContent).toContain('鍵盤控制已取得焦點');
    expect(unfocused.textContent).toContain('鍵盤控制目前未取得焦點');
  });

  it('explains quality reduction in visible text instead of relying on color alone', () => {
    const balanced = render(
      { mode: 'interactive' },
      { interactionFocused: true, qualityLevel: 'balanced' },
    );
    const minimum = render(
      { mode: 'interactive' },
      { interactionFocused: true, qualityLevel: 'minimumInteractive' },
    );

    expect(balanced.textContent).toContain('品質已降級');
    expect(balanced.textContent).toContain('非核心視覺效果');
    expect(minimum.textContent).toContain('品質已降級');
    expect(minimum.textContent).toContain('次要環境細節');
  });

  it('surfaces typed fallback error and states that fallback is not equivalent to realtime 3D', () => {
    const overlay = render({
      mode: 'fallback',
      error: {
        code: 'unsupported_webgl2',
        message: 'WebGL2 unavailable in this runtime.',
      },
    });

    const alert = overlay.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert?.textContent).toContain('unsupported_webgl2');
    expect(alert?.textContent).toContain('WebGL2 unavailable in this runtime.');
    expect(overlay.textContent).toContain('不等同於即時 3D 體驗');
    expect(overlay.textContent).not.toContain('你的裝置太差');
  });

  it('rejects invalid loading progress instead of silently displaying misleading status', () => {
    expect(() =>
      render(
        { mode: 'loading' },
        { loadingProgress: 1.1 },
      ),
    ).toThrow(RangeError);
  });
});
