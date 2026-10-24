// Renders the small Markdown subset the chat answers use - headings, **bold**, *italic*,
// `code`, bullet/numbered lists and paragraphs - as React elements. Deliberately not an
// HTML pipeline (no dangerouslySetInnerHTML): answer text can never inject markup, and
// anything outside this subset just shows as plain text.

const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
// Underscore emphasis only at word boundaries, so identifiers like match_threshold stay intact.
const INLINE = /(\*\*[^*]+\*\*|(?<!\w)__[^_]+__(?!\w)|\*[^*\s][^*]*\*|(?<!\w)_[^_\s][^_]*_(?!\w)|`[^`]+`)/g;

function renderInline(text) {
  return text.split(INLINE).map((part, i) => {
    if (/^(\*\*|__).+\1$/.test(part)) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (/^`.+`$/.test(part)) return <code key={i}>{part.slice(1, -1)}</code>;
    if (/^([*_]).+\1$/.test(part)) return <em key={i}>{part.slice(1, -1)}</em>;
    return part;
  });
}

// Groups lines into blocks: a heading line, a run of list items of one kind, or a paragraph
// (consecutive plain lines, kept as line breaks).
function parseBlocks(markdown) {
  const blocks = [];
  for (const line of markdown.replace(/\r\n/g, '\n').split('\n')) {
    const last = blocks[blocks.length - 1];
    const heading = line.match(HEADING);
    const bullet = line.match(BULLET);
    const numbered = !bullet && line.match(NUMBERED);

    if (!line.trim()) {
      blocks.push({ type: 'break' });
    } else if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] });
    } else if (bullet || numbered) {
      const type = bullet ? 'ul' : 'ol';
      const item = (bullet || numbered)[1];
      if (last && last.type === type) last.items.push(item);
      else blocks.push({ type, items: [item] });
    } else if (last && last.type === 'p') {
      last.lines.push(line);
    } else {
      blocks.push({ type: 'p', lines: [line] });
    }
  }
  return blocks.filter((b) => b.type !== 'break');
}

export default function MarkdownText({ text, className }) {
  return (
    <div className={className}>
      {parseBlocks(text || '').map((block, i) => {
        if (block.type === 'heading') {
          // Answers sit under the page's own headings, so even "#" renders as a small heading.
          const Tag = block.level <= 2 ? 'h4' : 'h5';
          return <Tag key={i}>{renderInline(block.text)}</Tag>;
        }
        if (block.type === 'ul' || block.type === 'ol') {
          const List = block.type;
          return (
            <List key={i}>
              {block.items.map((item, j) => (
                <li key={j}>{renderInline(item)}</li>
              ))}
            </List>
          );
        }
        return (
          <p key={i}>
            {block.lines.map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {renderInline(line)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
