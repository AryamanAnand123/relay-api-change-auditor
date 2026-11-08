import { ExactNumber } from './api.js';

export const labels = { breaking: 'Breaking', potentially_breaking: 'Potential', informational: 'Informational', needs_review: 'Needs review' };
export const short = (value, length = 110) => { const text = String(value ?? ''); return text.length > length ? text.slice(0, length) + '…' : text; };
export const bytes = value => value >= 1048576 ? (value / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(value / 1024)) + ' KB';
export const date = value => new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

export function displayJson(value, max = 20000) {
  // A bounded formatter emits exact numeric lexemes instead of rounding large
  // integers through JavaScript Number or displaying them as quoted strings.
  function* tokens(item, depth = 0) {
    if (item instanceof ExactNumber) { yield item.source; return; }
    if (item === null || typeof item !== 'object') { yield JSON.stringify(item) ?? 'null'; return; }
    const entries = Array.isArray(item) ? item.map((v, i) => [i, v]) : Object.entries(item);
    const array = Array.isArray(item);
    yield array ? '[' : '{';
    for (let index = 0; index < entries.length; index++) {
      yield (index ? ',' : '') + '\n' + '  '.repeat(depth + 1);
      const [key, next] = entries[index];
      if (!array) yield JSON.stringify(key) + ': ';
      yield* tokens(next, depth + 1);
    }
    if (entries.length) yield '\n' + '  '.repeat(depth);
    yield array ? ']' : '}';
  }
  let text = '';
  for (const token of tokens(value)) {
    if (text.length + token.length > max) return { text: text + token.slice(0, max - text.length), clipped: true };
    text += token;
  }
  return { text, clipped: false };
}
