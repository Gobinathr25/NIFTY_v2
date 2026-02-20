import { useState, useEffect } from 'react'
import { api } from '../hooks/useWebSocket'

const STATUS_COLOR = { OPEN:'#ffa502', CLOSED:'#2ed573', FORCE_CLOSE:'#ff4757' }

export default function TradeLog() {
  const [trades,  setTrades]  = useState([])
  const [filter,  setFilter]  = useState('ALL')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api('/api/trades').then(r => { setTrades(r.trades || []); setLoading(false) })
  }, [])

  const filtered = filter === 'ALL' ? trades : trades.filter(t => t.status === filter)
  const totalPnL = filtered.reduce((s, t) => s + (t.realized_pnl || 0), 0)

  return (
    <div style={S.page}>
      <div style={S.header}>
        <span style={S.title}>Trade Log</span>
        <div style={S.filters}>
          {['ALL','OPEN','CLOSED'].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              style={{ ...S.filterBtn, ...(filter===f ? S.filterActive : {}) }}>{f}</button>
          ))}
        </div>
        <div style={S.summary}>
          <span style={{ color:'#8899bb', fontSize:12 }}>{filtered.length} trades</span>
          <span style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:13, fontWeight:600,
            color: totalPnL >= 0 ? '#2ed573' : '#ff4757' }}>
            Net: {totalPnL >= 0 ? '+' : ''}₹{totalPnL.toLocaleString('en-IN', {maximumFractionDigits:0})}
          </span>
        </div>
      </div>

      {loading && <div style={S.loading}>Loading trade history…</div>}
      {!loading && filtered.length === 0 && (
        <div style={S.empty}>
          <div style={{ fontSize:36 }}>📋</div>
          <div style={{ color:'#8899bb' }}>No trades found</div>
        </div>
      )}

      {filtered.length > 0 && (
        <div style={S.tableWrap}>
          <table style={S.table}>
            <thead>
              <tr>{['Date','Entry','Exit','CE Strike','PE Strike','Premium','Qty','Realised P&L','Adj','Status','Reason']
                .map(h => <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {filtered.map((t, i) => {
                const pnl = t.realized_pnl || 0
                return (
                  <tr key={t.id} style={S.tr}>
                    <td style={S.td}><code style={S.mono}>{t.trade_date}</code></td>
                    <td style={{ ...S.td, ...S.monoS }}>{t.entry_time ? t.entry_time.substring(11,19) : '—'}</td>
                    <td style={{ ...S.td, ...S.monoS }}>{t.exit_time  ? t.exit_time.substring(11,19)  : '—'}</td>
                    <td style={{ ...S.td, ...S.mono, color:'#0099ff' }}>{t.ce_strike}</td>
                    <td style={{ ...S.td, ...S.mono, color:'#ff4757' }}>{t.pe_strike}</td>
                    <td style={{ ...S.td, ...S.mono }}>₹{t.premium_collected?.toFixed(0)}</td>
                    <td style={{ ...S.td, ...S.mono }}>{t.quantity}</td>
                    <td style={{ ...S.td, ...S.mono, fontWeight:600,
                      color: pnl >= 0 ? '#2ed573' : '#ff4757' }}>
                      {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN', {maximumFractionDigits:0})}
                    </td>
                    <td style={{ ...S.td, ...S.monoS }}>{t.adjustment_level || 0}</td>
                    <td style={S.td}>
                      <span style={{ ...S.statusBadge, color: STATUS_COLOR[t.status] || '#8899bb',
                        border: `1px solid ${STATUS_COLOR[t.status] || '#8899bb'}44`,
                        background: `${STATUS_COLOR[t.status] || '#8899bb'}11` }}>{t.status}</span>
                    </td>
                    <td style={{ ...S.td, color:'#8899bb', fontSize:11 }}>{t.close_reason || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const S = {
  page:        { display:'flex', flexDirection:'column', gap:16 },
  header:      { display:'flex', alignItems:'center', gap:16, flexWrap:'wrap' },
  title:       { fontSize:16, fontWeight:600, color:'#e8edf5' },
  filters:     { display:'flex', gap:6 },
  filterBtn:   { padding:'5px 14px', background:'transparent', border:'1px solid #1e2d50',
                 color:'#8899bb', borderRadius:6, fontSize:12, cursor:'pointer' },
  filterActive:{ background:'rgba(0,212,170,.1)', borderColor:'#00d4aa', color:'#00d4aa' },
  summary:     { marginLeft:'auto', display:'flex', gap:16, alignItems:'center' },
  loading:     { color:'#8899bb', padding:40, textAlign:'center' },
  empty:       { padding:60, textAlign:'center', display:'flex', flexDirection:'column', alignItems:'center', gap:12 },
  tableWrap:   { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, overflow:'auto' },
  table:       { width:'100%', borderCollapse:'collapse' },
  th:          { padding:'10px 14px', fontSize:10, fontWeight:700, color:'#4a5a7a', letterSpacing:.5,
                 textTransform:'uppercase', textAlign:'left', borderBottom:'1px solid #1e2d50',
                 background:'#0a0e1a', whiteSpace:'nowrap' },
  tr:          { borderBottom:'1px solid #1e2d5044' },
  td:          { padding:'10px 14px', fontSize:13, color:'#e8edf5', whiteSpace:'nowrap' },
  mono:        { fontFamily:"'JetBrains Mono',monospace", fontSize:13 },
  monoS:       { fontFamily:"'JetBrains Mono',monospace", fontSize:12, color:'#8899bb' },
  statusBadge: { fontSize:11, fontWeight:700, padding:'2px 8px', borderRadius:4 },
}
