import { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function Batches() {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type }); setTimeout(() => setToast(null), 3000);
  };

  const load = async () => {
    setLoading(true);
    api.batches().then(d => setBatches(d.results ?? d)).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const lock = async (id) => {
    try {
      const r = await api.lockBatch(id);
      showToast(`Locked ${r.locked} records in batch #${r.batch_id}`);
      load();
    } catch (e) {
      try { showToast(JSON.parse(e.message)?.error || e.message, 'error'); }
      catch { showToast(e.message, 'error'); }
    }
  };

  return (
    <>
      <div className="page-header">
        <span className="page-title">Batch History</span>
        <span className="page-subtitle">— {batches.length} batches ingested</span>
        <div className="header-actions">
          <button className="btn btn-secondary btn-sm" onClick={load}>↻ Refresh</button>
        </div>
      </div>
      <div className="page-body">
        {loading
          ? <div className="empty-state"><div className="spinner" style={{ margin: 'auto' }} /></div>
          : (
            <div className="card" style={{ padding: 0 }}>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>#</th><th>Source</th><th>File</th><th>Uploaded By</th><th>Date</th>
                      <th>Rows</th><th>Errors</th><th>Pending</th><th>Flagged</th><th>Approved</th>
                      <th>tCO₂e</th><th>Status</th><th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batches.map(b => (
                      <tr key={b.id}>
                        <td className="mono">#{b.id}</td>
                        <td><SourceBadge s={b.source_type} /></td>
                        <td className="mono" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{b.filename}</td>
                        <td>{b.uploaded_by || '—'}</td>
                        <td className="mono">{b.uploaded_at?.slice(0, 10)}</td>
                        <td>{b.row_count}</td>
                        <td>{b.error_count > 0 ? <span className="badge badge-flagged">{b.error_count}</span> : '0'}</td>
                        <td><span className="badge badge-pending">{b.pending_count}</span></td>
                        <td><span className="badge badge-flagged">{b.flagged_count}</span></td>
                        <td><span className="badge badge-approved">{b.approved_count}</span></td>
                        <td className="mono">{(b.total_co2e_kg / 1000).toFixed(2)}t</td>
                        <td><StatusBadge s={b.status} /></td>
                        <td>
                          {b.status === 'COMPLETE' && b.pending_count === 0 && b.flagged_count === 0 && (
                            <button className="btn btn-sm" style={{ background: 'var(--accent-blue-dim)', color: 'var(--accent-blue)' }}
                              onClick={() => lock(b.id)}>🔒 Lock</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        }
      </div>
      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}
    </>
  );
}

function SourceBadge({ s }) {
  const cls = { SAP: 'badge-sap', UTILITY: 'badge-utility', TRAVEL: 'badge-travel' }[s] || '';
  return <span className={`badge ${cls}`}>{s}</span>;
}
function StatusBadge({ s }) {
  const map = { COMPLETE: 'approved', FAILED: 'flagged', PROCESSING: 'pending' };
  return <span className={`badge badge-${map[s] || 'pending'}`}>{s}</span>;
}
