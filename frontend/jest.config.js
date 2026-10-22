// Jest for frontend component tests. next/jest compiles JSX the same way the Next.js app does
// (SWC) and loads next.config.js / .env files, so tests see components as the app builds them.
const nextJest = require('next/jest');

const createJestConfig = nextJest({ dir: './' });

module.exports = createJestConfig({
  testEnvironment: 'jsdom', // a simulated browser DOM - no real browser or server needed
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testPathIgnorePatterns: ['<rootDir>/node_modules/', '<rootDir>/.next/', '<rootDir>/out/'],
});
