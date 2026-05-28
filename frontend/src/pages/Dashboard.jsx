import { useEffect, useState } from 'react';
import { api } from '../api/client';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, CartesianGrid,
} from 'recharts';

const SCOPE_COLORS = { 1: '#ea580c', 2: '#2563eb', 3: '#7c3aed' };
const SOURCE_COLORS = { SAP: '#0d9488', UTILITY: '#2563eb', TRAVEL: '#7c3aed' };
const fmt  = (n) => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : n?.toFixed(1) ?? '—';
const fmtT = (n) => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : n?.toFixed(0) ?? '—';

export default function Dashboard() {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.dashboard().then(setData).catch(console.error).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page-body"><div className="empty-state"><div className="spinner" style={{ margin: 'auto' }} /></div></div>;
  if (!data)   return <div className="page-body"><div className="empty-state">Failed to load dashboard</div></div>;

  const scopeData = [
    { name: 'Scope 1', value: +(data.scope_1_co2e_kg / 1000).toFixed(2), count: data.scope_1_count },
    { name: 'Scope 2', value: +(data.scope_2_co2e_kg / 1000).toFixed(2), count: data.scope_2_count },
    { name: 'Scope 3', value: +(data.scope_3_co2e_kg / 1000).toFixed(2), count: data.scope_3_count },
  ];

  const sourceData = data.source_breakdown.map(s => ({
    name: s.source,
    tCO2e: +(s.co2e_kg / 1000).toFixed(2),
    count: s.count,
    pct: data.total_co2e_t > 0 ? ((s.co2e_kg / 1000) / data.total_co2e_t * 100).toFixed(1) : 0,
  }));
  const maxSource = Math.max(...sourceData.map(s => s.tCO2e));

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ background: '#fff', border: '1px solid #e2e5ea', borderRadius: 8, padding: '10px 14px', fontSize: 12, boxShadow: '0 4px 12px rgba(0,0,0,0.10)' }}>
        <div style={{ fontWeight: 600, marginBottom: 4, color: '#111827' }}>{label}</div>
        {payload.map(p => <div key={p.name} style={{ color: p.color }}>{p.name}: <strong>{p.value}t</strong></div>)}
      </div>
    );
  };

  return (
    <>
      <div className="page-header">
        <span className="page-title">Dashboard</span>
        <span className="page-subtitle">— Acme Industries Ltd · FY 2024 Q1</span>
      </div>
      <div className="page-body">

        {/* KPI row */}
        <div className="kpi-grid">
          <KPI label="Total tCO₂e"     value={fmt(data.total_co2e_t)}          unit="metric tonnes CO₂e"        cls="total"   />
          <KPI label="Scope 1"          value={fmt(data.scope_1_co2e_kg/1000)}  unit={`${data.scope_1_count} records`} cls="scope1" />
          <KPI label="Scope 2"          value={fmt(data.scope_2_co2e_kg/1000)}  unit={`${data.scope_2_count} records`} cls="scope2" />
          <KPI label="Scope 3"          value={fmt(data.scope_3_co2e_kg/1000)}  unit={`${data.scope_3_count} records`} cls="scope3" />
          <KPI label="Pending Review"   value={data.pending_count}               unit="need analyst action"       cls="pending" />
          <KPI label="Flagged"          value={data.flagged_count}               unit="need attention"            cls="flagged" />
          <KPI label="Approved"         value={data.approved_count}              unit="cleared"                   cls="total"   />
          <KPI label="Locked"           value={data.locked_count}                unit="audit-ready"               cls="total"   />
        </div>

        {/* Charts */}
        <div className="chart-grid">

          {/* Scope bar chart — compact, no big gaps */}
          <div className="card">
            <div className="section-title">Emissions by Scope (tCO₂e)</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={scopeData}
                barCategoryGap="28%"
                barGap={0}
                margin={{ top: 4, right: 8, left: -10, bottom: 0 }}
              >
                <CartesianGrid vertical={false} stroke="#f0f1f4" strokeDasharray="0" />
                <XAxis
                  dataKey="name"
                  axisLine={false} tickLine={false}
                  tick={{ fill: '#4b5563', fontSize: 12, fontWeight: 500 }}
                />
                <YAxis
                  axisLine={false} tickLine={false}
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  tickFormatter={v => v + 't'}
                  width={44}
                />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="value" name="tCO₂e" radius={[5, 5, 0, 0]} maxBarSize={64}>
                  {scopeData.map((_, i) => <Cell key={i} fill={SCOPE_COLORS[i + 1]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Source breakdown — clean horizontal bars */}
          <div className="card">
            <div className="section-title">Breakdown by Source</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20, paddingTop: 8 }}>
              {sourceData.map(s => (
                <div key={s.name}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        display: 'inline-block', width: 10, height: 10,
                        borderRadius: '50%', background: SOURCE_COLORS[s.name], flexShrink: 0,
                      }} />
                      <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>{s.name}</span>
                      <span style={{ fontSize: 11, color: '#9ca3af' }}>{s.count} records</span>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>{fmtT(s.tCO2e)}</span>
                      <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 3 }}>t · {s.pct}%</span>
                    </div>
                  </div>
                  <div style={{ height: 8, background: '#f0f1f4', borderRadius: 99, overflow: 'hidden' }}>
                    <div style={{
                      height: '100%',
                      width: `${maxSource > 0 ? (s.tCO2e / maxSource) * 100 : 0}%`,
                      background: SOURCE_COLORS[s.name],
                      borderRadius: 99,
                      transition: 'width 0.6s ease',
                    }} />
                  </div>
                </div>
              ))}

              {/* Total row */}
              <div style={{ borderTop: '1px solid #e2e5ea', paddingTop: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.6px' }}>Total</span>
                <span style={{ fontSize: 16, fontWeight: 700, color: '#111827' }}>{fmtT(data.total_co2e_t)} tCO₂e</span>
              </div>
            </div>
          </div>
        </div>

        {/* Recent batches */}
        <div className="card">
          <div className="section-title">Recent Ingestion Batches</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th><th>File</th><th>Uploaded By</th><th>Rows</th>
                  <th>Pending</th><th>Flagged</th><th>Approved</th><th>tCO₂e</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_batches.map(b => (
                  <tr key={b.id}>
                    <td><SourceBadge src={b.source_type} /></td>
                    <td className="mono">{b.filename}</td>
                    <td>{b.uploaded_by || '—'}</td>
                    <td>{b.row_count}</td>
                    <td><span className="badge badge-pending">{b.pending_count}</span></td>
                    <td><span className="badge badge-flagged">{b.flagged_count}</span></td>
                    <td><span className="badge badge-approved">{b.approved_count}</span></td>
                    <td className="mono">{(b.total_co2e_kg / 1000).toFixed(2)}t</td>
                    <td><StatusBadge s={b.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}

function KPI({ label, value, unit, cls }) {
  return (
    <div className={`kpi-card ${cls}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-unit">{unit}</div>
    </div>
  );
}

function SourceBadge({ src }) {
  const cls = { SAP: 'badge-sap', UTILITY: 'badge-utility', TRAVEL: 'badge-travel' }[src] || '';
  return <span className={`badge ${cls}`}>{src}</span>;
}

function StatusBadge({ s }) {
  const map = { COMPLETE: 'approved', FAILED: 'flagged', PROCESSING: 'pending' };
  return <span className={`badge badge-${map[s] || 'pending'}`}>{s}</span>;
}
