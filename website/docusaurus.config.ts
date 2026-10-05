import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import repoLinks from './plugins/repo-links.mjs';

const REPO = 'https://github.com/futureofdev/skilling';
const BASE_URL = '/skilling/';
// Resolve repository files from this config's directory, whatever the working directory is.
const repoFile = (relative: string) => path.resolve(__dirname, '..', relative);

// The start prompt and spec version are read from their canonical homes at build time, so the
// site can never drift from the README (whose prompt the onboarding tests pin) or spec/README.md.
function readStartPrompt(): string {
  const lines = readFileSync(repoFile('README.md'), 'utf-8').split('\n');
  const first = lines.findIndex((line) => line.startsWith('> Check that'));
  if (first < 0) throw new Error('README.md no longer contains the start prompt');
  const prompt: string[] = [];
  for (const line of lines.slice(first)) {
    if (!line.startsWith('> ')) break;
    prompt.push(line.slice(2).trim());
  }
  return prompt.join(' ');
}

function readSpecVersion(): string {
  const match = readFileSync(repoFile('spec/README.md'), 'utf-8').match(/\*\*Version ([0-9][\w.-]*)\*\*/);
  if (!match) throw new Error('spec/README.md no longer declares a version');
  return match[1];
}

const config: Config = {
  title: 'Skilling',
  tagline: 'Turn the coding assistant you already use into a one-to-one tutor.',
  favicon: 'favicon/favicon.ico',

  future: {
    v4: true,
  },

  customFields: {
    startPrompt: readStartPrompt(),
    specVersion: readSpecVersion(),
  },

  url: 'https://futureofdev.github.io',
  baseUrl: BASE_URL,
  organizationName: 'futureofdev',
  projectName: 'skilling',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',

  // Brand files are served straight from brand/assets so the site never carries a second copy.
  staticDirectories: ['../brand/assets'],

  markdown: {
    // .md is CommonMark (the spec and guides stay plain markdown); .mdx opts into JSX.
    format: 'detect',
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  headTags: [
    {tagName: 'link', attributes: {rel: 'icon', type: 'image/svg+xml', href: `${BASE_URL}favicon/favicon.svg`}},
    {tagName: 'link', attributes: {rel: 'apple-touch-icon', href: `${BASE_URL}favicon/apple-touch-icon-180.png`}},
    {tagName: 'link', attributes: {rel: 'preconnect', href: 'https://fonts.googleapis.com'}},
    {tagName: 'link', attributes: {rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: 'anonymous'}},
  ],
  stylesheets: [
    'https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@112,800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap',
  ],

  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      {
        docs: {
          path: 'guides',
          routeBasePath: 'docs',
          sidebarPath: './sidebars.ts',
          editUrl: `${REPO}/edit/main/website/`,
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    [
      '@docusaurus/plugin-content-docs',
      {
        // The normative specification is rendered from spec/, never copied.
        id: 'spec',
        path: '../spec',
        routeBasePath: 'spec',
        sidebarPath: './sidebars-spec.ts',
        editUrl: ({docPath}: {docPath: string}) => `${REPO}/edit/main/spec/${docPath}`,
        beforeDefaultRemarkPlugins: [[repoLinks, {repo: REPO, repoDir: repoFile('.'), root: 'spec'}]],
      },
    ],
  ],

  themeConfig: {
    image: 'github/social-preview-1280x640.png',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Skilling',
      logo: {
        alt: 'Skilling',
        // The Cut is always Ink on a light field: bare on light, inside its tile on dark.
        src: 'mark/skilling-mark.svg',
        srcDark: 'tiles/skilling-tile-cloud.svg',
        width: 28,
        height: 28,
      },
      items: [
        {type: 'docSidebar', sidebarId: 'learn', position: 'left', label: 'Learn'},
        {type: 'docSidebar', sidebarId: 'write', position: 'left', label: 'Write a course'},
        {type: 'docSidebar', sidebarId: 'embed', position: 'left', label: 'Embed a tutor'},
        {type: 'docSidebar', sidebarId: 'spec', docsPluginId: 'spec', position: 'left', label: 'Specification'},
        {href: REPO, label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'light',
      links: [
        {
          title: 'Learn',
          items: [
            {label: 'Why learn this way', to: '/docs/learn/why'},
            {label: 'Install your tools', to: '/docs/learn/install'},
            {label: 'Start your first course', to: '/docs/learn/start'},
            {label: 'Troubleshooting', to: '/docs/learn/troubleshooting'},
          ],
        },
        {
          title: 'Write',
          items: [
            {label: 'Why write a course', to: '/docs/write/why'},
            {label: 'Your first course', to: '/docs/write/first-course'},
            {label: 'Publish and share', to: '/docs/write/publish'},
            {label: 'Error codes', href: `${REPO}/blob/main/docs/error-codes.md`},
          ],
        },
        {
          title: 'Embed',
          items: [
            {label: 'Build a learning app', to: '/docs/embed'},
            {label: 'Run the React example', to: '/docs/embed/quickstart'},
            {label: 'Integrate with FastAPI', to: '/docs/embed/fastapi'},
            {label: 'Customize your tutor', to: '/docs/embed/customize'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'Specification', to: '/spec'},
            {label: 'Format status', to: '/docs/write/status'},
            {label: 'Contributing', href: `${REPO}/blob/main/CONTRIBUTING.md`},
            {label: 'GitHub', href: REPO},
          ],
        },
      ],
      copyright:
        'Specification text CC BY 4.0. Reference implementation Apache-2.0. Skilling was created by Future of Dev.',
    },
    mermaid: {
      // Colours come from custom.css (brand tokens, per colour mode); 'base' keeps Mermaid neutral.
      theme: {light: 'base', dark: 'base'},
      options: {
        fontFamily: 'Inter, -apple-system, Segoe UI, Arial, sans-serif',
        flowchart: {curve: 'linear', htmlLabels: true, padding: 14},
        sequence: {mirrorActors: false},
      },
    },
    prism: {
      theme: prismThemes.vsLight,
      darkTheme: prismThemes.vsDark,
      additionalLanguages: ['bash', 'yaml'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
