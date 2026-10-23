import { render } from '@testing-library/react';
import MarkdownText from '../components/MarkdownText';

function html(text) {
  return render(<MarkdownText text={text} />).container.innerHTML;
}

test('renders the headings, bold and paragraphs chat answers use', () => {
  const { container } = render(
    <MarkdownText
      text={"## What's Changed in the NAB Thesis\n\n**Most significant new development: workforce restructuring**\nNAB announced plans to cut up to 2,500 jobs."}
    />
  );
  expect(container.querySelector('h4').textContent).toBe("What's Changed in the NAB Thesis");
  expect(container.querySelector('strong').textContent).toBe('Most significant new development: workforce restructuring');
  expect(container.textContent).not.toMatch(/[#*]/);
  // A bold lead-in and the line after it stay one paragraph, on separate lines.
  expect(container.querySelectorAll('p')).toHaveLength(1);
  expect(container.querySelector('br')).not.toBeNull();
});

test('renders bullet and numbered lists', () => {
  const { container } = render(<MarkdownText text={'- one\n- *two*\n\n1. first\n2. second'} />);
  expect(container.querySelectorAll('ul li')).toHaveLength(2);
  expect(container.querySelector('ul em').textContent).toBe('two');
  expect(container.querySelectorAll('ol li')).toHaveLength(2);
});

test('never turns answer text into markup', () => {
  const out = html('<img src=x onerror=alert(1)> **<b>bold</b>**');
  expect(out).not.toContain('<img');
  expect(out).toContain('&lt;img');
  expect(out).toContain('<strong>&lt;b&gt;bold&lt;/b&gt;</strong>');
});

test('leaves identifiers and plain text alone', () => {
  expect(html('the match_threshold_value field')).toContain('the match_threshold_value field');
  expect(html('Plain answer with no markdown.')).toBe('<div><p><span>Plain answer with no markdown.</span></p></div>');
});
