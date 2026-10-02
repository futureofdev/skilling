import type {ReactNode} from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import CodeBlock from '@theme/CodeBlock';

// Both components read the canonical prompt from README.md (via customFields), so the pinned
// course tag in the guides moves with every release without a second place to edit.
function usePrompt(): string {
  const {siteConfig} = useDocusaurusContext();
  return (siteConfig.customFields as {startPrompt: string}).startPrompt;
}

export function StartPrompt(): ReactNode {
  return (
    <CodeBlock language="text" title="Paste into Claude Code or Codex" className="start-prompt">
      {usePrompt()}
    </CodeBlock>
  );
}

export function StartCommands(): ReactNode {
  const start = usePrompt().match(/`(skilling start [^`]+)`/);
  if (!start) throw new Error('The start prompt no longer contains a skilling start command');
  return (
    <CodeBlock language="bash">
      {['uv tool install skilling', 'skilling --version', start[1]].join('\n')}
    </CodeBlock>
  );
}
