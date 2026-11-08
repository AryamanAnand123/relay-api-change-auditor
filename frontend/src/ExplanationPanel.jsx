import React, { useEffect, useRef, useState } from 'react';
import { api } from './api.js';

export default function ExplanationPanel({ record, finding }) {
  const [status, setStatus] = useState(null), [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(false), [content, setContent] = useState(null), [error, setError] = useState('');
  const active = useRef(true), running = useRef(false);
  async function refresh() {
    try { const data = await api.aiStatus(); if (active.current) { setStatus(data); setError(''); } }
    catch { if (active.current) setStatus({ status: 'unavailable' }); }
  }
  useEffect(() => { active.current = true; refresh(); return () => { active.current = false; }; }, []);
  async function generate() {
    if (!consent || running.current || !record) return;
    running.current = true; setLoading(true); setError('');
    try { const data = await api.explain(record.id, finding.id); if (active.current) setContent(data); }
    catch (failure) { if (active.current) setError(failure.message); }
    finally { running.current = false; if (active.current) setLoading(false); }
  }
  const ready = status?.status === 'ready';
  return <section className="ai-panel" aria-label="AI migration guidance" aria-busy={loading}>
    <div className="ai-heading"><h3>AI migration guidance</h3><span>Optional</span></div>
    <p className="ai-intro">Explain this finding and plan migration checks with LangChain and Groq.</p>
    {!record ? <p className="ai-state">Save this comparison to request an explanation. Rule evidence remains available above.</p>
      : finding.severity === 'needs_review' ? <p className="ai-state">Unsupported semantics need manual review. AI explanations are available for supported findings.</p>
      : <>
        {!ready && <div className="ai-state">{!status ? 'Checking AI availability...' : status.status === 'missing_key' ? <>Add your Free-plan key using <code>scripts/configure-ai.py</code>, then retry.</> : status.status === 'disabled' ? 'AI is disabled in backend settings.' : 'AI status is unavailable. The comparison still works.'}{status && <button type="button" className="text-button" onClick={refresh}>Refresh AI status</button>}</div>}
        {ready && !content && <>
          <label className="ai-consent"><input type="checkbox" checked={consent} disabled={loading} onChange={event => setConsent(event.target.checked)} />Send this finding's bounded evidence to Groq for an explanation.</label>
          <p className="ai-privacy">Includes endpoint and field names, pointers, and selected contract values. Descriptions, examples, and original files are excluded. Use your Free-plan account.</p>
          <button type="button" className="primary-button ai-generate" disabled={!consent || loading} onClick={generate}>{loading ? 'Generating explanation...' : 'Explain finding'}</button>
          <small className="ai-budget">One provider attempt. No automatic retries. Rule results stay unchanged.</small>
        </>}
        {error && <p className="ai-error" role="alert">{error}</p>}
        {content && <div className="ai-content" role="status">
          <p className="ai-generated-label">AI-generated guidance{content.cached ? ' · Reused from memory cache' : ''}</p>
          <p>{content.content.explanation}</p>
          {[['Migration steps', content.content.migration_steps], ['Verification checks', content.content.verification_steps], ['Caveats', content.content.caveats]].map(([title, items]) => <div key={title}><h4>{title}</h4><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>)}
          <h4>Referenced evidence</h4><ul className="ai-references">{content.content.evidence_references.map(key => <li key={key}><strong>{key}</strong><code>{content.references[key]?.pointer || 'Location unavailable'}</code></li>)}</ul>
          <p className="ai-provenance">Groq · {content.provenance.reported_model} · {content.provenance.latency_ms} ms · Prompt {content.provenance.prompt_version}</p>
          <p className="ai-disclaimer">{content.notice} Guidance is cached in backend memory for up to one hour and is separate from comparison exports.</p>
        </div>}
      </>}
    </section>;
}
