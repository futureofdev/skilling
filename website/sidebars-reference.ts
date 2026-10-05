import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  reference: [
    {type: 'link', label: '← Embed a tutor', href: '/docs/embed'},
    'embedding-a-tutor',
    {
      type: 'category',
      label: 'Persistence backends',
      collapsed: false,
      items: ['persistence', 'persistence-postgres', 'persistence-s3'],
    },
    {
      type: 'category',
      label: 'Lower-level Python APIs',
      items: ['python-session', 'python-tutor'],
    },
  ],
};

export default sidebars;
