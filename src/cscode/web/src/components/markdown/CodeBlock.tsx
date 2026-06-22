import { useState, useEffect, useMemo } from 'react';
import { Copy, Check } from 'lucide-react';
import hljs from 'highlight.js';

interface CodeBlockProps {
  language: string;
  code: string;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const highlighted = useMemo(() => {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language }).value;
    }
    return escapeHtml(code);
  }, [language, code]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = code;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    setCopied(true);
  };

  useEffect(() => {
    if (copied) {
      const t = setTimeout(() => setCopied(false), 2000);
      return () => clearTimeout(t);
    }
  }, [copied]);

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-v2-border-light">
      <div className="flex items-center justify-between bg-v2-code-header px-4 py-1.5 border-b border-v2-border-light">
        <span className="text-xs text-v2-text-muted font-mono">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="bg-v2-code-bg p-4 overflow-x-auto">
        <code
          className="text-sm font-mono leading-relaxed hljs"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </pre>
    </div>
  );
}
