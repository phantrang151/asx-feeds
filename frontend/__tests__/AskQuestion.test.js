/**
 * Level 4 of the request token limit tests (levels 1-3 are in
 * tests/system/test_request_token_limit.py): how AskQuestion shows each outcome of /api/ask.
 *
 *  - per-request token ceiling -> backend answers HTTP 200 with the decline as `answer`
 *    -> shown in the ANSWER box like a normal answer
 *  - daily token budget        -> backend answers HTTP 429 with `detail`
 *    -> shown as the red ERROR line, answer box left empty
 *
 * fetch and the Supabase session are faked, so no backend, login or network is needed.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import AskQuestion from '../components/AskQuestion';

jest.mock('../lib/supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: jest.fn().mockResolvedValue({ data: { session: { access_token: 'fake-token' } } }),
    },
  },
}));

const TOKEN_CEILING_MESSAGE =
  'This question required more processing than we allow per request. Please try asking something more specific.';
const DAILY_BUDGET_MESSAGE = "You've used your token budget for today - please try again later.";

function mockApiResponse(status, body) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

function askQuestion(text = "What was ANZ's FY2025 profit?") {
  fireEvent.change(screen.getByPlaceholderText(/Ask a question/), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
}

afterEach(() => {
  jest.clearAllMocks();
});

test('per-request token ceiling (200 + decline) is shown in the answer box, not as an error', async () => {
  mockApiResponse(200, { answer: TOKEN_CEILING_MESSAGE, category: 'declined', references: [] });
  const { container } = render(<AskQuestion />);

  askQuestion();

  const shown = await screen.findByText(TOKEN_CEILING_MESSAGE);
  expect(shown.closest('.qa-answer')).not.toBeNull();
  expect(container.querySelector('.error')).toBeNull();
});

test('daily token budget (429 + detail) is shown as the red error line', async () => {
  mockApiResponse(429, { detail: DAILY_BUDGET_MESSAGE });
  const { container } = render(<AskQuestion />);

  askQuestion();

  const shown = await screen.findByText(DAILY_BUDGET_MESSAGE);
  expect(shown).toHaveClass('error');
  expect(container.querySelector('.qa-answer')).toBeNull(); // no answer rendered
});

test('the request carries the login token, the question and the conversation thread id', async () => {
  mockApiResponse(200, { answer: 'ok', references: [] });
  render(<AskQuestion />);

  askQuestion('Why is NAB laying off its staff?');
  await screen.findByText('ok');

  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toMatch(/\/api\/ask$/);
  expect(options.headers.Authorization).toBe('Bearer fake-token');
  const body = JSON.parse(options.body);
  expect(body.question).toBe('Why is NAB laying off its staff?');
  expect(body.thread_id).toMatch(/^[0-9a-f-]{36}$/);
});

test('a 429 without a detail falls back to a generic message', async () => {
  mockApiResponse(429, {});
  render(<AskQuestion />);

  askQuestion();

  expect(await screen.findByText('Failed to get an answer.')).toHaveClass('error');
});

test('sample questions use the given ticker and fill the box without asking', () => {
  global.fetch = jest.fn();
  render(<AskQuestion sampleTicker="NAB.AX" />);

  const chip = screen.getByRole('button', { name: /What has changed in my NAB\.AX investment thesis\?/ });
  expect(chip).toHaveTextContent('My investment thesis');
  expect(screen.getAllByRole('button', { name: /NAB\.AX/ })).toHaveLength(3);

  fireEvent.click(chip);
  expect(screen.getByPlaceholderText(/Ask a question/)).toHaveValue('What has changed in my NAB.AX investment thesis?');
  expect(global.fetch).not.toHaveBeenCalled(); // filled in for editing, not sent
});

test('no sample questions until the user has a ticker', () => {
  render(<AskQuestion />);
  expect(screen.queryByRole('button', { name: /investment thesis/ })).toBeNull();
  expect(screen.getByText(/Add a ticker and a feed/)).toBeInTheDocument();
});
