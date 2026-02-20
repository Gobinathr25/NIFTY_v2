import { useState } from 'react'
import { api } from '../hooks/useWebSocket'

export default function StrategyControl({ live, onRefresh }) {
  const [loading, setLoading] = useState('')
  const [msg,     setMsg]     = useState(null)
  const [params,  setParams]  = useState({ capital:'', risk_pct:'', num_lots:'' })
  const [margin,  setMargin]  = useState(null)

  const running = live?.running
  const ready   = live?.strategy_ready

  async function action(path, label) {
    setLoading(label); setMsg(null)
    try {
      const r = await api(path, 'POST')
      setMsg({ ok:true, text: r.message })
      onRefresh()
    } catch(e) { setMsg({ ok:false, text: e.message }) }
    setLoading('')
  }

  async function saveParams() {
    const body = {}
    if (params.capital)  body.capital  = parseFloat(params.capital)
    if (params.risk_pct) body.risk_pct = parseFloat(params.risk_pct)
    if (params.num_lots) body.num_lots = parseInt(params.num_lots)
    if (!Object.keys(body).length) return
    setLoading('params'); setMsg(null)
    try {
      await api('/api/strategy/params', 'POST', body)
      setMsg({ ok:true, text:'Parameters updated.' })
      setParams({ capital:'', risk_pct:'', num_lots:'' })
      onRefresh()
    } catch(e) { setMsg({ ok:false, text: e.message }) }
    setLoading('')
  }

  async function fetchMargin() {
    setLoading('margin'); setMsg(null)
    try { setMargin(await api('/api/margin')) }
    catch(e) { setMsg({ ok:false, text: 'Margin fetch failed: ' + e.message }) }
    setLoading('')
  }

  return (
    <div style={S.page}>
      {/* Strategy status */}
      <div style={S.statusCard}>
        <div style={S.statusLeft}>
          <div style={{ ...S.statusDot, background: running ? '#2ed573' : ready ? '#ffa502' : '#ff4757',
            boxShadow: running ? '0 0 10px #2ed57366' : 'none',
            animation: running ? 'pulse-green 2s infinite' : 'none' }} />
          <div>
            <div style={S.statusTitle}>
              {running ? 'Strategy Running' : ready ? 'Strategy Ready (Idle)' : 'Strategy Not Initialised'}
            </div>
            <div style={S.statusSub}>
              {running ? 'Auto-monitor active. Adjustments will be triggered automatically.'
               : ready  ? 'Click Start to begin trading.'
               : 'Go to Session tab and login first.'}
            </div>
          </div>
        </div>
      </div>

      {/* Control buttons */}
      <div style={S.controlRow}>
        <CtrlBtn label="▶ Start Strategy"   color="#2ed573" onClick={() => action('/api/strategy/start','start')}
          disabled={!ready || running} loading={loading==='start'} />
        <CtrlBtn label="⏹ Stop Strategy"    color="#ffa502" onClick={() => action('/api/strategy/stop','stop')}
          disabled={!running} loading={loading==='stop'} />
        <CtrlBtn label="⚠ Close All Orders" color="#ff4757" onClick={() => action('/api/strategy/close-all','close')}
          disabled={!ready} loading={loading==='close'} confirm />
        <CtrlBtn label="↺ Reset Day"         color="#8899bb" onClick={() => action('/api/strategy/reset-day','reset')}
          disabled={!ready} loading={loading==='reset'} />
      </div>

      {msg && (
        <div style={{ ...S.msg, background: msg.ok ? 'rgba(46,213,115,.1)' : 'rgba(255,71,87,.1)',
                      border: `1px solid ${msg.ok ? '#2ed573' : '#ff4757'}44`,
                      color: msg.ok ? '#2ed573' : '#ff4757' }}>{msg.text}</div>
      )}

      {/* Current params */}
      <div style={S.row2}>
        <div style={S.card}>
          <div style={S.cardTitle}>Current Parameters</div>
          <div style={S.paramGrid}>
            {[
              ['Capital',    `₹${(live?.capital||0).toLocaleString('en-IN')}`],
              ['Risk/Trade', `${live?.risk_pct || 0}%`],
              ['Lots',       live?.num_lots || 0],
              ['Qty/Leg',    (live?.num_lots || 0) * 65],
            ].map(([k,v]) => (
              <div key={k} style={S.paramItem}>
                <div style={S.paramLabel}>{k}</div>
                <div style={S.paramValue}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={S.card}>
          <div style={S.cardTitle}>Update Parameters</div>
          <div style={S.fieldGroup}>
            <Field label="Capital (₹)"    value={params.capital}    placeholder={live?.capital}
              onChange={v => setParams(p => ({...p, capital:v}))} />
            <Field label="Risk % per trade" value={params.risk_pct}  placeholder={live?.risk_pct}
              onChange={v => setParams(p => ({...p, risk_pct:v}))} />
            <Field label="Number of Lots"  value={params.num_lots}   placeholder={live?.num_lots}
              onChange={v => setParams(p => ({...p, num_lots:v}))} />
          </div>
          <button onClick={saveParams} disabled={loading==='params'}
            style={{ ...S.saveBtn, opacity: loading==='params' ? .6 : 1 }}>
            {loading==='params' ? 'Saving…' : '💾 Save Parameters'}
          </button>
        </div>
      </div>

      {/* Margin calculator */}
      <div style={S.card}>
        <div style={S.cardTitle}>Margin Calculator</div>
        <button onClick={fetchMargin} disabled={!ready || loading==='margin'}
          style={S.marginBtn}>
          {loading==='margin' ? 'Fetching from Fyers…' : '🔄 Fetch Live Margin from Fyers'}
        </button>
        {margin && (
          <div style={S.marginGrid}>
            {[
              ['SPAN Margin',     `₹${(margin.span_margin||0).toLocaleString('en-IN',{maximumFractionDigits:0})}`],
              ['Exposure Margin', `₹${(margin.exposure_margin||0).toLocaleString('en-IN',{maximumFractionDigits:0})}`],
              ['Total Required',  `₹${(margin.total_margin||0).toLocaleString('en-IN',{maximumFractionDigits:0})}`, '#ffa502'],
              ['Hedge Benefit',   `₹${(margin.hedge_benefit||0).toLocaleString('en-IN',{maximumFractionDigits:0})}`, '#2ed573'],
            ].map(([k,v,c]) => (
              <div key={k} style={S.marginItem}>
                <div style={S.marginLabel}>{k}</div>
                <div style={{ ...S.marginValue, color: c || '#e8edf5' }}>{v}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Schedule info */}
      <div style={S.card}>
        <div style={S.cardTitle}>Auto-Schedule (IST)</div>
        <div style={S.scheduleGrid}>
          {[
            ['09:20', 'Market Open',    'Strategy auto-starts, entries enabled', '#2ed573'],
            ['14:45', 'No New Trades',  'Entry disabled, existing positions monitored', '#ffa502'],
            ['15:10', 'Force Close',    'All open positions closed forcefully', '#ff4757'],
            ['15:20', 'EOD Report',     'P&L summary sent via Telegram', '#0099ff'],
          ].map(([t,label,desc,c]) => (
            <div key={t} style={S.scheduleRow}>
              <code style={{ ...S.scheduleTime, color:c }}>{t}</code>
              <div>
                <div style={{ fontSize:13, fontWeight:600, color:'#e8edf5' }}>{label}</div>
                <div style={{ fontSize:11, color:'#8899bb' }}>{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function CtrlBtn({ label, color, onClick, disabled, loading, confirm }) {
  function handleClick() {
    if (confirm && !window.confirm('Are you sure? This will close ALL open positions.')) return
    onClick()
  }
  return (
    <button onClick={handleClick} disabled={disabled || loading}
      style={{ flex:1, padding:'12px 8px', border:`1px solid ${color}44`,
        background: disabled ? 'transparent' : `${color}15`,
        color: disabled ? '#4a5a7a' : color, borderRadius:8, fontSize:13, fontWeight:600,
        cursor: disabled ? 'not-allowed' : 'pointer', transition:'all .15s',
        opacity: disabled ? .5 : 1 }}>
      {loading ? '…' : label}
    </button>
  )
}

function Field({ label, value, placeholder, onChange }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
      <label style={{ fontSize:11, color:'#8899bb' }}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)}
        placeholder={String(placeholder || '')}
        style={{ padding:'8px 12px', background:'#151d35', border:'1px solid #1e2d50',
                 borderRadius:6, color:'#e8edf5', fontSize:13, outline:'none',
                 fontFamily:"'JetBrains Mono',monospace" }} />
    </div>
  )
}

const S = {
  page:          { display:'flex', flexDirection:'column', gap:16 },
  statusCard:    { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:'16px 20px' },
  statusLeft:    { display:'flex', alignItems:'center', gap:14 },
  statusDot:     { width:14, height:14, borderRadius:'50%', flexShrink:0 },
  statusTitle:   { fontSize:15, fontWeight:600, color:'#e8edf5' },
  statusSub:     { fontSize:12, color:'#8899bb', marginTop:3 },
  controlRow:    { display:'flex', gap:10 },
  msg:           { padding:'10px 16px', borderRadius:8, fontSize:13 },
  row2:          { display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 },
  card:          { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:20 },
  cardTitle:     { fontSize:12, fontWeight:700, color:'#8899bb', textTransform:'uppercase',
                   letterSpacing:1, marginBottom:16 },
  paramGrid:     { display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 },
  paramItem:     { padding:12, background:'#151d35', borderRadius:8 },
  paramLabel:    { fontSize:10, color:'#4a5a7a', textTransform:'uppercase', letterSpacing:.5, marginBottom:4 },
  paramValue:    { fontFamily:"'JetBrains Mono',monospace", fontSize:16, fontWeight:600, color:'#e8edf5' },
  fieldGroup:    { display:'flex', flexDirection:'column', gap:10, marginBottom:14 },
  saveBtn:       { width:'100%', padding:'9px', background:'rgba(0,212,170,.15)', color:'#00d4aa',
                   border:'1px solid rgba(0,212,170,.3)', borderRadius:7, fontSize:13, fontWeight:600 },
  marginBtn:     { padding:'9px 18px', background:'rgba(0,153,255,.1)', color:'#0099ff',
                   border:'1px solid rgba(0,153,255,.3)', borderRadius:7, fontSize:13, marginBottom:14 },
  marginGrid:    { display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 },
  marginItem:    { padding:12, background:'#151d35', borderRadius:8 },
  marginLabel:   { fontSize:10, color:'#4a5a7a', textTransform:'uppercase', letterSpacing:.5, marginBottom:4 },
  marginValue:   { fontFamily:"'JetBrains Mono',monospace", fontSize:17, fontWeight:700 },
  scheduleGrid:  { display:'flex', flexDirection:'column', gap:12 },
  scheduleRow:   { display:'flex', alignItems:'center', gap:16, padding:'10px 0',
                   borderBottom:'1px solid #1e2d5055' },
  scheduleTime:  { fontFamily:"'JetBrains Mono',monospace", fontSize:18, fontWeight:700, minWidth:56 },
}
