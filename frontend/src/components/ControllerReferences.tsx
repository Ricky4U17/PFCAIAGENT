/**
 * ControllerReferences.tsx — live reference-citation panel for the control-design
 * flow (Step 16). Queries the local controller reference database
 * (POST /controller-db/query → backend/app/reference_agent.py) and surfaces the
 * most relevant, cited passages from the FAN9672 datasheet, app notes and the
 * shared control-loop-design theory. Auto-loads a starter set on mount; the
 * designer can also ask the database directly.
 */
import React, { useEffect, useState } from 'react'
import { C, Btn } from './ui'
import { controllerDbQuery, type RefPassage } from '../api/client'

const TOPICS: { label: string; q: string }[] = [
  { label: 'Voltage loop',   q: 'voltage error amplifier (VEA) loop compensation network poles zeros and component values' },
  { label: 'Current loop',   q: 'current loop crossover frequency RIC compensation and current sense gain' },
  { label: 'Multiplier/gain', q: 'multiplier input, current sense gain GMI and transconductance constants' },
  { label: 'Type II / III',  q: 'Type II and Type III compensator design equations and component selection' },
  { label: 'Pin functions',  q: 'FAN9672 pin functions and external component connections' },
]

interface Props { controller?: string }

export const ControllerReferences: React.FC<Props> = ({ controller = 'fan9672' }) => {
  const [open,     setOpen]     = useState(true)
  const [q,        setQ]        = useState('')
  const [passages, setPassages] = useState<RefPassage[]>([])
  const [loading,  setLoading]  = useState(false)
  const [err,      setErr]      = useState<string | null>(null)
  const [heading,  setHeading]  = useState('Key references for control-loop design')

  const run = async (question: string, label: string) => {
    setLoading(true); setErr(null); setHeading(label)
    try {
      const res = await controllerDbQuery({ question, controller, k: 6 })
      setPassages(res.passages)
    } catch (e) {
      setErr((e as Error).message ?? String(e)); setPassages([])
    } finally { setLoading(false) }
  }

  // Starter set: surface the canonical control-loop references on mount.
  useEffect(() => {
    run(TOPICS.map(t => t.q).join('; '), 'Key references for control-loop design')
  }, [controller])  // eslint-disable-line react-hooks/exhaustive-deps

  const onSearch = () => { if (q.trim()) run(q.trim(), `Results for “${q.trim()}”`) }

  return (
    <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, background: C.bg2,
      marginTop: 12, overflow: 'hidden' }}>
      {/* header */}
      <div onClick={() => setOpen(o => !o)}
        style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
          cursor: 'pointer', userSelect: 'none', borderBottom: open ? `1px solid ${C.border}` : 'none' }}>
        <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em',
          color: C.accent, fontWeight: 700 }}>📚 Controller references</span>
        <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono,monospace', color: C.muted }}>
          {controller.toUpperCase()} datasheet · app notes · control-loop theory
        </span>
        <span style={{ marginLeft: 'auto', color: C.hint, fontSize: 14 }}>{open ? '▾' : '▸'}</span>
      </div>

      {open && (
        <div style={{ padding: '12px 14px' }}>
          {/* search + topic chips */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') onSearch() }}
              placeholder="Ask the reference database… (e.g. how to set the current loop crossover)"
              style={{ flex: 1, minWidth: 240, background: C.bg3, color: C.text,
                border: `1px solid ${C.border}`, borderRadius: 8, padding: '7px 10px',
                fontSize: 12, fontFamily: 'IBM Plex Mono,monospace', outline: 'none' }} />
            <Btn variant="ghost" disabled={loading} onClick={onSearch}>
              {loading ? '⏳' : '🔍 Search'}
            </Btn>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
            {TOPICS.map(t => (
              <span key={t.label} onClick={() => run(t.q, t.label + ' references')}
                style={{ fontSize: 10, fontFamily: 'IBM Plex Mono,monospace', color: C.muted,
                  border: `1px solid ${C.border}`, borderRadius: 999, padding: '3px 10px',
                  cursor: 'pointer', background: C.bg3 }}>{t.label}</span>
            ))}
          </div>

          {/* results */}
          <div style={{ fontSize: 10, color: C.hint, fontFamily: 'IBM Plex Mono,monospace',
            textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>{heading}</div>

          {err && (
            <div style={{ fontSize: 12, color: '#c0392b', background: '#fdf2f2',
              border: '1px solid #e8b4b8', borderRadius: 8, padding: '8px 10px' }}>
              ⚠ Reference DB error: {err}
            </div>
          )}
          {!err && !loading && passages.length === 0 && (
            <div style={{ fontSize: 12, color: C.muted }}>No matching passages.</div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {passages.map(p => (
              <div key={p.rank + p.citation} style={{ border: `0.5px solid ${C.border}`,
                borderRadius: 8, padding: '8px 10px', background: C.bg3 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, fontFamily: 'IBM Plex Mono,monospace',
                    color: C.accent, background: C.accentL, borderRadius: 5, padding: '1px 7px' }}>
                    {p.citation}
                  </span>
                  <span style={{ fontSize: 11, color: C.muted }}>{p.title}</span>
                  {p.collection && (
                    <span style={{ fontSize: 9, color: C.hint, fontFamily: 'IBM Plex Mono,monospace' }}>
                      · shared theory
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11.5, color: C.text, lineHeight: 1.5, marginTop: 5 }}>
                  {p.snippet}
                </div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10, color: C.hint, marginTop: 10, lineHeight: 1.5 }}>
            Passages are retrieved from the local controller reference database
            (datasheet, application notes and control-loop-design theory). Citations are
            <code style={{ margin: '0 3px' }}>DOC&nbsp;page</code> (PDF) or
            <code style={{ margin: '0 3px' }}>DOC&nbsp;§n</code> (report/tool).
          </div>
        </div>
      )}
    </div>
  )
}
