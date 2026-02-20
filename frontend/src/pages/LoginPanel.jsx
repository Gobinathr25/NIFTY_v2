import { useState } from 'react'
import { api } from '../hooks/useWebSocket'

export default function LoginPanel({ live, onLogin }) {
  const [mode,    setMode]    = useState('totp')
  const [loading, setLoading] = useState(false)
  const [otpSent, setOtpSent] = useState(false)
  const [otp,     setOtp]     = useState('')
  const [msg,     setMsg]     = useState(null)

  async function doTOTP() {
    setLoading(true); setMsg(null)
    try {
      const r = await api('/api/login/totp', 'POST')
      setMsg({ ok: true, text: r.message })
      onLogin()
    } catch(e) { setMsg({ ok: false, text: e.message }) }
    setLoading(false)
  }

  async function sendOTP() {
    setLoading(true); setMsg(null)
    try {
      await api('/api/login/sms/send', 'POST')
      setOtpSent(true)
      setMsg({ ok: true, text: 'OTP sent to registered mobile.' })
    } catch(e) { setMsg({ ok: false, text: e.message }) }
    setLoading(false)
  }

  async function verifyOTP() {
    setLoading(true); setMsg(null)
    try {
      const r = await api('/api/login/sms/verify', 'POST', { otp })
      setMsg({ ok: true, text: r.message })
      onLogin()
    } catch(e) { setMsg({ ok: false, text: e.message }) }
    setLoading(false)
  }

  async function doLogout() {
    await api('/api/logout', 'POST')
    setMsg({ ok: true, text: 'Logged out.' })
    onLogin()
  }

  const isConnected = live?.logged_in || live?.strategy_ready

  return (
    <div style={S.page}>
      <div style={S.card}>
        <div style={S.title}>🔐 Broker Session</div>

        {/* Status */}
        <div style={{ ...S.statusBar, background: isConnected ? 'rgba(46,213,115,.1)' : 'rgba(255,71,87,.1)',
                      border: `1px solid ${isConnected ? '#2ed573' : '#ff4757'}33` }}>
          <span style={{ color: isConnected ? '#2ed573' : '#ff4757', fontSize: 13, fontWeight: 600 }}>
            {isConnected ? '🟢 Fyers API Connected — Session Active' : '🔴 Not Connected — Login Required'}
          </span>
          {live?.token_expiry && (
            <span style={{ color: '#8899bb', fontSize: 11 }}>
              Token expires: {new Date(live.token_expiry).toLocaleTimeString('en-IN')}
            </span>
          )}
        </div>

        {/* Token persistence note */}
        <div style={S.infoBox}>
          <span style={{ color: '#00d4aa', fontSize: 12 }}>ℹ️</span>
          <span style={{ color: '#8899bb', fontSize: 12, lineHeight: 1.5 }}>
            Your access token is saved in the database. Closing and reopening the browser will
            auto-restore your session — no re-login needed until the token expires (~24 hours).
          </span>
        </div>

        {!isConnected && (
          <>
            {/* Mode selector */}
            <div style={S.modeRow}>
              {['totp','sms'].map(m => (
                <button key={m} onClick={() => { setMode(m); setOtpSent(false); setMsg(null) }}
                  style={{ ...S.modeBtn, ...(mode===m ? S.modeBtnActive : {}) }}>
                  {m === 'totp' ? '🔐 TOTP (Auto)' : '📱 SMS OTP'}
                </button>
              ))}
            </div>

            {mode === 'totp' && (
              <>
                <p style={S.hint}>Fully automatic — app generates TOTP from your secret key. One click, done.</p>
                <button onClick={doTOTP} disabled={loading} style={S.btnPrimary}>
                  {loading ? <Spinner /> : '⚡ Initiate Session via TOTP'}
                </button>
              </>
            )}

            {mode === 'sms' && !otpSent && (
              <>
                <p style={S.hint}>OTP will be sent to your registered Fyers mobile number.</p>
                <button onClick={sendOTP} disabled={loading} style={S.btnPrimary}>
                  {loading ? <Spinner /> : '📲 Send OTP'}
                </button>
              </>
            )}

            {mode === 'sms' && otpSent && (
              <>
                <p style={{ ...S.hint, color: '#2ed573' }}>✅ OTP sent! Enter it below.</p>
                <input value={otp} onChange={e => setOtp(e.target.value)} placeholder="Enter 6-digit OTP"
                  maxLength={6} style={S.otpInput} />
                <div style={{ display: 'flex', gap: 10 }}>
                  <button onClick={verifyOTP} disabled={loading || !otp} style={S.btnPrimary}>
                    {loading ? <Spinner /> : '✅ Verify & Connect'}
                  </button>
                  <button onClick={() => { setOtpSent(false); setMsg(null) }} style={S.btnSecondary}>
                    ← Resend
                  </button>
                </div>
              </>
            )}
          </>
        )}

        {isConnected && (
          <button onClick={doLogout} style={S.btnDanger}>🚪 Logout (Clear Session)</button>
        )}

        {msg && (
          <div style={{ ...S.msgBox, background: msg.ok ? 'rgba(46,213,115,.1)' : 'rgba(255,71,87,.1)',
                        border: `1px solid ${msg.ok ? '#2ed573' : '#ff4757'}44` }}>
            <span style={{ color: msg.ok ? '#2ed573' : '#ff4757' }}>{msg.text}</span>
          </div>
        )}
      </div>

      {/* Telegram commands info */}
      <div style={S.card}>
        <div style={S.title}>📱 Telegram Commands</div>
        <p style={{ color: '#8899bb', fontSize: 12, marginBottom: 16 }}>
          Send these commands to your bot. Only messages from your configured Chat ID are accepted.
        </p>
        <div style={S.cmdGrid}>
          {[
            ['START',  'Login + init + start strategy'],
            ['STOP',   'Close all positions + stop'],
            ['STATUS', 'Current P&L + positions report'],
            ['PAUSE',  'Stop new entries, keep positions'],
            ['RESUME', 'Resume new entries'],
            ['HELP',   'Show all commands'],
          ].map(([cmd, desc]) => (
            <div key={cmd} style={S.cmdRow}>
              <code style={S.cmd}>{cmd}</code>
              <span style={S.cmdDesc}>{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Spinner() {
  return <span style={{ display:'inline-block', width:14, height:14, border:'2px solid #ffffff33',
    borderTopColor:'#fff', borderRadius:'50%', animation:'spin 0.6s linear infinite' }} />
}

const S = {
  page:        { display:'flex', flexDirection:'column', gap:20, maxWidth:600 },
  card:        { background:'#0f1527', border:'1px solid #1e2d50', borderRadius:10, padding:24 },
  title:       { fontSize:16, fontWeight:600, color:'#e8edf5', marginBottom:16 },
  statusBar:   { padding:'10px 14px', borderRadius:8, marginBottom:16, display:'flex', justifyContent:'space-between', alignItems:'center' },
  infoBox:     { display:'flex', gap:10, padding:'10px 14px', background:'rgba(0,212,170,.06)',
                 border:'1px solid rgba(0,212,170,.15)', borderRadius:8, marginBottom:20 },
  modeRow:     { display:'flex', gap:8, marginBottom:16 },
  modeBtn:     { flex:1, padding:'8px 0', border:'1px solid #1e2d50', borderRadius:6, background:'transparent',
                 color:'#8899bb', fontSize:13, fontWeight:500 },
  modeBtnActive:{ background:'rgba(0,212,170,.1)', borderColor:'#00d4aa', color:'#00d4aa' },
  hint:        { color:'#8899bb', fontSize:12, marginBottom:14, lineHeight:1.5 },
  btnPrimary:  { width:'100%', padding:'11px', background:'#00d4aa', color:'#0a0e1a',
                 border:'none', borderRadius:7, fontSize:14, fontWeight:700,
                 display:'flex', alignItems:'center', justifyContent:'center', gap:8 },
  btnSecondary:{ padding:'11px 20px', background:'transparent', color:'#8899bb',
                 border:'1px solid #1e2d50', borderRadius:7, fontSize:13 },
  btnDanger:   { padding:'10px 20px', background:'rgba(255,71,87,.1)', color:'#ff4757',
                 border:'1px solid rgba(255,71,87,.3)', borderRadius:7, fontSize:13, fontWeight:600 },
  otpInput:    { width:'100%', padding:'10px 14px', background:'#151d35', border:'1px solid #1e2d50',
                 borderRadius:7, color:'#e8edf5', fontSize:20, letterSpacing:8, textAlign:'center',
                 marginBottom:12, outline:'none' },
  msgBox:      { marginTop:14, padding:'10px 14px', borderRadius:7, fontSize:13 },
  cmdGrid:     { display:'flex', flexDirection:'column', gap:8 },
  cmdRow:      { display:'flex', alignItems:'center', gap:14, padding:'6px 0',
                 borderBottom:'1px solid #1e2d5033' },
  cmd:         { fontSize:13, fontWeight:700, color:'#00d4aa', background:'rgba(0,212,170,.1)',
                 padding:'2px 10px', borderRadius:4, minWidth:80, textAlign:'center' },
  cmdDesc:     { color:'#8899bb', fontSize:12 },
}
