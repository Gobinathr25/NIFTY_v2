import { useState, useEffect } from 'react'
import { api } from '../hooks/useWebSocket'

export default function Positions() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try { setData(await api('/api/positions')) }
    catch(e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t) }, [])

  const positions = data?.positions || []
  const live  = positions.filter(p => !p.is_hedge)
  const hedge = positions.filter(p =>  p.is_hedge)

  return (
    <div style={S.page}>
      <div style={S.header}>
        <span style={S.title}>Open Positions</span>
        <div style={S.headerRight}>
          <span style={S.badge}>{positions.length} position{positions.length!==1?'s':''}</span>
          <button onClick={load} style={S.refreshBtn}>↻ Refresh</button>
        </div>
      </div>

      {loading && <div style={S.loading}>Loading positions…</div>}

      {!loading && positions.length === 0 && (
        <div style={S.empty}>
          <div style={S.emptyIcon}>📂</div>
          <div style={S.emptyText}>No open positions</div>
          <div style={S.emptySub}>Positions will appear here after strategy takes an entry</div>
        </div>
      )}

      {positions.length > 0 && (
        <>
          {live.length > 0 && (
            <>
              <div style={S.sectionLabel}>SHORT LEGS</div>
              <PositionTable rows={live} />
            </>
          )}
          {hedge.length > 0 && (
            <>
              <div style={S.sectionLabel}>HEDGE LEGS</div>
              <PositionTable rows={hedge} />
            </>
          )}
        </>
      )}
    </div>
  )
}

function PositionTable({ rows }) {
  const totalPnL = rows.reduce((s, r) => s + (r.pnl || 0), 0)
  return (
    <div style={S.tableWrap}>
      <table style={S.table}>
        <thead>
          <tr>{['Symbol','Strike','Type','Side','Entry','LTP','P&L','Delta','Gamma','Theta'].map(h =>
            <th key={h} style={S.th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const pnl    = r.pnl || 0
            const pnlPos = pnl >= 0
            return (
              <tr key={i} style={{ ...S.tr, animation:'slide-in .2s ease forwards', animationDelay:`${i*30}ms` }}>
                <td style={S.td}><code style={S.symbol}>{r.symbol}</code></td>
                <td style={{ ...S.td, ...S.mono }}>{r.strike}</td>
                <td style={S.td}>
                  <span style={{ ...S.badge2, background: r.option_type==='CE' ? 'rgba(0,153,255,.15)' : 'rgba(255,71,87,.15)',
                    color: r.option_type==='CE' ? '#0099ff' : '#ff4757' }}>{r.option_type}</span>
                </td>
                <td style={S.td}>
                  <span style={{ ...S.badge2, background: r.side==='SELL' ? 'rgba(255,71,87,.1)' : 'rgba(46,213,115,.1)',
                    color: r.side==='SELL' ? '#ff4757' : '#2ed573' }}>{r.side}</span>
                </td>
                <td style={{ ...S.td, ...S.mono }}>{r.entry_px?.toFixed(2)}</td>
                <td style={{ ...S.td, ...S.mono }}>{r.current_px?.toFixed(2)}</td>
                <td style={{ ...S.td, ...S.mono, color: pnlPos ? '#2ed573' : '#ff4757', fontWeight:600 }}>
                  {pnlPos ? '+' : ''}₹{pnl.toLocaleString('en-IN', {maximumFractionDigits:0})}
                </td>
                <td style={{ ...S.td, ...S.mono, color: Math.abs(r.delta||0) > 0.4 ? '#ffa502' : '#8899bb' }}>
                  {r.delta?.toFixed(3)}
                </td>
                <td style={{ ...S.td, ...S.mono, color:'#8899bb' }}>{r.gamma?.toFixed(4)}</td>
                <td style={{ ...S.td, ...S.mono, color:'#ff4757' }}>{r.theta?.toFixed(2)}</td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={6} style={{ ...S.td, color:'#8899bb', fontSize:11 }}>TOTAL P&L</td>
            <td style={{ ...S.td, ...S.mono, fontWeight:700, fontSize:16,
              color: totalPnL >= 0 ? '#2ed573' : '#ff4757' }}>
              {totalPnL >= 0 ? '+' : ''}₹{totalPnL.toLocaleString('en-IN', {maximumFractionDigits:0})}
            </td>
            <td colSpan={3} style={S.td} />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

const mono = { fontFamily:"'JetBrains Mono',monospace", fontSize:13 }
const S = {
  page:        { display:'flex', flexDirection:'column', gap:16 },
  header:      { display:'flex', justifyContent:'space-between', alignItems:'center' },
  title:       { fontSize:16, fontWeight:600, color:'#e8edf5' },
  headerRight: { display:'flex', gap:10, alignItems:'center' },
  badge:       { fontSize:11, padding:'3px 10px', background:'rgba(0,212,170,.1)', color:'#00d4aa',
                 border:'1px solid rgba(0,212,170,.2)', borderRadius:20 },
  badge2:      { fontSize:11, fontWeight:600, padding:'2px 8px', borderRadius:4 },
  refreshBtn:  { padding:'5px 12px', background:'transparent', border:'1px solid #1e2d50',
                 color:'#8899bb', borderRadius:6, fontSize:12 },
  loading:     { color:'#8899bb', padding:40, textAlign:'center' },
  empty:       { padding:60, textAlign:'center', display:'flex', flexDirection:'column', alignItems:'center', gap:10 },
  emptyIcon:   { fontSize:40 },
  emptyText:   { fontSize:16, fontWeight:500, color:'#8899bb' },
  emptySub:    { fontSize:12, color:'#4a5a7a' },
  sectionLabel:{ fontSize:10, fontWeight:700, color:'#4a5a7a', letterSpacing:2, textTransform:'uppercase',
                 marginBottom:6, paddingLeft:4 },
  tableWrap:   { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, overflow:'auto', marginBottom:4 },
  table:       { width:'100%', borderCollapse:'collapse' },
  th:          { padding:'10px 14px', fontSize:10, fontWeight:700, color:'#4a5a7a', letterSpacing:.5,
                 textTransform:'uppercase', textAlign:'left', borderBottom:'1px solid #1e2d50',
                 background:'#0a0e1a', whiteSpace:'nowrap' },
  tr:          { borderBottom:'1px solid #1e2d5055', opacity:0 },
  td:          { padding:'10px 14px', fontSize:13, color:'#e8edf5', whiteSpace:'nowrap' },
  mono,
  symbol:      { fontFamily:"'JetBrains Mono',monospace", fontSize:11, color:'#8899bb' },
}
