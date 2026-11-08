export class ExactNumber {
  constructor(source) { this.source = source; }
}

export class ApiError extends Error {
  constructor(message, status = 0, code = '') { super(message); this.status = status; this.code = code; }
}

export function parseResponse(text) {
  return JSON.parse(text, (key, value, context) => {
    if (typeof value === 'number' && !Number.isSafeInteger(value)) {
      if (!context?.source) throw new ApiError('This browser cannot display these JSON numbers exactly. Use an up-to-date Chrome or Edge.');
      return new ExactNumber(context.source);
    }
    return value;
  });
}

async function response(path, options = {}) {
  let result;
  try { result = await fetch(path, { credentials: 'same-origin', cache: 'no-store', redirect: 'error', ...options }); }
  catch { throw new ApiError('Cannot reach the workspace. Check that the backend is running, then try again.'); }
  if (!result.ok) {
    let detail;
    try { detail = JSON.parse(await result.text()).detail; } catch { /* Keep a bounded generic message. */ }
    const message = typeof detail === 'string' ? detail : detail?.message || (Array.isArray(detail) ? 'The request contains an invalid identifier or option.' : 'The request could not be completed.');
    const side = ['old', 'new'].includes(detail?.side) ? detail.side : '';
    const error = new ApiError((side ? (side === 'old' ? 'Old' : 'New') + ' specification: ' : '') + message, result.status, detail?.code || '');
    error.side = side;
    throw error;
  }
  return result;
}

async function json(path, options) {
  const result = await response(path, options);
  try { return parseResponse(await result.text()); }
  catch (error) { throw error instanceof ApiError ? error : new ApiError('The server returned an unreadable response.'); }
}

export const api = {
  aiStatus: () => json('/api/ai/status'),
  explain: (id, findingId) => json('/api/comparisons/' + encodeURIComponent(id) + '/explanations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ finding_id: findingId, allow_external_processing: true }) }),
  status: () => json('/api/system/database'),
  history: cursor => json('/api/comparisons?limit=10' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '')),
  detail: id => json('/api/comparisons/' + encodeURIComponent(id)),
  remove: id => response('/api/comparisons/' + encodeURIComponent(id), { method: 'DELETE' }),
  async compare(old, next, save) {
    const form = new FormData(); form.append('old', old); form.append('new', next);
    return json(save ? '/api/comparisons' : '/api/specifications/compare', { method: 'POST', body: form });
  },
  async example(name) {
    const result = await response('/api/examples/' + encodeURIComponent(name));
    return new File([await result.blob()], name, { type: 'application/json' });
  },
  async download(id, format) {
    if (!['json', 'markdown'].includes(format)) throw new ApiError('Choose JSON or Markdown.');
    const result = await response('/api/comparisons/' + encodeURIComponent(id) + '/export?format=' + format);
    const href = URL.createObjectURL(await result.blob());
    const link = document.createElement('a'); link.href = href; link.download = 'comparison-' + id + (format === 'json' ? '.json' : '.md');
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(href), 1000);
  },
};

export function unpack(body) {
  const result = body.result || body;
  const report = result?.comparison;
  if (!report || !Array.isArray(report.findings) || !Array.isArray(report.coverage?.analysis_warnings) || !Array.isArray(report.policy_assumptions) || !result.old || !result.new || !report.summary) throw new ApiError('The server returned an unexpected comparison report.');
  const severities = ['breaking', 'potentially_breaking', 'informational', 'needs_review'];
  if (!severities.every(key => Number.isSafeInteger(report.summary[key]) && report.summary[key] >= 0) || !Number.isSafeInteger(report.summary.total_findings)) throw new ApiError('The report summary is invalid.');
  if (!report.policy_assumptions.every(text => typeof text === 'string') || !report.findings.every(f => typeof f.id === 'string' && typeof f.title === 'string' && typeof f.path === 'string' && typeof f.method === 'string' && typeof f.rule_id === 'string' && Array.isArray(f.location) && f.location.every(item => typeof item === 'string') && severities.includes(f.severity) && typeof f.before?.present === 'boolean' && typeof f.after?.present === 'boolean')) throw new ApiError('The report findings are incomplete.');
  return { result, record: body.id ? body : null };
}
