export default function LiveTerminal({ live }) {
  const running = live?.running
  const spot    = live?.spot || 0

  return (
    <div style={S.page}>
      {/* Top metrics row */}
      <div style={S.metricsRow}>
        {[
          { label:'NIFTY SPOT',     value: spot > 0 ? spot.toFixed(2) : '—',              color:'#00d4aa', large:true },
          { label:'VWAP',           value: live?.vwap > 0 ? live.vwap.toFixed(2) : '—',   color:'#e8edf5' },
          { label:'SUPERTREND',     value: live?.supertrend || '—',
            color: live?.supertrend==='BULLISH' ? '#2ed573' : live?.supertrend==='BEARISH' ? '#ff4757' : '#8899bb' },
          { label:'NET DELTA',      value: live?.net_delta != null ? live.net_delta.toFixed(3) : '—',
            color: Math.abs(live?.net_delta||0) > 0.5 ? '#ffa502' : '#e8edf5' },
          { label:'GAMMA RISK',     value: live?.gamma_score != null ? `${live.gamma_score.toFixed(0)}/100` : '—',
            color: (live?.gamma_score||0) > 70 ? '#ff4757' : (live?.gamma_score||0) > 40 ? '#ffa502' : '#2ed573' },
          { label:'OPEN POSITIONS', value: live?.open_positions ?? '—',                    color:'#e8edf5' },
        ].map(m => <MetricCard key={m.label} {...m} />)}
      </div>

      {/* PnL row */}
      <div style={S.pnlRow}>
        <PnLCard label="MTM P&L (Unrealised)"  value={live?.mtm_pnl  || 0} />
        <PnLCard label="Daily P&L (Realised)"  value={live?.daily_pnl || 0} />
        <PnLCard label="Trades Today"  value={live?.trades_today ?? 0} isTrades />
      </div>

      {/* Status */}
      <div style={S.statusCard}>
        <div style={S.statusLeft}>
          <div style={{ ...S.statusDot, background: running ? '#2ed573' : '#ff4757',
            boxShadow: running ? '0 0 8px #2ed573' : 'none',
            animation: running ? 'pulse-green 2s infinite' : 'none' }} />
          <div>
            <div style={S.statusTitle}>{running ? 'STRATEGY RUNNING' : 'STRATEGY IDLE'}</div>
            <div style={S.statusSub}>{running ? 'Monitoring positions. Auto-adjust active.' : 'Waiting for market open or manual start.'}</div>
          </div>
        </div>
        <div style={S.lastUpdate}>
          {live?.ts ? `Last update: ${new Date(live.ts).toLocaleTimeString('en-IN')}` : '—'}
        </div>
      </div>

      {/* Config summary */}
      {live?.capital && (
        <div style={S.configRow}>
          {[
            ['Capital',    `₹${(live.capital/100000).toFixed(1)}L`],
            ['Lots',       live.num_lots],
            ['Risk/Trade', `${live.risk_pct}%`],
            ['Mode',       'PAPER'],
          ].map(([k,v]) => (
            <div key={k} style={S.configItem}>
              <span style={S.configLabel}>{k}</span>
              <span style={S.configValue}>{v}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value, color, large }) {
  return (
    <div style={S.metricCard}>
      <div style={S.metricLabel}>{label}</div>
      <div style={{ ...S.metricValue, color, fontSize: large ? 28 : 22 }}>{value}</div>
    </div>
  )
}

function PnLCard({ label, value, isTrades }) {
  const pos = value >= 0
  return (
    <div style={{ ...S.pnlCard, borderTop: `2px solid ${isTrades ? '#0099ff' : pos ? '#2ed573' : '#ff4757'}` }}>
      <div style={S.pnlLabel}>{label}</div>
      <div style={{ ...S.pnlValue, color: isTrades ? '#0099ff' : pos ? '#2ed573' : '#ff4757' }}>
        {isTrades ? value : `₹${Math.abs(value).toLocaleString('en-IN', {maximumFractionDigits:0})}`}
        {!isTrades && <span style={{ fontSize:13, marginLeft:4 }}>{pos ? '▲' : '▼'}</span>}
      </div>
    </div>
  )
}

const S = {
  page:        { display:'flex', flexDirection:'column', gap:16 },
  metricsRow:  { display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))', gap:12 },
  metricCard:  { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:'16px 20px' },
  metricLabel: { fontSize:10, color:'#4a5a7a', letterSpacing:1, textTransform:'uppercase', marginBottom:8 },
  metricValue: { fontFamily:"'JetBrains Mono',monospace", fontWeight:600 },
  pnlRow:      { display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12 },
  pnlCard:     { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:'16px 20px' },
  pnlLabel:    { fontSize:11, color:'#8899bb', marginBottom:8 },
  pnlValue:    { fontFamily:"'JetBrains Mono',monospace", fontSize:24, fontWeight:700,
                 display:'flex', alignItems:'center' },
  statusCard:  { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:'16px 20px',
                 display:'flex', justifyContent:'space-between', alignItems:'center' },
  statusLeft:  { display:'flex', alignItems:'center', gap:14 },
  statusDot:   { width:12, height:12, borderRadius:'50%', flexShrink:0 },
  statusTitle: { fontWeight:600, fontSize:14, color:'#e8edf5' },
  statusSub:   { color:'#8899bb', fontSize:12, marginTop:2 },
  lastUpdate:  { fontSize:11, color:'#4a5a7a', fontFamily:"'JetBrains Mono',monospace" },
  configRow:   { display:'flex', gap:0, background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, overflow:'hidden' },
  configItem:  { flex:1, padding:'12px 20px', borderRight:'1px solid #1e2d50', display:'flex', flexDirection:'column', gap:4 },
  configLabel: { fontSize:10, color:'#4a5a7a', letterSpacing:1, textTransform:'uppercase' },
  configValue: { fontSize:16, fontWeight:600, fontFamily:"'JetBrains Mono',monospace", color:'#e8edf5' },
}
