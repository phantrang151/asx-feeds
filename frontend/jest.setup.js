// Adds DOM matchers such as toBeInTheDocument() / toHaveClass() to Jest's expect().
import '@testing-library/jest-dom';
import { randomUUID } from 'crypto';

// AskQuestion creates its thread id with crypto.randomUUID(); jsdom's simulated browser
// doesn't always provide it, so borrow Node's.
if (!globalThis.crypto?.randomUUID) {
  Object.defineProperty(globalThis, 'crypto', {
    value: { ...(globalThis.crypto || {}), randomUUID },
    configurable: true,
  });
}
