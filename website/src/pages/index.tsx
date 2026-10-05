import {useState, type ReactNode} from 'react';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import CodeBlock from '@theme/CodeBlock';

import styles from './index.module.css';

type Fields = {startPrompt: string; specVersion: string};

function Session(): ReactNode {
  const lines: [string, string, boolean?][] = [
    ['you', '/learn', true],
    ['tutor', 'Welcome back. You finished lesson 1 yesterday, so today is lesson 2: keeping what you learn.'],
    ['tutor', "What's one goal you'd like to keep from this course, in your own words?"],
    ['you', 'Stop rushing to the answer and ask more questions.'],
    ['tutor', "Good one. Let's save that in your showcase folder so it's there next time."],
  ];
  return (
    <div className={styles.session} aria-label="An example tutoring session">
      <div className={styles.sessionBar}>Claude Code · Codex</div>
      <dl className={styles.sessionBody}>
        {lines.map(([who, text, command], index) => (
          <div key={index} className={styles.turn}>
            <dt>{who}</dt>
            <dd className={command ? styles.command : undefined}>{text}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Hero(): ReactNode {
  return (
    <header className={styles.hero}>
      <div className={`container ${styles.heroGrid}`}>
        <div>
          <p className={styles.eyebrow}>For Claude Code and Codex</p>
          <h1 className={styles.title}>Turn your coding assistant into a tutor.</h1>
          <p className={styles.lede}>
            Skilling gives the assistant you already use a course to teach. It explains one idea,
            asks you a question, waits for your answer, and goes back over anything that didn't
            land. Your progress is saved in your own folder, so next time it picks up where you
            stopped.
          </p>
          <div className={styles.actions}>
            <Link className="button button--lg button--learn" to="/docs/learn/start">
              Start learning
            </Link>
            <Link className={`button button--lg button--outline button--primary ${styles.secondary}`} to="/docs/write/first-course">
              Write a course
            </Link>
            <Link className={`button button--lg button--outline button--primary ${styles.secondary}`} to="/docs/embed">
              Embed a tutor
            </Link>
          </div>
          <p className={styles.small}>Free and open source. Learn through your existing coding assistant, or build a tutor into your own app.</p>
        </div>
        <Session />
      </div>
    </header>
  );
}

function CopyPrompt({prompt}: {prompt: string}): ReactNode {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  return (
    <section className={styles.band}>
      <div className="container">
        <div className={styles.promptHead}>
          <div>
            <h2>Start with one paste</h2>
            <p>
              You need <a href="https://git-scm.com/downloads">Git</a>,{' '}
              <a href="https://docs.astral.sh/uv/getting-started/installation/">uv</a>, and Claude
              Code or Codex. Paste this into your assistant. It installs Skilling, sets up a
              learning folder and starts your first lesson.
            </p>
          </div>
          <button type="button" className="button button--learn" onClick={copy} aria-live="polite">
            {copied ? 'Copied' : 'Copy prompt'}
          </button>
        </div>
        <blockquote className={styles.prompt}>{prompt}</blockquote>
        <p className={styles.small}>
          Rather type it yourself? <Link to="/docs/learn/start#type-the-commands-yourself">Use the terminal route</Link>.
        </p>
      </div>
    </section>
  );
}

function HowItWorks(): ReactNode {
  return (
    <section className={styles.section}>
      <div className="container">
        <h2>How it works</h2>
        <ol className={styles.steps}>
          <li>
            <span className={styles.stepLabel}>01 Your coding host</span>
            <strong>Claude Code or Codex</strong>
            <p>The assistant you already have supplies the model. Skilling has none of its own.</p>
          </li>
          <li aria-hidden="true" className={styles.connector}>+</li>
          <li>
            <span className={styles.stepLabel}>02 A course folder</span>
            <strong>Markdown plus one YAML file</strong>
            <p>Lessons with a concept, an exercise and a short quiz. Anyone can write one.</p>
          </li>
          <li aria-hidden="true" className={styles.connector}>→</li>
          <li>
            <span className={styles.stepLabel}>03 Progress you keep</span>
            <strong>Saved on disk, not in a chat</strong>
            <p>Close the assistant any time. Type <code>/learn</code> or <code>$learn</code> to carry on.</p>
          </li>
        </ol>
      </div>
    </section>
  );
}

const yours = [
  ['The course', 'A checked copy is saved in your workspace, so it keeps working if the original moves.'],
  ['Your record', 'Lessons finished, homework and your streak live under .skilling/ in that folder.'],
  ['Your work', 'Notes and code go in showcase/. Keep it, share it or commit it.'],
  ['Your choice of tutor', 'The same folder works in Claude Code and Codex. Switch whenever you like.'],
];

function StaysYours(): ReactNode {
  return (
    <section className={`${styles.section} ${styles.tinted}`}>
      <div className="container">
        <h2>What stays yours</h2>
        <div className={styles.cards}>
          {yours.map(([title, body]) => (
            <div key={title} className={styles.card}>
              <h3>{title}</h3>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Authors(): ReactNode {
  return (
    <section className={styles.section}>
      <div className={`container ${styles.authorGrid}`}>
        <div>
          <p className={styles.eyebrow}>For course authors</p>
          <h2>Write a course once. Anyone can take it.</h2>
          <p>
            A Skilling course is a folder of markdown files. There's no platform to sign up to.
            Scaffold one, check it with the validator, then take it yourself the way a learner
            would before you share it.
          </p>
          <Link className="button button--outline button--primary" to="/docs/write/first-course">
            Write your first course
          </Link>
        </div>
        <CodeBlock language="bash">
          {`uv tool install skilling
skilling init my-course
skilling validate ./my-course --strict
skilling start ./my-course my-course-preview --json`}
        </CodeBlock>
      </div>
    </section>
  );
}

function Producers(): ReactNode {
  return (
    <section className={`${styles.section} ${styles.tinted}`}>
      <div className={`container ${styles.authorGrid}`}>
        <div>
          <p className={styles.eyebrow}>For application developers</p>
          <h2>Your app. Your Agent. A course that remembers.</h2>
          <p>
            Add a streaming tutor to your product with PydanticAI and FastAPI. Keep your own
            model, tools and sign-in. Skilling supplies the teaching flow and saved progress;
            the React reference app shows how to bring them together.
          </p>
          <Link className="button button--outline button--primary" to="/docs/embed">
            Embed a tutor
          </Link>
        </div>
        <div>
          <h3>Start with a working experience</h3>
          <p>
            Stream explanations, render quiz choices and feedback, and resume from durable
            learning state. Use the branded example as a starting point for your own interface.
          </p>
          <p className={styles.small}>
            Experimental Python integration. You provide model access and host the application.
          </p>
          <Link to="/docs/embed/quickstart">Run the React example →</Link>
        </div>
      </div>
    </section>
  );
}

function Status({specVersion}: {specVersion: string}): ReactNode {
  return (
    <section className={styles.status}>
      <div className="container">
        <dl className={styles.facts}>
          <div>
            <dt>Specification</dt>
            <dd>
              <Link to="/spec">{specVersion}</Link>
            </dd>
          </div>
          <div>
            <dt>Independent implementations</dt>
            <dd>
              <Link to="/docs/write/status">0 so far</Link>
            </dd>
          </div>
          <div>
            <dt>Conformance</dt>
            <dd>Self-certified</dd>
          </div>
          <div>
            <dt>Licence</dt>
            <dd>Apache-2.0 · spec CC BY 4.0</dd>
          </div>
        </dl>
        <p className={styles.small}>
          Skilling is an open format, and it's young. Every implementation so far comes from one
          team. If you build another, we'd like to hear about it.
        </p>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  const {startPrompt, specVersion} = siteConfig.customFields as Fields;
  return (
    <Layout
      title="Turn your coding assistant into a tutor"
      description="Learn with Claude Code or Codex, write portable courses, or embed a streaming React tutor in your app. Skilling keeps learning progress durable and under your control.">
      <Hero />
      <main>
        <CopyPrompt prompt={startPrompt} />
        <HowItWorks />
        <StaysYours />
        <Authors />
        <Producers />
        <Status specVersion={specVersion} />
      </main>
    </Layout>
  );
}
