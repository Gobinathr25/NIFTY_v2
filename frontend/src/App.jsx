import { useState, useEffect } from 'react'
import { useWebSocket, api } from './hooks/useWebSocket'
import LiveTerminal   from './pages/LiveTerminal'
import Positions      from './pages/Positions'
import TradeLog       from './pages/TradeLog'
import PnLHistory     from './pages/PnLHistory'
import StrategyControl from './pages/StrategyControl'
import LoginPanel     from './pages/LoginPanel'

const TABS = [
  { id:'terminal',  label:'Live Terminal',     icon:'📡' },
  { id:'positions', label:'Positions',         icon:'📂' },
  { id:'log',       label:'Trade Log',         icon:'📋' },
  { id:'pnl',       label:'P&L History',       icon:'📊' },
  { id:'control',   label:'Strategy Control',  icon:'🎛️' },
  { id:'login',     label:'Session',           icon:'🔐' },
]

export default function App() {
  const { data: ws, connected } = useWebSocket()
  const [tab,    setTab]    = useState('terminal')
  const [status, setStatus] = useState(null)

  useEffect(() => {
    api('/api/status').then(setStatus).catch(() => {})
  }, [])

  // Merge websocket ticks into status
  const live = ws ? { ...status, ...ws } : status
  const loggedIn = live?.logged_in || live?.strategy_ready

  return (
    <div style={S.app}>
      {/* ── Top bar ── */}
      <header style={S.header}>
        <div style={S.brand}>
          <span style={S.brandDot} />
          <span style={S.brandName}>NIFTY Terminal</span>
          <span style={S.paperBadge}>PAPER MODE</span>
        </div>

        <div style={S.headerCenter}>
          {live?.spot > 0 && (
            <>
              <Stat label="NIFTY" value={live.spot?.toFixed(2)} accent />
              <Stat label="VWAP"  value={live.vwap?.toFixed(2)} />
              <Stat label="Trend" value={live.supertrend}
                color={live.supertrend === 'BULLISH' ? '#2ed573' : live.supertrend === 'BEARISH' ? '#ff4757' : '#8899bb'} />
              <Stat label="Delta"  value={live.net_delta?.toFixed(2)} />
              <Stat label="Gamma"  value={live.gamma_score?.toFixed(0) + '/100'} />
              <Stat label="MTM"    value={'₹' + (live.mtm_pnl || 0).toLocaleString('en-IN', {maximumFractionDigits:0})}
                color={(live.mtm_pnl || 0) >= 0 ? '#2ed573' : '#ff4757'} />
            </>
          )}
        </div>

        <div style={S.headerRight}>
          <div style={{ ...S.wsDot, background: connected ? '#2ed573' : '#ff4757' }} />
          <span style={S.wsLabel}>{connected ? 'LIVE' : 'OFFLINE'}</span>
          {loggedIn
            ? <span style={S.loginBadge}>🟢 Connected</span>
            : <span style={{ ...S.loginBadge, color:'#ff4757' }}>🔴 Not Connected</span>}
        </div>
      </header>

      {/* ── Tabs ── */}
      <nav style={S.nav}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ ...S.tab, ...(tab === t.id ? S.tabActive : {}) }}>
            <span>{t.icon}</span> {t.label}
          </button>
        ))}
      </nav>

      {/* ── Content ── */}
      <main style={S.main}>
        {tab === 'terminal'  && <LiveTerminal  live={live} />}
        {tab === 'positions' && <Positions />}
        {tab === 'log'       && <TradeLog />}
        {tab === 'pnl'       && <PnLHistory />}
        {tab === 'control'   && <StrategyControl live={live} onRefresh={() => api('/api/status').then(setStatus)} />}
        {tab === 'login'     && <LoginPanel live={live} onLogin={() => api('/api/status').then(setStatus)} />}
      </main>
    </div>
  )
}

function Stat({ label, value, accent, color }) {
  return (
    <div style={S.stat}>
      <span style={S.statLabel}>{label}</span>
      <span style={{ ...S.statValue, color: color || (accent ? '#00d4aa' : '#e8edf5') }}>{value || '—'}</span>
    </div>
  )
}

const S = {
  app:         { display:'flex', flexDirection:'column', height:'100vh', background:'#0a0e1a' },
  header:      { display:'flex', alignItems:'center', justifyContent:'space-between', padding:'0 20px',
                 height:52, background:'#0f1527', borderBottom:'1px solid #1e2d50', flexShrink:0 },
  brand:       { display:'flex', alignItems:'center', gap:10 },
  brandDot:    { width:8, height:8, borderRadius:'50%', background:'#00d4aa',
                 boxShadow:'0 0 8px #00d4aa', animation:'pulse-green 2s infinite' },
  brandName:   { fontFamily:"'JetBrains Mono', monospace", fontWeight:600, fontSize:15, color:'#e8edf5', letterSpacing:1 },
  paperBadge:  { fontSize:10, fontWeight:700, padding:'2px 8px', borderRadius:3,
                 background:'rgba(255,167,2,0.15)', color:'#ffa502', border:'1px solid rgba(255,167,2,0.3)', letterSpacing:1 },
  headerCenter:{ display:'flex', alignItems:'center', gap:24 },
  headerRight: { display:'flex', alignItems:'center', gap:10 },
  wsDot:       { width:7, height:7, borderRadius:'50%', transition:'background .3s' },
  wsLabel:     { fontSize:11, fontFamily:"'JetBrains Mono',monospace", fontWeight:600, color:'#8899bb' },
  loginBadge:  { fontSize:12, color:'#2ed573' },
  stat:        { display:'flex', flexDirection:'column', alignItems:'center', gap:1 },
  statLabel:   { fontSize:10, color:'#4a5a7a', letterSpacing:.5, textTransform:'uppercase' },
  statValue:   { fontSize:13, fontFamily:"'JetBrains Mono',monospace", fontWeight:500 },
  nav:         { display:'flex', background:'#0f1527', borderBottom:'1px solid #1e2d50', flexShrink:0, overflowX:'auto' },
  tab:         { display:'flex', alignItems:'center', gap:6, padding:'10px 20px', border:'none',
                 background:'transparent', color:'#8899bb', fontSize:13, fontWeight:500, cursor:'pointer',
                 borderBottom:'2px solid transparent', transition:'all .15s', whiteSpace:'nowrap' },
  tabActive:   { color:'#00d4aa', borderBottomColor:'#00d4aa', background:'rgba(0,212,170,0.05)' },
  main:        { flex:1, overflow:'auto', padding:20 },
}
