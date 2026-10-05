// Include the exact Vite output in both Python distribution formats.
import { cpSync, rmSync } from 'node:fs';
const source = new URL('../dist/', import.meta.url);
const target = new URL('../src/skilling_react_example/static/', import.meta.url);
rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });
