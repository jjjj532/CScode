import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { autolinkFileNames, markdownComponents } from '../../lib/markdown';

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const linkedContent = autolinkFileNames(content);
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
