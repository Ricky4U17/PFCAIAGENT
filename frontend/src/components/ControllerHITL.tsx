import React, { useState } from 'react'
import { Card, SecHead, Btn, Badge, C } from './ui'
import type { ControllerStrategy } from '../api/client'

interface Props {
  strategy: ControllerStrategy
  selectedTopology: string
  isInterleaved: boolean
  appClass?: string
  nPhases?: number
  onSubmit: (fb: { approved: boolean; controller_mode: string }) => void
  onBack: () => void
  loading: boolean
}

const CHIPS: Record<string, { name: string; why: string }[]> = {
  digital: [
    { name: 'TI C2000',        why: 'Purpose-built DSP for PFC/motor. Adaptive dead-time, CLA co-processor, Medical ecosystem.' },
    { name: 'STM32G4 + MCSDK', why: '170 MHz Cortex-M4 + FPU. TIM_HR for high-res PWM. Cost-effective for 2-phase interleaved.' },
    { name: 'dsPIC33CK',       why: 'Dual-core DSC. Motor + PFC on one die. Compact Medical board designs.' },
  ],
  digital_arm: [
    { name: 'TI UCD3138',      why: 'Dedicated ARM Cortex-M3 digital power controller. On-chip PWM, ADC, and hardware compensators. Purpose-built for PFC and DC-DC.' },
    { name: 'UCD3138A',        why: 'Enhanced variant with 4 independent loops. Ideal for interleaved PFC with per-phase current balancing and PMBus telemetry.' },
  ],
  analog: [
    { name: 'UCC28070A (TI)',   why: 'Dedicated 2-phase interleaved CCM PFC. 180 deg phase shift hardwired. SiC-capable gate drive.' },
    { name: 'NCP1631 (ON Semi)',why: '2-phase interleaved PFC, programmable dead-time, OVP/OCP. Medical supply chain.' },
    { name: 'FAN9612 (ON Semi)',why: 'Master-slave 2-phase interleaved PFC. Strong Medical leakage track record.' },
  ],
  analog_3phase: [
    { name: 'FAN9613 (ON Semi)',why: 'Dedicated 3-phase interleaved CCM PFC. Built-in 120 deg phase shift. No external sync network needed.' },
    { name: 'UCC28070A x3 + sync', why: 'Three UCC28070A with external 120 deg RC phase-shift network. More complex but available.' },
  ],
  analog_single: [
    { name: 'TI UC3854',             why: 'Classic single-phase CCM PFC. Mature, long supply history.' },
    { name: 'Infineon ICE3PCS01G',   why: 'Single-phase CCM with integrated gate drive and OVP.' },
    { name: 'ON NCP1654',            why: 'Fixed-frequency CCM with burst mode for wide load range.' },
  ],
}

const MODE_META: Record<string, { icon: string; label: string; desc: string; color: string; bgActive: string }> = {
  digital: {
    icon: '🖥', label: 'Digital',
    desc: 'DSP or MCU. Adaptive dead-time, per-phase balancing, real-time telemetry.',
    color: C.accent, bgActive: C.accentL,
  },
  digital_arm: {
    icon: '⚙️', label: 'Digital ARM Controller',
    desc: 'ARM Cortex-M3 dedicated power controller (UCD3138). On-chip hardware compensators, PMBus, purpose-built for PFC.',
    color: C.teal, bgActive: C.tealL,
  },
  analog: {
    icon: '🔧', label: 'Analog',
    desc: 'Fixed-freq IC controller. No firmware required.',
    color: C.green, bgActive: C.greenL,
  },
}

const ctrlLabel = (m: string) =>
  m === 'digital_arm' ? 'Digital ARM Controller' : m === 'analog' ? 'Analog' : 'Digital'

export const ControllerHITL: React.FC<Props> = ({
  strategy, selectedTopology, isInterleaved, appClass, nPhases, onSubmit, onBack, loading,
}) => {
  // If intake preference was "Recommend", start with nothing selected.
  // Otherwise use the backend's recommended mode (which reflects the intake preference).
  const initialSel = strategy.stated_control_preference === 'Recommend' ? '' : strategy.recommended_controller_mode
  const [sel, setSel] = useState(initialSel)

  const isMedical = appClass === 'Medical'
  const isInterl  = isInterleaved || (selectedTopology || '').toLowerCase().includes('interleaved')
  const analogChips = nPhases === 3 ? CHIPS.analog_3phase : isInterl ? CHIPS.analog : CHIPS.analog_single
  const showInterleavedNote = isInterl && sel === 'analog'

  const getChips = (m: string) =>
    m === 'digital' ? CHIPS.digital : m === 'digital_arm' ? CHIPS.digital_arm : analogChips

  return (
    <div>
      <div style={{ fontSize: 20, fontWeight: 500, marginBottom: 3 }}>Controller mode</div>
      <div style={{ fontSize: 13, color: C.muted, marginBottom: 18 }}>
        <strong>{selectedTopology.replace(/_/g, ' ')}</strong>
      </div>

      <Card style={{ marginBottom: 14 }}>
        <SecHead icon="💡" label="Reasoning" />
        {strategy.reasoning.map((r, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12,
            color: i === strategy.reasoning.length - 1 ? C.accent : C.muted, marginBottom: 5, lineHeight: 1.45 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', flexShrink: 0, marginTop: 5, background: C.accent }} />
            {r}
          </div>
        ))}
        {isMedical && (
          <div style={{ marginTop: 10, padding: '10px 13px', background: C.accentL, borderRadius: 7, fontSize: 12, color: C.muted, lineHeight: 1.5 }}>
            <strong style={{ color: C.accent }}>Medical class:</strong> Digital enables
            (a) real-time leakage monitoring via ADC,
            (b) adaptive EMI notch filter coefficients within tight Y-cap budget,
            (c) IEC 60601-1 safety log / fault register in firmware.
          </div>
        )}
      </Card>

      {showInterleavedNote && (
        <Card style={{ background: C.amberL, border: `1px solid ${C.amber}55`, marginBottom: 14 }}>
          <div style={{ fontWeight: 500, fontSize: 13, color: C.amber, marginBottom: 8 }}>
            ⚠ Analog controller IC update for interleaved operation
          </div>
          <div style={{ fontSize: 12, color: C.muted, marginBottom: 10, lineHeight: 1.55 }}>
            Single-phase analog ICs each control one phase only. For 2-phase interleaved PFC use a dedicated multi-phase IC with built-in 180° phase shift:
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            {CHIPS.analog.map(c => (
              <div key={c.name} style={{ background: C.bg3, borderRadius: 6, padding: '9px 11px', border: `0.5px solid ${C.border}` }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: C.accent, marginBottom: 3 }}>{c.name}</div>
                <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.4 }}>{c.why}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Selection hint when Recommend was chosen */}
      {strategy.stated_control_preference === 'Recommend' && !sel && (
        <div style={{ padding: '10px 14px', background: C.bg3, borderRadius: 8, marginBottom: 14,
          fontSize: 12, color: C.muted, border: `0.5px solid ${C.border}` }}>
          Select the Control Method
        </div>
      )}

      <Card>
        <SecHead icon="🔌" label="Select control mode" />

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {(['digital', 'digital_arm', 'analog'] as const).map(m => {
            const isSel  = sel === m
            const isRec  = strategy.recommended_controller_mode === m
            const meta   = MODE_META[m]
            const chips  = getChips(m)
            return (
              <div key={m} data-testid="gate-option" onClick={() => setSel(m)}
                style={{ borderRadius: 10, border: `2px solid ${isSel ? meta.color : C.border}`,
                  background: isSel ? meta.bgActive : C.bg3,
                  padding: '16px 18px', cursor: 'pointer', flex: '1 1 220px',
                  transition: 'all .2s', position: 'relative', minWidth: 200 }}>
                {isRec && (
                  <div style={{ position: 'absolute', top: 10, right: 10, fontSize: 10, fontWeight: 500,
                    padding: '2px 7px', borderRadius: 4, background: meta.color,
                    color: m === 'analog' ? '#0a2a20' : '#fff' }}>
                    ★ Recommended
                  </div>
                )}
                <div style={{ fontSize: 28, marginBottom: 8 }}>{meta.icon}</div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, color: isSel ? meta.color : C.muted }}>
                  {meta.label}
                </div>
                <div style={{ fontSize: 11, color: isSel ? C.muted : C.hint, lineHeight: 1.5, marginBottom: 12 }}>
                  {meta.desc}
                </div>
                <div style={{ textAlign: 'left' }}>
                  {chips.map(c => (
                    <div key={c.name} style={{ display: 'flex', gap: 7, marginBottom: 5 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, minWidth: 120, color: isSel ? meta.color : C.muted, flexShrink: 0 }}>
                        {c.name}
                      </div>
                      <div style={{ fontSize: 10, color: C.hint, lineHeight: 1.4 }}>{c.why}</div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          paddingTop: 12, borderTop: `0.5px solid ${C.border}`, marginTop: 14, flexWrap: 'wrap', gap: 10 }}>
          <div>
            <div style={{ fontSize: 11, color: C.hint }}>Selected control mode</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: sel ? MODE_META[sel]?.color ?? C.accent : C.hint }}>
              {sel ? ctrlLabel(sel) : '— select one —'}
            </div>
            {showInterleavedNote && (
              <div style={{ fontSize: 11, color: C.amber, marginTop: 3 }}>⚠ Use UCC28070A / NCP1631 / FAN9612</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn variant="ghost" onClick={onBack} disabled={loading}>← Back</Btn>
            <Btn variant="primary"
              onClick={() => onSubmit({ approved: true, controller_mode: sel })}
              disabled={loading || !sel}>
              {loading ? 'Processing…' : 'Approve →'}
            </Btn>
          </div>
        </div>
      </Card>
    </div>
  )
}
