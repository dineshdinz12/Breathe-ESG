import { useEffect, useState, useCallback } from 'react';
import { api } from '../api/client';

const STATUS_OPTS = ['', 'PENDING', 'APPROVED', 'FLAGGED', 'REJECTED'];
const SOURCE_OPTS = ['', 'SAP', 'UTILITY', 'TRAVEL'];
const SCOPE_OPTS  = ['', '1', '2', '3'];

export default function Review() {
  const [records, setRecords] = useState([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: 'PENDING', source_type: '', scope: '', search: '', page: 1 });
  const [toast, setToast] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [reasonModal, setReasonModal] = useState(null); // { id, action }
  const [reasonText, setReasonText] = useState('');

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.status) params.status = filters.status;
      if (filters.source_type) params.source_type = filters.source_type;
      if (filters.scope) params.scope = filters.scope;
      if (filters.search) params.search = filters.search;
      if (filters.page > 1) params.page = filters.page;
      const data = await api.records(params);
      setRecords(data.results ?? data);
      setCount(data.count ?? (data.results ?? data).length);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const doAction = async (id, action, reason = '') => {
    try {
      if (action === 'approve') await api.approve(id);
      else if (action === 'flag') await api.flag(id, reason);
      else if (action === 'reject') await api.reject(id, reason);
      showToast(`Record ${action}d successfully`);
      load();
    } catch (e) { showToast('Action failed: ' + e.message, 'error'); }
  };

  const openReasonModal = (id, action) => {
    setReasonModal({ id, action }); setReasonText('');
  };
  const submitReason = async () => {
    if (!reasonModal) return;
    await doAction(reasonModal.id, reasonModal.action, reasonText);
    setReasonModal(null);
  };

  const setFilter = (k, v) => setFilters(f => ({ ...f, [k]: v, page: 1 }));

  return (
    <>
      <div className="page-header">
        <span className="page-title">Review Queue</span>
        <span className="page-subtitle">— {count} records</span>
        <div className="header-actions">
          <button className="btn btn-secondary btn-sm" onClick={load}>↻ Refresh</button>
        </div>
      </div>
      <div className="page-body">
        {/* Filters */}
        <div className="filter-bar">
          <input className="input" placeholder="Search ID, category, facility…" value={filters.search}
            onChange={e => setFilter('search', e.target.value)} style={{ width: 260 }} />
          <select className="select" value={filters.status} onChange={e => setFilter('status', e.target.value)}>
            <option value="">All statuses</option>
            {STATUS_OPTS.slice(1).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="select" value={filters.source_type} onChange={e => setFilter('source_type', e.target.value)}>
            <option value="">All sources</option>
            {SOURCE_OPTS.slice(1).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="select" value={filters.scope} onChange={e => setFilter('scope', e.target.value)}>
            <option value="">All scopes</option>
            {SCOPE_OPTS.slice(1).map(s => <option key={s} value={s}>Scope {s}</option>)}
          </select>
        </div>

        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
            {loading
              ? <div className="empty-state"><div className="spinner" style={{ margin: 'auto' }} /></div>
              : records.length === 0
                ? <div className="empty-state">No records match your filters</div>
                : (
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th><th>Source</th><th>Scope</th><th>Category</th>
                        <th>Date</th><th>Qty (normalized)</th><th>kgCO₂e</th>
                        <th>Facility</th><th>Status</th><th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map(r => (
                        <>
                          <tr key={r.id} className={r.is_flagged_auto ? 'flagged-row' : ''} onClick={() => setExpandedId(expandedId === r.id ? null : r.id)} style={{ cursor: 'pointer' }}>
                            <td className="mono">#{r.id}</td>
                            <td><SourceBadge s={r.source_type} /></td>
                            <td><ScopeBadge s={r.scope} /></td>
                            <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.category_code}</td>
                            <td className="mono">{r.activity_date || '—'}</td>
                            <td className="mono">{Number(r.quantity_normalized).toFixed(2)} {r.unit_canonical}</td>
                            <td className="mono" style={{ fontWeight: 600 }}>{Number(r.co2e_kg).toFixed(2)}</td>
                            <td style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.facility_or_cc || '—'}</td>
                            <td><StatusBadge s={r.status} /></td>
                            <td onClick={e => e.stopPropagation()}>
                              {!r.is_locked && r.status !== 'APPROVED' && (
                                <button className="btn btn-sm" style={{ background: 'var(--accent-green-dim)', color: 'var(--accent-green)', marginRight: 4 }}
                                  onClick={() => doAction(r.id, 'approve')}>✓</button>
                              )}
                              {!r.is_locked && r.status !== 'FLAGGED' && (
                                <button className="btn btn-sm" style={{ background: 'var(--accent-red-dim)', color: 'var(--accent-red)', marginRight: 4 }}
                                  onClick={() => openReasonModal(r.id, 'flag')}>⚑</button>
                              )}
                              {!r.is_locked && r.status !== 'REJECTED' && (
                                <button className="btn btn-sm btn-ghost"
                                  onClick={() => openReasonModal(r.id, 'reject')}>✕</button>
                              )}
                            </td>
                          </tr>
                          {expandedId === r.id && (
                            <tr key={`exp-${r.id}`}>
                              <td colSpan={10} style={{ padding: 0 }}>
                                <ExpandedRow record={r} onRefresh={load} showToast={showToast} />
                              </td>
                            </tr>
                          )}
                        </>
                      ))}
                    </tbody>
                  </table>
                )
            }
          </div>
        </div>

        {/* Pagination */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
          <button className="btn btn-secondary btn-sm" disabled={filters.page <= 1}
            onClick={() => setFilter('page', filters.page - 1)}>← Prev</button>
          <span style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: '30px' }}>Page {filters.page}</span>
          <button className="btn btn-secondary btn-sm"
            onClick={() => setFilter('page', filters.page + 1)}>Next →</button>
        </div>
      </div>

      {/* Reason modal */}
      {reasonModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div className="card" style={{ width: 380 }}>
            <div style={{ fontWeight: 600, marginBottom: 12 }}>
              {reasonModal.action === 'flag' ? '🚩 Flag Record' : '✕ Reject Record'}
            </div>
            <textarea className="input" rows={3} style={{ width: '100%', resize: 'none' }}
              placeholder="Reason (optional)…" value={reasonText} onChange={e => setReasonText(e.target.value)} />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button className="btn btn-primary" onClick={submitReason}>Confirm</button>
              <button className="btn btn-secondary" onClick={() => setReasonModal(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}
    </>
  );
}

function ExpandedRow({ record: r, onRefresh, showToast }) {
  const [editQty, setEditQty] = useState(r.quantity_normalized);
  const [editNote, setEditNote] = useState(r.review_note);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.patchRecord(r.id, { quantity_normalized: editQty, review_note: editNote });
      showToast('Record updated');
      onRefresh();
    } catch (e) { showToast('Save failed: ' + e.message, 'error'); }
    finally { setSaving(false); }
  };

  return (
    <div style={{ background: 'var(--bg-elevated)', padding: '16px 24px', borderTop: '1px solid var(--border)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Raw ID</div>
          <div className="mono" style={{ fontSize: 12 }}>{r.raw_id}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Raw Date</div>
          <div className="mono" style={{ fontSize: 12 }}>{r.raw_date_str}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Raw Qty / Unit</div>
          <div className="mono" style={{ fontSize: 12 }}>{r.raw_quantity_str} {r.raw_unit}</div>
        </div>
        {r.origin_iata && (
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Flight Route</div>
            <div className="mono" style={{ fontSize: 12 }}>{r.origin_iata} → {r.destination_iata} ({r.distance_km} km, {r.cabin_class})</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Emission Factor</div>
          <div style={{ fontSize: 12 }}>{r.emission_factor ? `${r.emission_factor.co2e_per_unit} kg/${r.emission_factor.unit} (${r.emission_factor.source_name})` : '—'}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Reviewed By</div>
          <div style={{ fontSize: 12 }}>{r.reviewed_by || '—'} {r.reviewed_at ? `@ ${r.reviewed_at.slice(0,10)}` : ''}</div>
        </div>
      </div>

      {r.is_flagged_auto && r.flag_reason && (
        <div className="flag-banner">⚠ {r.flag_reason}</div>
      )}

      {!r.is_locked && (
        <div style={{ display: 'flex', gap: 10, marginTop: 12, alignItems: 'flex-end' }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Override Quantity</div>
            <input className="input" type="number" step="0.001" value={editQty}
              onChange={e => setEditQty(e.target.value)} style={{ width: 140 }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Review Note</div>
            <input className="input" value={editNote} onChange={e => setEditNote(e.target.value)}
              placeholder="Add note…" style={{ width: '100%' }} />
          </div>
          <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>
            {saving ? '…' : 'Save'}
          </button>
        </div>
      )}

      {r.edits?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>Audit Log</div>
          {r.edits.map(e => (
            <div key={e.id} style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2, fontFamily: 'var(--font-mono)' }}>
              {e.edited_at.slice(0,16)} · {e.edited_by} changed {e.field_changed}: "{e.old_value}" → "{e.new_value}" {e.reason ? `(${e.reason})` : ''}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SourceBadge({ s }) {
  const cls = { SAP: 'badge-sap', UTILITY: 'badge-utility', TRAVEL: 'badge-travel' }[s] || '';
  return <span className={`badge ${cls}`}>{s}</span>;
}
function ScopeBadge({ s }) {
  const cls = { 1: 'badge-scope1', 2: 'badge-scope2', 3: 'badge-scope3' }[s] || '';
  return <span className={`badge ${cls}`}>S{s}</span>;
}
function StatusBadge({ s }) {
  const cls = { PENDING: 'badge-pending', APPROVED: 'badge-approved', FLAGGED: 'badge-flagged', REJECTED: 'badge-rejected' }[s] || '';
  return <span className={`badge ${cls}`}>{s}</span>;
}
