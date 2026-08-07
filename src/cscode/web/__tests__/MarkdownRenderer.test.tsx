import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MarkdownRenderer } from '../src/components/markdown/MarkdownRenderer';
import { autolinkFileNames } from '../src/lib/markdown';

// Fake Tauri runtime so openOutputFile takes the invoke path.
const mockInvoke = jest.fn().mockResolvedValue('');
jest.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

// react-markdown is ESM; MessageList.test mocks it. We render our
// markdownComponents.a via a controlled mock renderer. Crucially, we mimic
// react-markdown's defaultUrlTransform which encodeURI()s hrefs (中文路径 →
// percent-encoded), exactly as the real lib does — this is what makes the
// decodeFilePath fix observable in the test.
jest.mock('react-markdown', () => {
  const ReactMock = require('react');
  const { markdownComponents } = require('../src/lib/markdown');
  return {
    __esModule: true,
    default: ({ children, components }: any) => {
      const a = components?.a;
      if (a) {
        const text = String(children);
        const href = (text.match(/\((.*?)\)/) || [])[1] || text;
        const A = a as any;
        const encodedHref = encodeURI(href);
        return ReactMock.createElement(
          A,
          { href: encodedHref, children: text.replace(/^\[|\]$/g, '').replace(/\]\((.*?)\)$/, '') },
          null
        );
      }
      return ReactMock.createElement('div', null, children);
    },
  };
});

jest.mock('remark-gfm', () => () => {});

function setTauriRuntime(value: boolean) {
  Object.defineProperty(window, '__TAURI_INTERNALS__', {
    value: value ? {} : undefined,
    configurable: true,
  });
}

describe('MarkdownRenderer file paths', () => {
  beforeEach(() => {
    mockInvoke.mockClear();
    setTauriRuntime(false);
  });

  test('converts /tmp/cscode-outputs/ absolute path into a clickable link', () => {
    render(<MarkdownRenderer content="路径: /tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx" />);
    const link = screen.getByRole('link');
    expect(link).toBeTruthy();
    expect(link.getAttribute('href')).toContain('/tmp/cscode-outputs/');
  });

  test('converts /outputs/ relative path into a clickable link', () => {
    render(<MarkdownRenderer content="生成文件: /outputs/report.xlsx" />);
    const link = screen.getByRole('link');
    expect(link).toBeTruthy();
  });

  test('clicking a local file path in Tauri invokes open_output_file with full path', async () => {
    setTauriRuntime(true);
    render(<MarkdownRenderer content="/tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx" />);
    const link = screen.getByRole('link');
    fireEvent.click(link);
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith(
        'open_output_file',
        { filename: '/tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx' }
      );
    });
  });

  test('clicking a local path in plain browser does NOT navigate', () => {
    setTauriRuntime(false);
    render(<MarkdownRenderer content="/tmp/cscode-outputs/data.pdf" />);
    const link = screen.getByRole('link') as HTMLAnchorElement;
    fireEvent.click(link);
    expect(mockInvoke).not.toHaveBeenCalled();
    expect(link.getAttribute('href')).toContain('/tmp/cscode-outputs/data.pdf');
  });
});

describe('autolinkFileNames', () => {
  test('wraps bare artifact base name into a link when a path exists in the message', () => {
    const content = '文件名\t智转Pro_测试案例_v2.0.0.xlsx\n保存路径\t[/tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx](/tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx)';
    const out = autolinkFileNames(content);
    // bare name row → link to the same file
    expect(out).toContain('[智转Pro_测试案例_v2.0.0.xlsx](/tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx)');
    // already-linked path is NOT double-wrapped
    expect(out).toContain('[/tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx](/tmp/cscode-outputs/智转Pro_测试案例_v2.0.0.xlsx)');
  });

  test('bare absolute path becomes a markdown link', () => {
    const out = autolinkFileNames('路径: /tmp/cscode-outputs/报告.pdf');
    expect(out).toContain('[/tmp/cscode-outputs/报告.pdf](/tmp/cscode-outputs/报告.pdf)');
  });

  test('bare name without any path in the message stays plain text', () => {
    const out = autolinkFileNames('文件名\t孤立的文件.xlsx');
    expect(out).toContain('孤立的文件.xlsx');
    expect(out).not.toContain('[孤立的文件.xlsx]');
  });

  test('does not wrap a bare name when it is part of a longer token', () => {
    const out = autolinkFileNames('参考 abc报告.pdf 和 /tmp/cscode-outputs/报告.pdf');
    // 报告.pdf is embedded in abc报告.pdf → must not become its own link
    expect(out).toContain('abc报告.pdf');
    expect(out).toContain('[/tmp/cscode-outputs/报告.pdf](/tmp/cscode-outputs/报告.pdf)');
  });
});