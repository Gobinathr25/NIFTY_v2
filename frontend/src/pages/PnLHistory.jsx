import { useState, useEffect } from 'react'
import { api } from '../hooks/useWebSocket'

export default function PnLHistory() {
  const [data, setData] = useState([])

  useEffect(() => {
    api('/api/pnl').then(r => setData(r.summaries || []))
  }, [])

  const totalPnL   = data.reduce((s, d) => s + (d.net_pnl || 0), 0)
  const totalTrades = data.reduce((s, d) => s + (d.total_trades || 0), 0)
  const avgWinRate  = data.length ? data.reduce((s, d) => s + (d.win_rate || 0), 0) / data.length : 0
  const maxDD       = Math.min(...data.map(d => d.max_drawdown || 0), 0)

  // Bar chart dimensions
  const maxAbs = Math.max(...data.map(d => Math.abs(d.net_pnl || 0)), 1)
  const BAR_MAX_H = 80

  return (
    <div style={S.page}>
      {/* Summary cards */}
      <div style={S.summaryRow}>
        {[
          { label:'Total P&L',   value:`₹${totalPnL.toLocaleString('en-IN',{maximumFractionDigits:0})}`,
            color: totalPnL >= 0 ? '#2ed573' : '#ff4757' },
          { label:'Total Trades', value: totalTrades, color:'#e8edf5' },
          { label:'Avg Win Rate', value:`${avgWinRate.toFixed(1)}%`,
            color: avgWinRate >= 50 ? '#2ed573' : '#ff4757' },
          { label:'Max Drawdown', value:`₹${Math.abs(maxDD).toLocaleString('en-IN',{maximumFractionDigits:0})}`,
            color:'#ff4757' },
          { label:'Trading Days', value: data.length, color:'#e8edf5' },
        ].map(c => (
          <div key={c.label} style={S.summCard}>
            <div style={S.summLabel}>{c.label}</div>
            <div style={{ ...S.summValue, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Bar chart */}
      {data.length > 0 && (
        <div style={S.chartCard}>
          <div style={S.chartTitle}>Daily P&L Chart</div>
          <div style={S.chartArea}>
            <div style={S.baseline} />
            {[...data].reverse().slice(-30).map((d, i) => {
              const pnl  = d.net_pnl || 0
              const pos  = pnl >= 0
              const h    = Math.max(2, (Math.abs(pnl) / maxAbs) * BAR_MAX_H)
              return (
                <div key={i} style={S.barWrap} title={`${d.trade_date}: ₹${pnl.toFixed(0)}`}>
                  <div style={{ ...S.bar,
                    height: h,
                    alignSelf: pos ? 'flex-end' : 'flex-start',
                    background: pos ? '#2ed573' : '#ff4757',
                    opacity: 0.85,
                  }} />
                  <div style={S.barDate}>{d.trade_date?.substring(5)}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Daily table */}
      <div style={S.tableWrap}>
        <div style={S.tableTitle}>Daily Breakdown</div>
        {data.length === 0
          ? <div style={S.empty}><span style={{ fontSize:32 }}>📊</span><div style={{ color:'#8899bb' }}>No data yet</div></div>
          : (
          <table style={S.table}>
            <thead>
              <tr>{['Date','Trades','Winners','Net P&L','Win Rate','Max DD','Capital Used'].map(h =>
                <th key={h} style={S.th}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.map((d, i) => {
                const pnl = d.net_pnl || 0
                return (
                  <tr key={i} style={S.tr}>
                    <td style={{ ...S.td, ...S.mono }}>{d.trade_date}</td>
                    <td style={{ ...S.td, ...S.mono }}>{d.total_trades}</td>
                    <td style={{ ...S.td, ...S.mono, color:'#2ed573' }}>{d.winning_trades}</td>
                    <td style={{ ...S.td, ...S.mono, fontWeight:600,
                      color: pnl >= 0 ? '#2ed573' : '#ff4757' }}>
                      {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN',{maximumFractionDigits:0})}
                    </td>
                    <td style={{ ...S.td, ...S.mono,
                      color: d.win_rate >= 50 ? '#2ed573' : '#ff4757' }}>{d.win_rate?.toFixed(1)}%</td>
                    <td style={{ ...S.td, ...S.mono, color:'#ff4757' }}>
                      ₹{Math.abs(d.max_drawdown || 0).toLocaleString('en-IN',{maximumFractionDigits:0})}
                    </td>
                    <td style={{ ...S.td, ...S.mono }}>₹{(d.capital_used||0).toLocaleString('en-IN',{maximumFractionDigits:0})}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

const S = {
  page:        { display:'flex', flexDirection:'column', gap:16 },
  summaryRow:  { display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))', gap:12 },
  summCard:    { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:'14px 18px' },
  summLabel:   { fontSize:10, color:'#4a5a7a', textTransform:'uppercase', letterSpacing:1, marginBottom:6 },
  summValue:   { fontFamily:"'JetBrains Mono',monospace", fontSize:20, fontWeight:700 },
  chartCard:   { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:20 },
  chartTitle:  { fontSize:12, color:'#8899bb', marginBottom:16, textTransform:'uppercase', letterSpacing:1 },
  chartArea:   { display:'flex', alignItems:'center', gap:3, height:160, position:'relative', paddingTop:80 },
  baseline:    { position:'absolute', top:'50%', left:0, right:0, height:1, background:'#1e2d50' },
  barWrap:     { display:'flex', flexDirection:'column', alignItems:'center', gap:4, flex:'0 0 auto',
                 width:20, height:160, justifyContent:'center' },
  bar:         { width:14, borderRadius:2, cursor:'pointer', transition:'opacity .2s', minHeight:2 },
  barDate:     { fontSize:8, color:'#4a5a7a', transform:'rotate(-45deg)', whiteSpace:'nowrap', marginTop:4 },
  tableWrap:   { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, overflow:'auto' },
  tableTitle:  { padding:'14px 20px', fontSize:12, fontWeight:600, color:'#8899bb', borderBottom:'1px solid #1e2d50',
                 textTransform:'uppercase', letterSpacing:1 },
  empty:       { padding:40, textAlign:'center', display:'flex', flexDirection:'column', alignItems:'center', gap:10 },
  table:       { width:'100%', borderCollapse:'collapse' },
  th:          { padding:'10px 14px', fontSize:10, fontWeight:700, color:'#4a5a7a', letterSpacing:.5,
                 textTransform:'uppercase', textAlign:'left', borderBottom:'1px solid #1e2d50',
                 background:'#0a0e1a', whiteSpace:'nowrap' },
  tr:          { borderBottom:'1px solid #1e2d5044' },
  td:          { padding:'10px 14px', fontSize:13, color:'#e8edf5' },
  mono:        { fontFamily:"'JetBrains Mono',monospace", fontSize:13 },
}
