import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './markdown.css'

/**
 * Open links from agent output in a new tab so the IDE view is never navigated
 * away. react-markdown sanitises URLs (defaultUrlTransform) and escapes raw HTML
 * by default, so rendering untrusted model output here is safe.
 */
const components: Components = {
  a: ({ href, title, children }) => (
    <a href={href} title={title} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
}

/**
 * Renders an agent chat response as GitHub-flavoured Markdown.
 */
export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
