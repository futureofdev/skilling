import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  embed: [
    'embed/index',
    'embed/quickstart',
    'embed/fastapi',
    'embed/react',
    'embed/customize',
    'embed/operate',
  ],
  learn: [
    'learn/index',
    'learn/why',
    {
      type: 'category',
      label: 'Get set up',
      collapsed: false,
      items: ['learn/terminal', 'learn/install', 'learn/start'],
    },
    {
      type: 'category',
      label: 'While you learn',
      collapsed: false,
      items: ['learn/first-lesson', 'learn/progress-and-homework', 'learn/how-it-works'],
    },
    {
      type: 'category',
      label: 'Your learning folder',
      collapsed: false,
      items: ['learn/your-workspace', 'learn/courses'],
    },
    'learn/troubleshooting',
    'learn/glossary',
  ],
  write: [
    'write/index',
    'write/why',
    'write/how-delivery-works',
    {
      type: 'category',
      label: 'Write your course',
      collapsed: false,
      items: [
        'write/setup',
        'write/first-course',
        'write/lesson-anatomy',
        'write/teaching-well',
        'write/objectives-quizzes-homework',
        'write/extras',
      ],
    },
    {
      type: 'category',
      label: 'Check and share',
      collapsed: false,
      items: ['write/validate', 'write/preview', 'write/publish', 'write/updates'],
    },
    'write/status',
  ],
};

export default sidebars;
