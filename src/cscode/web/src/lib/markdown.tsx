import type { Components } from 'react-markdown';
import { CodeBlock } from '../components/markdown/CodeBlock';

const DOWNLOAD_EXTS = ['.xlsx', '.xls', '.pdf', '.doc', '.docx', '.csv', '.txt', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.tar', '.gz', '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.toml', '.md', '.log'];

function isDownloadLink(href: string | undefined): boolean {
  if (!href) return false;
  const path = href.split('?')[0].split('#')[0].toLowerCase();
  return DOWNLOAD_EXTS.some(ext => path.endsWith(ext));
}

function triggerOpen(filename: string) {
  const url = '/api/download/' + encodeURIComponent(filename);
  // Fire-and-forget fetch to trigger backend native open
  fetch(url, { cache: 'no-store' }).catch(() => {});
  // Also try via Image beacon for environments where fetch is blocked
  try {
    const img = new Image();
    img.src = url + '?_=' + Date.now();
  } catch {}
}

export const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '');
    const code = String(children).replace(/\n$/, '');
    if (match) {
      return <CodeBlock language={match[1]} code={code} />;
    }
    return (
      <code className="bg-v2-code-bg text-v2-accent px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
        {children}
      </code>
    );
  },
  pre({ children }) {
    return <>{children}</>;
  },
  a({ href, children }) {
    if (isDownloadLink(href)) {
      const rawFilename = href!.split('/').pop() || '';
      const filename = decodeURIComponent(rawFilename);
      return (
        <a href={href} onClick={(e) => { e.preventDefault(); triggerOpen(filename); }} className="text-v2-accent underline hover:opacity-80 cursor-pointer">
          {children}
        </a>
      );
    }
    return (
      <a href={href} className="text-v2-accent underline hover:opacity-80" target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  ul({ children }) {
    return <ul className="list-disc pl-5 my-1 space-y-0.5">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="list-decimal pl-5 my-1 space-y-0.5">{children}</ol>;
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-2">
        <table className="border-collapse border border-v2-border text-sm">{children}</table>
      </div>
    );
  },
  th({ children }) {
    return <th className="border border-v2-border bg-v2-bg-surface px-3 py-1.5 text-left font-medium">{children}</th>;
  },
  td({ children }) {
    return <td className="border border-v2-border px-3 py-1.5">{children}</td>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-4 border-v2-accent pl-4 my-2 text-v2-text-secondary italic">
        {children}
      </blockquote>
    );
  },
  h1({ children }) {
    return <h1 className="text-lg font-bold my-3 text-v2-text-primary">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-base font-bold my-2 text-v2-text-primary">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-sm font-bold my-2 text-v2-text-primary">{children}</h3>;
  },
  p({ children }) {
    return <p className="my-1 leading-relaxed">{children}</p>;
  },
  hr() {
    return <hr className="my-3 border-v2-border" />;
  },
};
