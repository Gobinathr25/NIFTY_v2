import { useState, useEffect, useRef, useCallback } from 'react'

const API = import.meta.env.VITE_API_URL || ''
const WS  = API.replace('http','ws').replace('https','wss')

export function useWebSocket() {
  const [data,       setData]       = useState(null)
  const [connected,  setConnected]  = useState(false)
  const wsRef = useRef(null)
  const retryRef = useRef(null)

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(`${WS}/ws`)
      wsRef.current = ws

      ws.onopen    = () => { setConnected(true); clearTimeout(retryRef.current) }
      ws.onmessage = (e) => { try { setData(JSON.parse(e.data)) } catch{} }
      ws.onclose   = () => {
        setConnected(false)
        retryRef.current = setTimeout(connect, 3000)
      }
      ws.onerror   = () => ws.close()
    } catch(e) {
      retryRef.current = setTimeout(connect, 3000)
    }
  }, [])

  useEffect(() => { connect(); return () => { wsRef.current?.close(); clearTimeout(retryRef.current) } }, [connect])
  return { data, connected }
}

export async function api(path, method='GET', body=null) {
  const opts = { method, headers: {'Content-Type':'application/json'} }
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(`${API}${path}`, opts)
  const json = await res.json()
  if (!res.ok) throw new Error(json.detail || 'Request failed')
  return json
}
