import { Fragment } from 'react';

/**
 * Renders an assistant reply as readable text.
 *
 * The chat bubble used to render `{msg.content}` raw, so a model answering in
 * markdown produced a wall of `**bold**` and `| pipes |` — a table dumped as
 * prose, unreadable exactly where the clinical content lives.
 *
 * Deliberately NOT a full markdown engine and NOT `dangerouslySetInnerHTML`:
 * this text comes from a model, so it is untrusted, and every branch here emits
 * React elements rather than HTML. It covers what the models actually produce —
 * headings, bullets, numbered steps, bold, and tables.
 *
 * Tables become label/value lines rather than a grid. A chat column is ~600px;
 * a four-column table cannot fit one even when rendered properly, and the
 * honest fix is to stop pretending it is a table.
 */

function inline(text, keyPrefix) {
  // **bold** and `code`, one pass, no nesting — that is all the models emit here.
  const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.filter(Boolean).map((part, i) => {
    const key = `${keyPrefix}-${i}`;
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={key} style={{ background: 'rgba(0,0,0,.06)', padding: '0 .25em', borderRadius: 3 }}>
          {part.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={key}>{part}</Fragment>;
  });
}

const isDivider = (row) => /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(row) && row.includes('-');
const cells = (row) => row.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((c) => c.trim());

export default function AssistantMarkdown({ content }) {
  if (!content) return null;

  // A model often emits a whole table on ONE line. Split those apart first, or
  // the row separators never reach the block parser below.
  const normalised = String(content)
    .replace(/\s*\|\s*\|\s*/g, '|\n|')
    .replace(/\*\*(Short answer|Bottom line|What to keep in mind|Practical suggestion)\*\*/gi,
             '\n\n**$1**\n');

  const lines = normalised.split('\n');
  const blocks = [];
  let paragraph = [];
  let table = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push({ kind: 'p', text: paragraph.join(' ') });
    paragraph = [];
  };
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !isDivider(r)).map(cells);
    const [header, ...body] = rows;
    blocks.push({ kind: 'table', header, body });
    table = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.trim().startsWith('|')) {
      flushParagraph();
      table.push(line);
      continue;
    }
    flushTable();

    if (!line.trim()) { flushParagraph(); continue; }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) { flushParagraph(); blocks.push({ kind: 'h', text: heading[2] }); continue; }

    // A line that is ONLY bold reads as a heading, which is how these replies
    // are actually structured ("**Bottom line:**").
    const boldOnly = line.trim().match(/^\*\*(.+?):?\*\*:?$/);
    if (boldOnly) { flushParagraph(); blocks.push({ kind: 'h', text: boldOnly[1] }); continue; }

    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    if (bullet) { flushParagraph(); blocks.push({ kind: 'li', text: bullet[1] }); continue; }

    const numbered = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (numbered) { flushParagraph(); blocks.push({ kind: 'li', text: numbered[2], n: numbered[1] }); continue; }

    paragraph.push(line.trim());
  }
  flushParagraph();
  flushTable();

  return (
    <div className="assistant-markdown">
      {blocks.map((b, i) => {
        if (b.kind === 'h') {
          return (
            <div key={i} style={{ fontWeight: 700, margin: i ? '.75em 0 .25em' : '0 0 .25em' }}>
              {inline(b.text, `h${i}`)}
            </div>
          );
        }
        if (b.kind === 'li') {
          return (
            <div key={i} style={{ display: 'flex', gap: '.5em', margin: '.2em 0' }}>
              <span aria-hidden="true" style={{ opacity: .6 }}>{b.n ? `${b.n}.` : '•'}</span>
              <span>{inline(b.text, `li${i}`)}</span>
            </div>
          );
        }
        if (b.kind === 'table') {
          // Label/value lines, not a grid — see the note at the top.
          return (
            <div key={i} style={{ margin: '.5em 0' }}>
              {b.body.map((row, r) => (
                <div key={r} style={{ margin: '.4em 0' }}>
                  <div style={{ fontWeight: 600 }}>{inline(row[0] || '', `t${i}-${r}-k`)}</div>
                  {row.slice(1).map((cell, c) => cell ? (
                    <div key={c} style={{ marginLeft: '.75em' }}>
                      {b.header?.[c + 1] ? (
                        <span style={{ opacity: .65 }}>{b.header[c + 1]}: </span>
                      ) : null}
                      {inline(cell, `t${i}-${r}-${c}`)}
                    </div>
                  ) : null)}
                </div>
              ))}
            </div>
          );
        }
        return <p key={i} style={{ margin: '.4em 0' }}>{inline(b.text, `p${i}`)}</p>;
      })}
    </div>
  );
}
