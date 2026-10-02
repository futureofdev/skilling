// Rewrites links in rendered repository markdown that point outside the rendered folder
// (or at non-markdown files such as LICENSE) to their GitHub blob URLs, so the site can use
// onBrokenLinks: 'throw' while the source keeps its repository-relative links.
import {statSync} from 'node:fs';
import path from 'node:path';

const EXTERNAL = /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i;

const isDirectory = (target) => {
  try {
    return statSync(target).isDirectory();
  } catch {
    return false;
  }
};

export default function repoLinks({repo, repoDir, root}) {
  const rootDir = path.join(repoDir, root);
  return (tree, file) => {
    const fromDir = path.dirname(file.path);
    const visit = (node) => {
      if ((node.type === 'link' || node.type === 'definition') && node.url && !EXTERNAL.test(node.url)) {
        const [target, hash] = node.url.split('#');
        if (target) {
          const absolute = path.resolve(fromDir, target);
          const inside = absolute.startsWith(rootDir + path.sep);
          if (!inside || !absolute.endsWith('.md')) {
            const relative = path.relative(repoDir, absolute).split(path.sep).join('/');
            const kind = isDirectory(absolute) ? 'tree' : 'blob';
            node.url = `${repo}/${kind}/main/${relative}${hash ? `#${hash}` : ''}`;
          }
        }
      }
      for (const child of node.children ?? []) visit(child);
    };
    visit(tree);
  };
}
