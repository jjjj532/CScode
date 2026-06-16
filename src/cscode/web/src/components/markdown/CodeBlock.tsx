import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  language: string;
  code: string;
}

export function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-v2-border-light">
      <div className="flex items-center justify-between bg-v2-code-header px-4 py-1.5 border-b border-v2-border-light">
        <span className="text-xs text-v2-text-muted font-mono">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="bg-v2-code-bg p-4 overflow-x-auto">
        <code className="text-sm font-mono leading-relaxed text-v2-text-primary">{code}</code>
      </pre>
    </div>
  );
}
