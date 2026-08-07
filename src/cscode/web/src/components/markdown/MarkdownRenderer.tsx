import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../lib/markdown';

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const linkedContent = content.replace(
    /(?<!\()(\/tmp\/cscode-outputs\/\S+|\/outputs\/\S+)/g,
    (match, path) => {
      const url = path.replace(/[.,;:!?，。]+$/, '');
      return `[${url}](${url})${match.slice(url.length)}`;
    }
  );
  return (
    <div className="text-sm leading-relaxed [&_p]:my-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
      >
        {linkedContent}
      </ReactMarkdown>
    </div>
  );
}
