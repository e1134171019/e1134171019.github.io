import type { QualityLevel } from '../quality/QualityPolicy';
import type { RuntimeState } from '../state/RuntimeState';

export interface RuntimeOverlayInput {
  readonly state: RuntimeState;
  readonly loadingProgress: number | null | undefined;
  readonly interactionFocused: boolean;
  readonly qualityLevel: QualityLevel;
}

const KEYBOARD_HELP =
  '控制提示：WASD 或方向鍵移動／轉向，按 E 執行主要動作。';

function appendTextBlock(
  documentRef: Document,
  parent: HTMLElement,
  className: string,
  text: string,
): HTMLElement {
  const paragraph = documentRef.createElement('p');
  paragraph.className = className;
  paragraph.textContent = text;
  parent.append(paragraph);
  return paragraph;
}

function formatLoadingProgress(progress: number | null | undefined): string {
  if (progress === null || progress === undefined) {
    return '載入進度：進度計算中。';
  }

  if (!Number.isFinite(progress) || progress < 0 || progress > 1) {
    throw new RangeError('loadingProgress must be a finite number from 0 through 1');
  }

  return `載入進度：${Math.round(progress * 100)}%。`;
}

function qualityMessage(level: QualityLevel): string {
  switch (level) {
    case 'high':
      return '品質：高品質模式。';
    case 'balanced':
      return '品質已降級：已降低非核心視覺效果，角色本體品質維持優先。';
    case 'minimumInteractive':
      return '品質已降級：已降低次要環境細節，角色本體品質維持優先。';
  }
}

function appendRuntimeState(
  documentRef: Document,
  root: HTMLElement,
  input: RuntimeOverlayInput,
): void {
  const heading = documentRef.createElement('h2');
  heading.className = 'runtime-overlay__heading';
  root.append(heading);

  switch (input.state.mode) {
    case 'loading':
      heading.textContent = '角色場景載入中';
      appendTextBlock(
        documentRef,
        root,
        'runtime-overlay__message',
        formatLoadingProgress(input.loadingProgress),
      );
      appendTextBlock(
        documentRef,
        root,
        'runtime-overlay__help',
        KEYBOARD_HELP,
      );
      return;

    case 'presentation':
      heading.textContent = '角色展示已就緒';
      appendTextBlock(
        documentRef,
        root,
        'runtime-overlay__message',
        '目前為展示模式；開始即時控制後，角色會依鍵盤輸入回應。',
      );
      appendTextBlock(
        documentRef,
        root,
        'runtime-overlay__help',
        KEYBOARD_HELP,
      );
      return;

    case 'interactive':
      heading.textContent = '即時控制已啟用';
      appendTextBlock(
        documentRef,
        root,
        'runtime-overlay__focus',
        input.interactionFocused
          ? '鍵盤控制已取得焦點。'
          : '鍵盤控制目前未取得焦點；重新聚焦互動區域後再操作。',
      );
      appendTextBlock(
        documentRef,
        root,
        'runtime-overlay__help',
        KEYBOARD_HELP,
      );
      return;

    case 'fallback': {
      heading.textContent = '即時 3D 目前無法使用';
      const alert = documentRef.createElement('div');
      alert.className = 'runtime-overlay__error';
      alert.setAttribute('role', 'alert');
      alert.setAttribute('aria-live', 'assertive');
      alert.setAttribute('aria-atomic', 'true');

      appendTextBlock(
        documentRef,
        alert,
        'runtime-overlay__error-code',
        `錯誤代碼：${input.state.error.code}`,
      );
      appendTextBlock(
        documentRef,
        alert,
        'runtime-overlay__error-message',
        input.state.error.message,
      );
      root.append(alert);

      appendTextBlock(
        documentRef,
        root,
        'runtime-overlay__fallback-note',
        '目前顯示的是最低可用狀態介面，不等同於即時 3D 體驗。',
      );
      return;
    }
  }
}

export function renderRuntimeOverlay(
  documentRef: Document,
  input: RuntimeOverlayInput,
): HTMLElement {
  const root = documentRef.createElement('section');
  root.className = 'runtime-overlay';
  root.dataset.runtimeMode = input.state.mode;
  root.dataset.qualityLevel = input.qualityLevel;
  root.setAttribute('role', 'status');
  root.setAttribute('aria-live', 'polite');
  root.setAttribute('aria-atomic', 'true');
  root.setAttribute('aria-label', '互動角色執行狀態');

  appendRuntimeState(documentRef, root, input);

  if (input.state.mode !== 'fallback') {
    appendTextBlock(
      documentRef,
      root,
      'runtime-overlay__quality',
      qualityMessage(input.qualityLevel),
    );
  }

  return root;
}
