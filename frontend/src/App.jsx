import React, { useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, unpack } from './api.js';
import { bytes, date, displayJson, labels, short } from './format.js';
import ExplanationPanel from './ExplanationPanel.jsx';

const SEVERITIES = Object.keys(labels);
const ICONS = {
  arrows: 'M4 7h14l-4-4m4 4-4 4M20 17H6l4-4m-4 4 4 4',
  grid: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  clock: 'M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  plus: 'M12 5v14M5 12h14', upload: 'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
  file: 'M14 2H5v20h14V7l-5-5zm0 0v6h5M8 12h8M8 16h6',
  chevron: 'm9 5 7 7-7 7', close: 'm6 6 12 12M6 18 18 6',
  check: 'm5 12 4 4L19 6', search: 'm16 16 5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  shield: 'm12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4zm-4 10 3 3 5-6',
  download: 'M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  info: 'M12 11v6M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  alert: 'm12 3 10 18H2L12 3zm0 6v5m0 3h.01',
  refresh: 'M20 7V2l-3 3a9 9 0 1 0 3 11M20 7h-5',
  monitor: 'M3 3h18v14H3zM8 21h8M12 17v4',
  branch: 'M6 3v12a5 5 0 0 0 5 5h3M6 7h9a4 4 0 0 1 4 4v2M3 3h6M16 13h6M14 17l3 3-3 3',
  layers: 'm12 2 10 5-10 5L2 7l10-5zM2 12l10 5 10-5M2 17l10 5 10-5',
};
function Icon({ name, size = 18, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={ICONS[name] || ICONS.file} /></svg>;
}
function Spinner() { return <span className="spinner" aria-hidden="true" />; }
function Severity({ value }) { return <span className={'severity ' + value}><span />{labels[value] || value}</span>; }

function FileSlot({ side, file, disabled, invalid, onFile, onRemove, onError }) {
  const [dragging, setDragging] = useState(false);
  const title = side === 'old' ? 'Old specification' : 'New specification';
  return <div className="file-slot"><div className="slot-label"><span className={'version-dot ' + side} />{title}<span className="slot-hint">{side === 'old' ? 'Baseline' : 'Proposed'}</span></div>
    <label htmlFor={side + '-file'} className={'drop-zone ' + (file ? 'has-file ' : '') + (dragging ? 'dragging ' : '') + (invalid ? 'invalid' : '')}
      onDragOver={e => { e.preventDefault(); if (!disabled) setDragging(true); }} onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); if (disabled) return; if (e.dataTransfer.files.length !== 1) return onError('Choose one JSON file for each version.'); onFile(side, e.dataTransfer.files[0]); }}>
      <input id={side + '-file'} type="file" accept=".json,application/json" className="sr-only" disabled={disabled} onChange={e => { if (e.target.files[0]) onFile(side, e.target.files[0]); e.target.value = ''; }} aria-label={title} aria-invalid={invalid || undefined} aria-describedby={side + '-file-help'} />
      <span className="file-icon"><Icon name={file ? 'file' : 'upload'} size={22} /></span>
      <span className="file-copy"><strong>{file ? short(file.name, 50) : 'Choose a JSON file'}</strong><small id={side + '-file-help'}>{file ? bytes(file.size) + (invalid ? ' · Check this file' : ' · Ready to compare') : 'or drop it here · up to 2 MB'}</small></span>
      <span className="file-action">{file ? 'Replace' : 'Browse'}</span>
    </label>
    {file && <button type="button" className="remove-file" disabled={disabled} onClick={() => onRemove(side)} aria-label={'Remove ' + title.toLowerCase()}><Icon name="close" size={13} /> Remove</button>}
  </div>;
}

function EvidenceValue({ title, value, tone }) {
  const rendered = value.present ? displayJson(value.value) : null;
  return <section className={'evidence-value ' + tone}><div className="evidence-value-head"><span className="version-dot" />{title}<span>JSON</span></div>
    <div className="pointer-label">{value.present ? 'SOURCE POINTER' : 'EXPECTED POINTER'}</div>
    <code className="source-pointer">{short(value.pointer || value.expected_pointer || 'Not available', 500)}</code>
    {value.present ? <><pre>{rendered.text}</pre>{rendered.clipped && <p className="clipped">Preview limited to 20,000 characters. Export JSON for complete evidence.</p>}</> : <div className="absent"><Icon name="close" size={16} /><strong>Not declared</strong><p>This location is absent in this version.</p>{value.context_pointer && <code>Context: {short(value.context_pointer, 300)}</code>}</div>}
  </section>;
}

function Evidence({ finding, report, record }) {
  return <aside className="evidence-panel" id="panel-evidence" tabIndex={-1} aria-label="Evidence inspector"><div className="panel-heading"><div><Icon name="layers" /><h2>Evidence inspector</h2></div><span className="tiny-label">SOURCE</span></div>
    {finding ? <div className="evidence-scroll"><div className="evidence-intro"><Severity value={finding.severity} /><h3>{finding.title}</h3><p><span className={'method ' + finding.method?.toLowerCase()}>{finding.method}</span><code>{short(finding.path, 120)}</code></p></div>
      <div className="finding-meta"><span>Direction<strong>{finding.direction}</strong></span><span>Rule<strong>{finding.rule_id.replaceAll('_', ' ')}</strong></span></div>
      {finding.severity !== finding.policy_severity && <p className="review-note"><Icon name="info" size={16} />Unsupported semantics affect this finding. Its policy classification is {labels[finding.policy_severity]?.toLowerCase() || finding.policy_severity}; review the coverage.</p>}
      <EvidenceValue title="Before" tone="before" value={finding.before} /><EvidenceValue title="After" tone="after" value={finding.after} />
      <div className="evidence-foot"><Icon name="shield" size={16} /><span>Values come from the declared contracts. This report does not verify runtime behavior.</span></div>
      <ExplanationPanel key={(record?.id || 'unsaved') + finding.id} record={record} finding={finding} />
    </div> : <div className="evidence-empty"><span className="empty-icon"><Icon name="layers" size={27} /></span><h3>{report ? 'No finding selected' : 'The details behind the change'}</h3><p>{report ? 'Choose a finding to inspect its source values, or review the coverage below the results.' : 'Select a finding after comparing versions to see its exact before-and-after evidence.'}</p><div className="mini-diff"><span><i />before</span><span><i />after</span></div></div>}
  </aside>;
}

function Coverage({ report }) {
  const warnings = [
    ...(report.coverage.input_warnings?.old || []).map(w => ({ ...w, side: 'Old' })),
    ...(report.coverage.input_warnings?.new || []).map(w => ({ ...w, side: 'New' })),
    ...(report.coverage.analysis_warnings || []).map(w => ({ ...w, side: 'Comparison' })),
  ];
  return <details className={'coverage-panel ' + (warnings.length ? 'partial' : '')}><summary><Icon name={warnings.length ? 'alert' : 'shield'} size={17} /><span>{warnings.length ? 'Coverage needs review' : 'Policy & analysis coverage'}</span><span className="coverage-count">{warnings.length ? warnings.length + ' notices' : 'Supported subset'}</span><Icon name="chevron" size={14} /></summary>
    <div className="coverage-body"><p>This is a declared-contract review within implemented rules, not a full compatibility certification.</p><h4>Client assumptions</h4><ul>{report.policy_assumptions.map((text, i) => <li key={i}>{text}</li>)}</ul>
      {warnings.length > 0 && <><h4>Review notices</h4><div className="warning-list">{warnings.map((warning, i) => <div className="warning-item" key={i}><span>{warning.side}</span><strong>{warning.message}</strong>{warning.pointer && <code>{short(warning.pointer, 300)}</code>}{warning.operation && <code>{short(warning.operation.join(' '), 200)}</code>}{warning.keywords?.length > 0 && <small>{warning.keywords.join(', ')}</small>}</div>)}</div></>}
      <div className="policy-version">Engine {report.engine_version} · Policy {report.policy_version}</div>
    </div></details>;
}

export default function App() {
  const [view, setView] = useState('comparison');
  const [mobileTab, setMobileTab] = useState('input');
  const [oldFile, setOldFile] = useState(null), [newFile, setNewFile] = useState(null);
  const [example, setExample] = useState('breaking'), [save, setSave] = useState(true);
  const [busy, setBusy] = useState(''), [notice, setNotice] = useState(null), [invalidSide, setInvalidSide] = useState('');
  const [result, setResult] = useState(null), [record, setRecord] = useState(null), [selectedId, setSelectedId] = useState(null);
  const [filter, setFilter] = useState('all'), [search, setSearch] = useState(''), [endpoint, setEndpoint] = useState('all');
  const [history, setHistory] = useState([]), [cursor, setCursor] = useState(null), [historyLoading, setHistoryLoading] = useState(false), [historyError, setHistoryError] = useState('');
  const [database, setDatabase] = useState({ state: 'loading' });
  const [pendingDelete, setPendingDelete] = useState(null);
  const dialog = useRef(null), mounted = useRef(true), working = useRef(false), historyEpoch = useRef(0), actionEpoch = useRef(0), statusEpoch = useRef(0);
  const report = result?.comparison;

  useEffect(() => {
    mounted.current = true;
    refreshHistory();
    const match = /^#review=([a-f0-9-]{36})$/i.exec(window.location.hash);
    if (match) openSaved(match[1]);
    return () => { mounted.current = false; actionEpoch.current++; historyEpoch.current++; statusEpoch.current++; };
  }, []);

  useEffect(() => {
    if (pendingDelete && !dialog.current.open) dialog.current.showModal();
    else if (!pendingDelete && dialog.current.open) dialog.current.close();
  }, [pendingDelete]);

  async function refreshStatus() {
    const epoch = ++statusEpoch.current;
    try { const data = await api.status(); if (mounted.current && epoch === statusEpoch.current) setDatabase({ ...data, state: 'ready' }); }
    catch { if (mounted.current && epoch === statusEpoch.current) { setDatabase({ state: 'unavailable' }); setSave(false); } }
  }
  async function refreshHistory(append = false, nextCursor = null) {
    if (!append) refreshStatus();
    const epoch = ++historyEpoch.current; setHistoryLoading(true); setHistoryError('');
    try {
      const page = await api.history(append ? nextCursor : null);
      if (!Array.isArray(page.items)) throw new ApiError('History could not be read.');
      if (mounted.current && epoch === historyEpoch.current) {
        setHistory(previous => append ? [...previous, ...page.items.filter(item => !previous.some(p => p.id === item.id))] : page.items);
        setCursor(page.next_cursor);
      }
    } catch (error) { if (mounted.current && epoch === historyEpoch.current) setHistoryError(error.message); }
    finally { if (mounted.current && epoch === historyEpoch.current) setHistoryLoading(false); }
  }
  function begin(action) { if (working.current) return null; working.current = true; setBusy(action); setNotice(null); return ++actionEpoch.current; }
  function finish(epoch) { if (mounted.current && epoch === actionEpoch.current) { working.current = false; setBusy(''); } }
  function fail(error) { setNotice({ type: 'error', text: error.message || 'Something went wrong. Please try again.' }); }
  function clearReport() {
    setResult(null); setRecord(null); setSelectedId(null); setFilter('all'); setSearch(''); setEndpoint('all'); setInvalidSide('');
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
  }
  function newComparison() { if (working.current) return; actionEpoch.current++; clearReport(); setOldFile(null); setNewFile(null); setNotice(null); setView('comparison'); setMobileTab('input'); }
  function chooseFile(side, file) {
    if (working.current) return;
    if (!file.name.toLowerCase().endsWith('.json')) return fail(new ApiError('Choose a .json file for the ' + side + ' specification.'));
    if (file.size > 2 * 1024 * 1024) return fail(new ApiError('Each specification must be at most 2 MB.'));
    clearReport(); setNotice(null); (side === 'old' ? setOldFile : setNewFile)(file);
  }
  function removeFile(side) { if (working.current) return; clearReport(); (side === 'old' ? setOldFile : setNewFile)(null); }
  async function loadExample() {
    const epoch = begin('example'); if (epoch === null) return;
    try {
      const next = example === 'identical' ? 'orders-v1.json' : example === 'additive' ? 'orders-v2-compatible.json' : 'orders-v2-breaking.json';
      const [old, proposed] = await Promise.all([api.example('orders-v1.json'), api.example(next)]);
      if (mounted.current && epoch === actionEpoch.current) { clearReport(); setOldFile(old); setNewFile(proposed); setNotice({ type: 'success', text: 'Example loaded. Compare the versions when you’re ready.' }); }
    } catch (error) { if (mounted.current && epoch === actionEpoch.current) fail(error); }
    finally { finish(epoch); }
  }
  function accept(body) {
    const unpacked = unpack(body); setResult(unpacked.result); setRecord(unpacked.record); setSelectedId(unpacked.result.comparison.findings[0]?.id || null);
    setFilter('all'); setSearch(''); setEndpoint('all'); setInvalidSide(''); setView('comparison'); setMobileTab('findings');
    if (unpacked.record) window.history.replaceState(null, '', '#review=' + encodeURIComponent(unpacked.record.id));
  }
  async function run(event) {
    event.preventDefault(); if (!oldFile || !newFile) return;
    const epoch = begin('comparing'); if (epoch === null) return;
    clearReport();
    try {
      const body = await api.compare(oldFile, newFile, save && database.state === 'ready');
      if (mounted.current && epoch === actionEpoch.current) {
        accept(body); setNotice({ type: 'success', text: body.id ? (body.reused ? 'This comparison was already saved. Opened the existing review.' : 'Comparison complete and saved to history.') : 'Comparison complete. This review has not been saved.' });
        if (body.id) { refreshHistory(); }
      }
    } catch (error) { if (mounted.current && epoch === actionEpoch.current) { fail(error); setInvalidSide(error.side || ''); } }
    finally { finish(epoch); }
  }
  async function openSaved(id) {
    const epoch = begin('opening'); if (epoch === null) return;
    setView('comparison'); setResult(null); setRecord(null);
    try { const body = await api.detail(id); if (mounted.current && epoch === actionEpoch.current) { accept(body); setOldFile(null); setNewFile(null); } }
    catch (error) { if (mounted.current && epoch === actionEpoch.current) { if (error.status === 404) clearReport(); fail(error); refreshHistory(); } }
    finally { finish(epoch); }
  }
  async function download(format) {
    if (!record) return;
    const epoch = begin('exporting'); if (epoch === null) return;
    try { await api.download(record.id, format); }
    catch (error) { if (mounted.current && epoch === actionEpoch.current) { if (error.status === 404) { clearReport(); refreshHistory(); } fail(error); } }
    finally { finish(epoch); }
  }
  async function confirmDelete() {
    if (!pendingDelete) return;
    const target = pendingDelete.id, epoch = begin('deleting'); if (epoch === null) return;
    try {
      await api.remove(target);
      if (mounted.current && epoch === actionEpoch.current) {
        if (record?.id === target) { clearReport(); setOldFile(null); setNewFile(null); }
        setNotice({ type: 'success', text: 'Saved comparison deleted.' }); setPendingDelete(null); refreshHistory();
      }
    } catch (error) { if (mounted.current && epoch === actionEpoch.current) { if (error.status === 404) { if (record?.id === target) clearReport(); setPendingDelete(null); refreshHistory(); } fail(error); } }
    finally { finish(epoch); }
  }

  const endpoints = useMemo(() => [...new Set((report?.findings || []).map(f => f.method + ' ' + f.path))].sort(), [report]);
  const visible = useMemo(() => (report?.findings || []).filter(f => (filter === 'all' || f.severity === filter) && (endpoint === 'all' || f.method + ' ' + f.path === endpoint) && [f.title, f.path, f.rule_id, f.method].some(value => value.toLowerCase().includes(search.toLowerCase()))), [report, filter, endpoint, search]);
  const groups = useMemo(() => { const map = new Map(); for (const f of visible) { const key = f.method + ' ' + f.path; if (!map.has(key)) map.set(key, []); map.get(key).push(f); } return [...map.entries()]; }, [visible]);
  const selected = visible.find(f => f.id === selectedId) || visible[0] || null;
  const disabled = Boolean(busy);
  const title = result ? short(result.old.title, 100) : 'New comparison';
  function mobileKeys(event) {
    const keys = ['input', 'findings', 'evidence'];
    const index = keys.indexOf(mobileTab);
    const next = event.key === 'ArrowRight' ? (index + 1) % 3 : event.key === 'ArrowLeft' ? (index + 2) % 3 : event.key === 'Home' ? 0 : event.key === 'End' ? 2 : null;
    if (next !== null) { event.preventDefault(); setMobileTab(keys[next]); event.currentTarget.querySelectorAll('[role=tab]')[next].focus(); }
  }

  return <div className="app-shell"><a className="skip-link" href="#main">Skip to workspace</a>
    <aside className="sidebar"><a className="brand" href="/" aria-label="Relay home"><span className="brand-mark"><Icon name="arrows" size={24} /></span><span>relay<span className="brand-period">.</span><small>API CHANGE AUDITOR</small></span></a>
      <div className="workspace-switch"><span className="workspace-avatar"><Icon name="layers" size={18} /></span><span><strong>My workspace</strong><small>Personal contract reviews</small></span></div>
      <div className="nav-label">WORKSPACE</div><nav className="primary-nav" aria-label="Workspace"><button className={view === 'comparison' ? 'active' : ''} disabled={disabled} onClick={() => setView('comparison')}><Icon name="arrows" />Compare contracts<span className="nav-indicator" /></button><button className={view === 'history' ? 'active' : ''} disabled={disabled} onClick={() => { setView('history'); refreshHistory(); }}><Icon name="clock" />Saved reviews{database.state === 'ready' && <span className="nav-count">{database.saved_comparisons}</span>}</button></nav>
      <div className="recent-heading"><span className="nav-label">RECENT REVIEWS</span><button className="icon-button" onClick={() => refreshHistory()} disabled={historyLoading || disabled} aria-label="Refresh history"><Icon name="refresh" size={14} /></button></div>
      <div className="recent-list">{history.slice(0, 6).map(item => <button key={item.id} disabled={disabled} className={'recent-item ' + (record?.id === item.id ? 'selected' : '')} onClick={() => openSaved(item.id)}><Icon name="file" size={16} /><span><strong>{short(item.old.title, 28)}</strong><small>{short(item.old.version, 12)} → {short(item.new.version, 12)}</small></span><i className={item.summary.breaking ? 'red-dot' : item.summary.needs_review ? 'amber-dot' : 'green-dot'} /></button>)}{!history.length && <p className="recent-empty">{historyLoading ? 'Loading your reviews…' : historyError ? 'History is unavailable. Retry with the refresh button.' : 'Saved comparisons will appear here.'}</p>}</div>
      <div className="sidebar-note"><span><Icon name="shield" size={17} />Rule-based analysis</span><p>Inspect the contract evidence behind each finding. Request optional AI migration guidance in the inspector.</p></div>
      <div className="sidebar-footer"><Icon name="monitor" size={20} /><span><strong>Local workspace</strong><small>{database.state === 'ready' ? 'History saved on this device' : 'Stateless comparison available'}</small></span><i className={database.state === 'ready' ? 'green-dot' : 'amber-dot'} /></div>
    </aside>
    <div className="app-body"><header className="topbar"><div className="breadcrumbs"><Icon name="grid" size={16} /><span>Workspace</span><Icon name="chevron" size={13} /><strong>{view === 'history' ? 'Saved reviews' : 'Contract review'}</strong></div><div className="topbar-actions"><span className={'status-pill ' + database.state}><i />{database.state === 'ready' ? 'History ready' : database.state === 'loading' ? 'Checking history' : 'History unavailable'}</span><button className="button small secondary" disabled={disabled} onClick={newComparison}><Icon name="plus" size={15} />New comparison</button><button className="mobile-history icon-button" disabled={disabled} onClick={() => { setView(view === 'history' ? 'comparison' : 'history'); refreshHistory(); }} aria-label={view === 'history' ? 'Return to comparison' : 'Open saved reviews'}><Icon name={view === 'history' ? 'arrows' : 'clock'} /></button></div></header>
      <main id="main" className={'workspace ' + (view === 'history' ? 'history-view' : '')}>
        {notice && <div className={'notice ' + notice.type} role={notice.type === 'error' ? 'alert' : 'status'}><Icon name={notice.type === 'error' ? 'alert' : 'check'} size={17} /><span>{notice.text}</span><button className="icon-button" onClick={() => setNotice(null)} aria-label="Dismiss message"><Icon name="close" size={15} /></button></div>}
        {view === 'history' ? <section className="history-page"><div className="page-heading"><div><span className="eyebrow">YOUR WORKSPACE</span><h1>Saved reviews</h1><p>Pick up a comparison, inspect its evidence, or export a report.</p></div><button className="button secondary" disabled={historyLoading || disabled} onClick={() => refreshHistory()}><Icon name="refresh" size={16} />Refresh</button></div>
          {historyError && <div className="inline-error" role="alert">History is unavailable. Try refreshing; you can still compare without saving.</div>}
          {history.length ? <div className="history-cards">{history.map(item => <article className="history-card" key={item.id}><span className="history-file"><Icon name="file" size={23} /></span><div className="history-card-info"><h2>{short(item.old.title, 90)}</h2><p><code>{short(item.old.version, 24)}</code><span>→</span><code>{short(item.new.version, 24)}</code><span className="history-date">{date(item.created_at)}</span></p><div className="history-card-badges"><span>{item.summary.total_findings} findings</span>{item.summary.breaking > 0 && <span className="history-breaking">{item.summary.breaking} breaking</span>}{item.coverage_status === 'partial' && <span>Coverage needs review</span>}</div></div><div className="history-card-actions"><button className="button secondary small" disabled={disabled} onClick={() => openSaved(item.id)}>Open review<Icon name="chevron" size={14} /></button><button className="icon-button danger-text" disabled={disabled} onClick={() => setPendingDelete(item)} aria-label={'Delete review ' + short(item.old.title, 80)}><Icon name="trash" size={17} /></button></div></article>)}</div> : !historyLoading && !historyError && <div className="history-empty"><span className="empty-icon"><Icon name="clock" size={30} /></span><h2>A place for your reviews</h2><p>Save a comparison to return to its findings and source evidence.</p><button className="button primary" onClick={newComparison}>Compare contracts<Icon name="arrows" size={16} /></button></div>}
          {historyLoading && <p className="loading-line" role="status"><Spinner />Loading saved reviews…</p>}{cursor && <button className="button secondary load-more" disabled={historyLoading || disabled} onClick={() => refreshHistory(true, cursor)}>Load more reviews</button>}
        </section> : <>
          <div className="page-heading"><div><span className="eyebrow">CONTRACT REVIEW</span><h1>Review an API change.</h1><p>Compare two OpenAPI versions and inspect their impact on existing clients.</p></div><span className="format-tag"><Icon name="file" size={15} />OpenAPI 3.0 & 3.1</span></div>
          <div className="mobile-tabs" role="tablist" aria-label="Comparison panels" onKeyDown={mobileKeys}>{[['input', 'Specifications'], ['findings', 'Findings'], ['evidence', 'Evidence']].map(([key, label]) => <button role="tab" id={"tab-" + key} aria-controls={"panel-" + key} tabIndex={mobileTab === key ? 0 : -1} aria-selected={mobileTab === key} key={key} onClick={() => setMobileTab(key)}>{label}{key === 'findings' && report && <span>{report.summary.total_findings}</span>}</button>)}</div>
          <div className={'review-layout tab-' + mobileTab}><div className="comparison-column">
            <section className="input-panel" id="panel-input"><div className="panel-heading"><div><span className="step-number">01</span><h2>Choose your specifications</h2></div><span className="tiny-label">OLD → NEW</span></div>
              <form onSubmit={run}><div className="file-pair"><FileSlot side="old" file={oldFile} disabled={disabled} invalid={invalidSide === 'old'} onFile={chooseFile} onRemove={removeFile} onError={text => fail(new ApiError(text))} /><span className="pair-arrow"><Icon name="arrows" size={20} /></span><FileSlot side="new" file={newFile} disabled={disabled} invalid={invalidSide === 'new'} onFile={chooseFile} onRemove={removeFile} onError={text => fail(new ApiError(text))} /></div>
                <div className="input-actions"><label className="save-option"><input type="checkbox" checked={save} onChange={e => setSave(e.target.checked)} disabled={disabled || database.state !== 'ready'} /><span>Save to history</span></label><button className="button primary" type="submit" disabled={disabled || !oldFile || !newFile || (save && database.state === 'loading')}>{busy === 'comparing' ? <><Spinner />Comparing…</> : <>Compare specifications<Icon name="arrows" size={17} /></>}</button></div>
              </form>
              <div className="example-bar"><span><Icon name="info" size={15} />Want to explore first?</span><select value={example} onChange={e => setExample(e.target.value)} disabled={disabled} aria-label="Example comparison"><option value="breaking">Breaking changes</option><option value="additive">Additive changes</option><option value="identical">Identical specifications</option></select><button type="button" className="text-button" disabled={disabled} onClick={loadExample}>{busy === 'example' ? 'Loading…' : 'Load example'}<Icon name="chevron" size={13} /></button></div>
              {database.state === 'unavailable' && <p className="storage-note">History is unavailable. You can still compare without saving. <button className="text-button" onClick={() => refreshHistory()}>Retry</button></p>}
            </section>
            <section className="results-panel" id="panel-findings" aria-label="Comparison results"><div className="panel-heading"><div><span className="step-number">02</span><h2>Review the changes</h2>{report && <span className="count-badge">{report.summary.total_findings}</span>}</div>{record ? <span className="saved-indicator"><Icon name="check" size={13} />Saved</span> : report ? <span className="tiny-label">UNSAVED REVIEW</span> : <span className="tiny-label">RESULTS</span>}</div>
              {busy === 'comparing' || busy === 'opening' ? <div className="analysis-loading" role="status"><Spinner /><h3>{busy === 'opening' ? 'Opening your saved review' : 'Reviewing the declared contracts'}</h3><p>{busy === 'opening' ? 'Loading findings and their saved evidence.' : 'Validating the specifications and comparing supported compatibility rules.'}</p></div> : report ? <>
                <div className="report-title"><div><h3>{title}</h3><p><code>{short(result.old.api_version, 30)}</code><Icon name="arrows" size={14} /><code>{short(result.new.api_version, 30)}</code><span>{record ? date(record.created_at) : 'Current comparison'}</span></p></div>{record && <div className="export-actions"><button className="button small secondary" disabled={disabled} onClick={() => download('json')} aria-label="Export JSON"><Icon name="download" size={14} />JSON</button><button className="button small secondary" disabled={disabled} onClick={() => download('markdown')} aria-label="Export Markdown">MD</button><button className="icon-button danger-text" disabled={disabled} onClick={() => setPendingDelete(record)} aria-label="Delete current review"><Icon name="trash" size={15} /></button></div>}</div>
                <div className="summary-grid">{SEVERITIES.map(key => <button className={'summary-card ' + key + (filter === key ? ' chosen' : '')} key={key} onClick={() => setFilter(filter === key ? 'all' : key)} aria-label={'Filter ' + labels[key].toLowerCase()}><span><i />{labels[key]}</span><strong>{report.summary[key]}</strong><small>{key === 'breaking' ? 'Declared incompatibilities' : key === 'potentially_breaking' ? 'Client-dependent impact' : key === 'needs_review' ? 'Manual interpretation' : 'Policy-compatible changes'}</small></button>)}</div>
                <div className={'verdict ' + (report.verdict === 'breaking_changes_detected' ? 'has-breaking' : '')}><Icon name={report.verdict === 'breaking_changes_detected' ? 'alert' : 'info'} size={16} /><span>{report.verdict === 'breaking_changes_detected' ? 'Breaking changes detected under the declared-client policy.' : report.verdict === 'review_required' ? 'Manual review is needed before drawing a compatibility conclusion.' : 'No breaking changes detected within the supported rules.'}</span></div>
                <div className="result-tools"><label className="search-box"><Icon name="search" size={15} /><input type="search" placeholder="Search endpoint, rule, or finding…" aria-label="Search findings" value={search} onChange={e => setSearch(e.target.value)} /></label><select aria-label="Filter endpoint" value={endpoint} onChange={e => setEndpoint(e.target.value)}><option value="all">All endpoints</option>{endpoints.map(key => <option value={key} key={key}>{short(key, 80)}</option>)}</select></div>
                <div className="filter-tabs" aria-label="Filter severity"><button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All changes <span>{report.summary.total_findings}</span></button>{SEVERITIES.map(key => <button key={key} className={filter === key ? 'active' : ''} onClick={() => setFilter(key)}>{labels[key]}</button>)}</div>
                <div className="finding-groups">{groups.map(([key, findings]) => <section className="endpoint-group" key={key}><div className="endpoint-heading"><span className={'method ' + findings[0].method.toLowerCase()}>{findings[0].method}</span><code>{short(findings[0].path, 130)}</code><span>{findings.length} {findings.length === 1 ? 'change' : 'changes'}</span></div>{findings.map(finding => <button className={'finding-row ' + (selected?.id === finding.id ? 'selected' : '')} key={finding.id} onClick={() => { setSelectedId(finding.id); setMobileTab('evidence'); if (window.matchMedia('(max-width:760px)').matches) requestAnimationFrame(() => document.getElementById('panel-evidence')?.focus()); }} aria-pressed={selected?.id === finding.id}><span className={'finding-glyph ' + finding.severity}><Icon name={finding.severity === 'breaking' ? 'alert' : finding.severity === 'informational' ? 'info' : 'search'} size={17} /></span><span className="finding-copy"><strong>{finding.title}</strong><small>{short(finding.location.join(' / ') || 'Operation declaration', 110)}</small></span><Severity value={finding.severity} /><Icon name="chevron" size={14} /></button>)}</section>)}</div>
                {!visible.length && <div className="no-findings"><Icon name={report.findings.length ? 'search' : 'check'} size={25} /><h3>{report.findings.length ? 'No matching findings' : 'No changes in the implemented subset'}</h3><p>{report.findings.length ? 'Try another severity, endpoint, or search term.' : 'Review the policy and coverage before interpreting this result.'}</p>{report.findings.length > 0 && <button className="text-button" onClick={() => { setFilter('all'); setSearch(''); setEndpoint('all'); }}>Clear filters</button>}</div>}
                <Coverage report={report} />
                {!record && <p className="unsaved-note"><Icon name="info" size={15} />To save and export this review, enable Save to history and compare the selected files again.</p>}
              </> : <div className="results-empty"><div className="empty-flow"><span><Icon name="file" size={20} /><small>old.json</small></span><i /><span className="flow-center"><Icon name="arrows" size={25} /></span><i /><span><Icon name="file" size={20} /><small>new.json</small></span></div><h3>Your next release, with more context.</h3><p>Add two specifications above or load an example.<br />Your findings and their evidence will appear here.</p><div className="empty-benefits"><span><Icon name="check" size={13} />Direction-aware rules</span><span><Icon name="check" size={13} />Source-level evidence</span></div></div>}
            </section>
          </div><Evidence finding={selected} report={report} record={record} /></div>
        </>}
        <footer className="workspace-footer"><span><Icon name="shield" size={13} />Your contracts stay in this local workspace.</span><span>Relay · Declared-contract review</span></footer>
      </main>
    </div>
    <dialog ref={dialog} className="delete-dialog" aria-labelledby="delete-title" onCancel={e => { if (busy === 'deleting') e.preventDefault(); else setPendingDelete(null); }} onClose={() => setPendingDelete(null)}><form onSubmit={e => { e.preventDefault(); confirmDelete(); }}><span className="dialog-icon"><Icon name="trash" size={23} /></span><h2 id="delete-title">Delete this saved review?</h2><p>{short(pendingDelete?.old?.title || 'This comparison', 100)}</p><p>Its saved result and evidence will be removed from history. Reports you already downloaded will remain.</p><div className="dialog-actions"><button className="button secondary" type="button" disabled={busy === 'deleting'} onClick={() => setPendingDelete(null)}>Cancel</button><button className="button danger" type="submit" disabled={busy === 'deleting'}>{busy === 'deleting' ? <><Spinner />Deleting…</> : 'Delete review'}</button></div></form></dialog>
  </div>;
}
