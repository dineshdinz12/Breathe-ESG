import { useState, useRef } from 'react';
import { api } from '../api/client';

const SOURCES = [
  {
    key: 'SAP',
    label: 'SAP Fuel & Procurement',
    desc: 'Tab-delimited flat file from SE16N/SQVI export. Joins EKKO, EKPO, MARA tables. Scope 1 direct combustion.',
    accept: '.tsv,.csv,.txt',
    fields: 'EBELN, EBELP, MATNR, MAKTX, WERKS, BEDAT, MENGE, MEINS, NETPR, WAERS',
    scope: 1,
    color: '#0d9488',
    scopeColor: 'scope1',
  },
  {
    key: 'UTILITY',
    label: 'Utility / Electricity',
    desc: 'Monthly billing CSV from utility portal (Green Button-style). Scope 2 purchased electricity.',
    accept: '.csv',
    fields: 'ACCOUNT_ID, METER_ID, SERVICE_ADDRESS, BILLING_PERIOD_START, BILLING_PERIOD_END, CONSUMPTION_KWH',
    scope: 2,
    color: '#2563eb',
    scopeColor: 'scope2',
  },
  {
    key: 'TRAVEL',
    label: 'Corporate Travel',
    desc: 'Concur-style CSV export with flights (IATA codes), hotels (nights), and ground transport. Scope 3 Cat 6.',
    accept: '.csv',
    fields: 'EXPENSE_ID, EXPENSE_TYPE, ORIGIN, DESTINATION, DEPARTURE_DATE, NIGHTS, DISTANCE_KM, CABIN_CLASS',
    scope: 3,
    color: '#7c3aed',
    scopeColor: 'scope3',
  },
];

/* Simple SVG icons — no emojis */
function IconFactory({ fill }) {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={fill} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3h18v4H3z" /><path d="M3 10h18v4H3z" /><path d="M3 17h18v4H3z" />
    </svg>
  );
}
function IconBolt({ fill }) {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={fill} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}
function IconPlane({ fill }) {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={fill} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.8 19.2 16 11l3.5-3.5C21 6 21 4 19 4c-1 0-1.5.5-3.5 1.5L7 3 4.5 5.5 11 9 8 12H5l-1 2 4 2 2 4 2-1v-3l3-3z" />
    </svg>
  );
}

function SourceIcon({ srcKey, color }) {
  if (srcKey === 'SAP')     return <IconFactory fill={color} />;
  if (srcKey === 'UTILITY') return <IconBolt    fill={color} />;
  if (srcKey === 'TRAVEL')  return <IconPlane   fill={color} />;
  return null;
}

export default function Upload() {
  const [activeTab, setActiveTab] = useState('SAP');
  const [dragOver, setDragOver]   = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState(null);
  const fileRef = useRef();
  const src = SOURCES.find(s => s.key === activeTab);

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true); setResult(null); setError(null);
    try {
      const data = await api.ingest(file, activeTab);
      setResult(data);
    } catch (e) {
      try { setError(JSON.parse(e.message)?.error || e.message); }
      catch { setError(e.message); }
    } finally { setUploading(false); }
  };

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  return (
    <>
      <div className="page-header">
        <span className="page-title">Upload Data</span>
        <span className="page-subtitle">— Ingest new emissions data from source files</span>
      </div>
      <div className="page-body">
        <div className="upload-tabs">
          {SOURCES.map(s => (
            <button key={s.key} id={`tab-${s.key.toLowerCase()}`}
              className={`upload-tab${activeTab === s.key ? ' active' : ''}`}
              style={activeTab === s.key ? { color: s.color, borderBottomColor: s.color } : {}}
              onClick={() => { setActiveTab(s.key); setResult(null); setError(null); }}>
              {s.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20 }}>
          {/* Drop zone */}
          <div>
            <div
              className={`drop-zone${dragOver ? ' drag-over' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
              style={dragOver ? { borderColor: src.color } : {}}
            >
              <div style={{ marginBottom: 14, display: 'flex', justifyContent: 'center' }}>
                <div style={{
                  width: 56, height: 56, borderRadius: 14,
                  background: `${src.color}15`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <SourceIcon srcKey={src.key} color={src.color} />
                </div>
              </div>
              <div className="drop-zone-title">Drop your {src.label} file here</div>
              <div className="drop-zone-hint" style={{ marginBottom: 16 }}>or click to browse · {src.accept}</div>
              <button className="btn btn-secondary" onClick={e => { e.stopPropagation(); fileRef.current?.click(); }}>
                Browse File
              </button>
              <input ref={fileRef} type="file" accept={src.accept} onChange={e => handleFile(e.target.files?.[0])} />
            </div>

            {uploading && (
              <div className="card" style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
                <div className="spinner" />
                <span style={{ color: 'var(--text-secondary)' }}>Parsing and ingesting rows…</span>
              </div>
            )}

            {result && (
              <div className="card" style={{ marginTop: 16, borderLeft: `3px solid var(--accent-green)` }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--accent-green)', marginBottom: 12 }}>
                  Ingestion Complete
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                  <Stat label="Rows Ingested"  value={result.row_count} />
                  <Stat label="Errors Skipped" value={result.error_count} warn={result.error_count > 0} />
                  <Stat label="Status"         value={result.status} />
                </div>
                {result.error_count > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>Parse errors (first 3):</div>
                    {(result.error_log || []).slice(0, 3).map((e, i) => (
                      <div key={i} className="flag-banner" style={{ marginBottom: 4 }}>
                        Line {e.line}: {e.error}
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ marginTop: 14, fontSize: 13, color: 'var(--text-secondary)' }}>
                  Batch ID: <span className="mono">#{result.id}</span> · Head to the{' '}
                  <a href="/review" style={{ color: 'var(--accent-green)', fontWeight: 500 }}>Review Queue</a> to process records.
                </div>
              </div>
            )}

            {error && (
              <div className="card" style={{ marginTop: 16, borderLeft: '3px solid var(--accent-red)' }}>
                <div style={{ color: 'var(--accent-red)', fontWeight: 600, marginBottom: 8 }}>Upload Failed</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{error}</div>
              </div>
            )}
          </div>

          {/* Source info panel */}
          <div className="card" style={{ height: 'fit-content' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: `${src.color}15`,
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              }}>
                <SourceIcon srcKey={src.key} color={src.color} />
              </div>
              <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{src.label}</div>
            </div>

            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>{src.desc}</p>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 6 }}>Expected columns</div>
              <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.9 }}>{src.fields}</div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 6 }}>GHG Scope</div>
              <span className={`badge badge-${src.scopeColor}`}>Scope {src.scope}</span>
            </div>

            <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.7, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
              The parser auto-detects delimiters, normalizes units, maps to emission factors (DEFRA 2023), and flags suspicious rows for analyst review.
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function Stat({ label, value, warn }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: warn ? 'var(--accent-amber)' : 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}
