/**
 * SemiconductorSelection.tsx — Chapter 7: Semiconductor Selection (formation).
 *
 * Entry page for Chapter 7, reached from the Control Design page via the
 * "Select Semiconductors →" button once the control loop is designed. This is
 * the scaffold the chapter-7 selection flow (boost switches, diodes/SiC, gate
 * drive, thermal) will build on; it carries the approved upstream design forward.
 */
import React from 'react'
import { C, Btn, Card, SecHead } from './ui'
import type { CapacitorResult } from './Step15Capacitor'

interface Props {
  confirmedState:          Record<string, unknown>
  approvedInductorDesign:  Record<string, unknown>
  approvedCapacitorDesign: CapacitorResult | null
  onBack:    () => void
  onRestart: () => void
}

export const SemiconductorSelection: React.FC<Props> = ({
  confirmedState, approvedInductorDesign, approvedCapacitorDesign, onBack, onRestart,
}) => {
  const app = (confirmedState as any)?.intake?.application ?? {}
  const vout = Number(app.output_bus_voltage_v ?? 393.7)
  const poutHi = Number(app.output_power_w_high_line ?? 3600)

  const carry = [
    ['Bus voltage', `${vout.toFixed(0)} V`],
    ['High-line power', `${poutHi.toFixed(0)} W`],
    ['Per-phase inductance', `${Number((approvedInductorDesign as any)?.L_target_uH ?? 235).toFixed(0)} µH`],
    ['Bus capacitance', `${Number(approvedCapacitorDesign?.C_total_uF ?? 2200).toFixed(0)} µF`],
  ]

  return (
    <div style={{ maxWidth: 920, margin: '0 auto', padding: '8px 4px 28px' }}>
      <SecHead icon="🔌" label="Chapter 7 — Semiconductor Selection"
        sub="Boost switches, rectifiers, gate drive and thermal sizing" />

      <Card style={{ marginTop: 14 }}>
        <div style={{ fontSize: 13, color: C.text, lineHeight: 1.7 }}>
          The control loop is complete. Chapter 7 selects the power semiconductors for the
          2-phase interleaved boost stage — the main switches, the boost rectifiers (Si/SiC),
          gate-drive requirements and the thermal design — sized against the approved power-stage
          and control design carried forward below.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginTop: 16 }}>
          {carry.map(([k, v]) => (
            <div key={k} style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 8,
              padding: '10px 12px' }}>
              <div style={{ fontSize: 10, color: C.hint, textTransform: 'uppercase', letterSpacing: 0.5 }}>{k}</div>
              <div style={{ fontSize: 16, color: C.text, fontWeight: 600, fontFamily: 'IBM Plex Mono,monospace' }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16, fontSize: 11, color: C.muted, fontStyle: 'italic' }}>
          Selection workflow coming next: device shortlist → loss/thermal evaluation → gate-drive
          sizing → Chapter 7 report.
        </div>
      </Card>

      <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
        <Btn variant="ghost" onClick={onBack}>← Back to Control Design</Btn>
        <Btn variant="ghost" onClick={onRestart}>↺ New design</Btn>
      </div>
    </div>
  )
}
