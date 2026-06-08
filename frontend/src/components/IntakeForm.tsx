import React, { useState } from 'react'
import { Card, SecHead, Field, Inp, Sel, Btn, Chip, Spinner, C } from './ui'

export interface IntakeData {
  application: {
    vin_rms_min: number; vin_rms_max: number
    nominal_line_frequency_hz: number | null
    universal_input_frequency: boolean
    output_bus_voltage_v: number; output_power_w_high_line: number
    output_power_w_low_line: number; power_factor_target: number
    efficiency_target_percent: number; hold_up_time_ms: number
    dc_bus_voltage_ripple_pk_pk_v: number
  }
  thermal: {
    cooling_type: string; ambient_temp_c_max: number
    max_temp_rise_c: number; hotspot_limit_c: number
  }
  control: { control_preference: string }
  business: {
    cost_priority: number; efficiency_priority: number
    power_density_priority: number; implementation_risk_priority: number
    preferred_switch_technology: string[]
  }
  mechanical: { power_density_priority: number }
  compliance: {
    application_class: string; conducted_emi_class: string
    harmonics_class: string; leakage_current_limit_ua: number
    surge_level: string; eft_level: string
    magnetic_field_level: string; voltage_dips_class: string
    semi_f47: boolean
  }
  supply: { preferred_vendors: string[]; avoid_vendors: string[] }
}

const DEFAULT: IntakeData = {
  application: {
    vin_rms_min: 90, vin_rms_max: 264,
    nominal_line_frequency_hz: 60, universal_input_frequency: true,
    output_bus_voltage_v: 394, output_power_w_high_line: 3600,
    output_power_w_low_line: 1700, power_factor_target: 0.99,
    efficiency_target_percent: 98, hold_up_time_ms: 20,
    dc_bus_voltage_ripple_pk_pk_v: 20,
  },
  thermal: { cooling_type: 'fan_cooled', ambient_temp_c_max: 50, max_temp_rise_c: 45, hotspot_limit_c: 110 },
  control: { control_preference: 'Recommend' },
  business: { cost_priority: 7, efficiency_priority: 9, power_density_priority: 8, implementation_risk_priority: 6, preferred_switch_technology: ['Si','SiC'] },
  mechanical: { power_density_priority: 8 },
  compliance: {
    application_class: 'Industrial', conducted_emi_class: 'FCC Class B',
    harmonics_class: 'EN61000-3-2', leakage_current_limit_ua: 3500,
    surge_level: '1kV L-L / 2kV L-G (Class A)',
    eft_level: 'Level 3 — 2 kV (EN 61000-4-4)',
    magnetic_field_level: 'Level 4 — 30 A/m (EN 61000-4-8)',
    voltage_dips_class: 'Class 3 (EN 61000-4-11)',
    semi_f47: true,
  },
  supply: { preferred_vendors: [], avoid_vendors: [] },
}

const LEAKAGE_BY_CLASS: Record<string,number> = {
  Industrial:3500, 'IT Equipment':3500, Medical:500, Telecom:3500, 'EV Charge':3500,
}

function setDeep(obj: IntakeData, path: string, val: unknown): IntakeData {
  const n = JSON.parse(JSON.stringify(obj)) as IntakeData
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const keys = path.split('.'); let cur: any = n
  for (let i = 0; i < keys.length - 1; i++) cur = cur[keys[i]]
  cur[keys[keys.length - 1]] = val
  return n
}

interface Props { onSubmit: (d: IntakeData) => void; loading: boolean }

export const IntakeForm: React.FC<Props> = ({ onSubmit, loading }) => {
  const [d, setD] = useState<IntakeData>(DEFAULT)
  const [lineFreq, setLineFreq] = useState<'50'|'60'|'400'|'univ'>('univ')

  const set = (path: string, val: unknown) => setD(prev => setDeep(prev, path, val))

  const handleLineFreq = (f: '50'|'60'|'400'|'univ') => {
    setLineFreq(f)
    if (f === 'univ') {
      set('application.nominal_line_frequency_hz', 60.0)
      set('application.universal_input_frequency', true)
    } else {
      set('application.nominal_line_frequency_hz', Number(f))
      set('application.universal_input_frequency', false)
    }
  }

  const handleAppClass = (cls: string) => {
    set('compliance.application_class', cls)
    const locked = LEAKAGE_BY_CLASS[cls] ?? 3500
    set('compliance.leakage_current_limit_ua', locked)
  }

  const toggleTech = (t: string) => {
    const cur = d.business.preferred_switch_technology
    set('business.preferred_switch_technology', cur.includes(t) ? cur.filter(x => x !== t) : [...cur, t])
  }

  const isMedical = d.compliance.application_class === 'Medical'

  const FreqBtn: React.FC<{ id: '50'|'60'|'400'|'univ'; label: string; sub: string }> = ({ id, label, sub }) => (
    <div onClick={() => handleLineFreq(id)} style={{
      flex: 1, padding: '10px 8px', borderRadius: 8, cursor: 'pointer', textAlign: 'center',
      background: lineFreq === id ? C.accentL : C.bg3,
      border: `1px solid ${lineFreq === id ? C.accent : C.border2}`,
      color: lineFreq === id ? C.accent : C.muted, transition: 'all .15s', userSelect: 'none',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'IBM Plex Mono,monospace' }}>{label}</div>
      <div style={{ fontSize: 10, color: lineFreq === id ? C.accent : C.hint, marginTop: 2 }}>{sub}</div>
    </div>
  )

  const SliderField: React.FC<{ label: string; path: string; min?: number; max?: number }> = ({ label, path, min=1, max=10 }) => {
    const val = path.split('.').reduce((o: unknown, k) => (o as Record<string,unknown>)[k], d) as number
    return (
      <Field label={`${label}: ${val}/10`}>
        <input type="range" min={min} max={max} value={val}
          onChange={e => set(path, Number(e.target.value))}
          style={{ width: '100%', accentColor: C.accent } as React.CSSProperties} />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: C.hint, marginTop: 2 }}>
          <span>{min} — low priority</span><span>{max} — critical</span>
        </div>
      </Field>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Design intake</div>

      {/* ── Section 1: Electrical ── */}
      <Card>
        <SecHead icon="⚡" label="Electrical requirements" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '0 24px' }}>
          <Field label="Vin min (Vrms)">
            <Inp value={d.application.vin_rms_min} min={47} max={120}
              onChange={v => set('application.vin_rms_min', v)} />
          </Field>
          <Field label="Vin max (Vrms)">
            <Inp value={d.application.vin_rms_max} min={200} max={277}
              onChange={v => set('application.vin_rms_max', v)} />
          </Field>
          <Field label="Output bus voltage (V)">
            <Inp value={d.application.output_bus_voltage_v} min={200} max={800}
              onChange={v => set('application.output_bus_voltage_v', v)} />
          </Field>
          <Field label="Bus voltage ripple pk-pk (V)">
            <Inp value={d.application.dc_bus_voltage_ripple_pk_pk_v} min={1} max={50}
              onChange={v => set('application.dc_bus_voltage_ripple_pk_pk_v', v)} />
          </Field>
          {/* CORRECTION 1a: Renamed to "Output power — High Line" */}
          <Field label="Output power — High Line (W)">
            <Inp value={d.application.output_power_w_high_line} min={100} max={20000}
              onChange={v => set('application.output_power_w_high_line', v)} />
          </Field>
          <Field label="Output power — Low Line (W)">
            <Inp value={d.application.output_power_w_low_line} min={100} max={20000}
              onChange={v => set('application.output_power_w_low_line', v)} />
          </Field>
          <Field label="Power factor target">
            <Inp value={d.application.power_factor_target} min={0.9} max={1} step={0.001}
              onChange={v => set('application.power_factor_target', v)} />
          </Field>
          <Field label="Efficiency target (%)">
            <Inp value={d.application.efficiency_target_percent} min={85} max={99.9} step={0.1}
              onChange={v => set('application.efficiency_target_percent', v)} />
          </Field>
          <Field label="Hold-up time (ms)">
            <Inp value={d.application.hold_up_time_ms} min={0} max={100}
              onChange={v => set('application.hold_up_time_ms', v)} />
          </Field>
        </div>

        {/* CORRECTION 1b: 4-option line frequency selector including Universal 47–63 Hz */}
        <Field label="Line frequency">
          <div style={{ display: 'flex', gap: 8 }}>
            <FreqBtn id="50"   label="50 Hz"    sub="EU / Asia" />
            <FreqBtn id="60"   label="60 Hz"    sub="US / Japan" />
            <FreqBtn id="400"  label="400 Hz"   sub="Aviation" />
            <FreqBtn id="univ" label="47–63 Hz" sub="Universal input" />
          </div>
          {lineFreq === 'univ' && (
            <div style={{ marginTop: 8, padding: '7px 11px', background: C.accentL,
              border: `1px solid ${C.accent}44`, borderRadius: 7, fontSize: 12, color: C.accent,
              fontFamily: 'IBM Plex Mono,monospace' }}>
              ★ Universal input selected — backend will design for full 47–63 Hz range
            </div>
          )}
        </Field>
      </Card>

      {/* ── Section 2: Thermal ── */}
      <Card>
        <SecHead icon="🌡️" label="Thermal" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '0 24px' }}>
          <Field label="Cooling type">
            <Sel value={d.thermal.cooling_type} onChange={v => set('thermal.cooling_type', v)}
              options={[
                {value:'fan_cooled',label:'Fan cooled'},
                {value:'natural_convection',label:'Natural convection'},
                {value:'liquid_cooled',label:'Liquid cooled'},
                {value:'conduction_cooled',label:'Conduction cooled'},
              ]} />
          </Field>
          <Field label="Max ambient (°C)">
            <Inp value={d.thermal.ambient_temp_c_max} min={20} max={85}
              onChange={v => set('thermal.ambient_temp_c_max', v)} />
          </Field>
          <Field label="Max temp rise (°C)">
            <Inp value={d.thermal.max_temp_rise_c} min={10} max={80}
              onChange={v => set('thermal.max_temp_rise_c', v)} />
          </Field>
          <Field label="Hotspot limit (°C)">
            <Inp value={d.thermal.hotspot_limit_c} min={60} max={150}
              onChange={v => set('thermal.hotspot_limit_c', v)} />
          </Field>
        </div>
        <div style={{ padding: '8px 12px', background: C.bg3, borderRadius: 7, fontSize: 12,
          color: C.hint, fontFamily: 'IBM Plex Mono,monospace' }}>
          Hotspot budget: {d.thermal.hotspot_limit_c - d.thermal.ambient_temp_c_max} °C
          &nbsp;(limit − ambient)
          <span style={{ color: d.thermal.hotspot_limit_c - d.thermal.ambient_temp_c_max < 40
            ? C.amber : C.green, marginLeft: 8 }}>
            {d.thermal.hotspot_limit_c - d.thermal.ambient_temp_c_max < 40 ? '⚠ tight margin' : '✓ adequate'}
          </span>
        </div>
      </Card>

      {/* ── Section 3: Control & Business ── */}
      <Card>
        <SecHead icon="🎛️" label="Control & business preferences" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '0 24px' }}>
          <Field label="Control preference">
            <Sel value={d.control.control_preference} onChange={v => set('control.control_preference', v)}
              options={['Analog','Digital',{value:'Digital ARM',label:'Digital ARM Based Controller'},'Recommend']} />
          </Field>
          {/* CORRECTION 2: Application class triggers leakage auto-set for Medical */}
          <Field label="Application class">
            <Sel value={d.compliance.application_class} onChange={handleAppClass}
              options={['Industrial','IT Equipment','Medical','Telecom','EV Charge']} />
          </Field>
          <SliderField label="Cost priority"           path="business.cost_priority" />
          <SliderField label="Efficiency priority"     path="business.efficiency_priority" />
          <SliderField label="Power density priority"  path="business.power_density_priority" />
          <SliderField label="Implementation risk"     path="business.implementation_risk_priority" />
        </div>
        <Field label="Switch technology preference">
          <div style={{ display: 'flex', gap: 8 }}>
            {['Si','SiC','GaN'].map(t => (
              <Chip key={t} label={t}
                on={d.business.preferred_switch_technology.includes(t)}
                onClick={() => toggleTech(t)} />
            ))}
          </div>
          {!d.business.preferred_switch_technology.some(t => ['SiC','GaN'].includes(t)) && (
            <div style={{ marginTop: 8, fontSize: 12, color: C.amber, fontFamily: 'IBM Plex Mono,monospace' }}>
              ⚠ No WBG selected — totem-pole topologies will be penalised in scoring
            </div>
          )}
        </Field>
      </Card>

      {/* ── Section 4: Compliance ── */}
      <Card>
        <SecHead icon="📋" label="Compliance" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '0 24px' }}>
          <Field label="Conducted EMI class">
            <Sel value={d.compliance.conducted_emi_class} onChange={v => set('compliance.conducted_emi_class', v)}
              options={['FCC Class B','FCC Class A','CISPR 22 Class B','CISPR 22 Class A']} />
          </Field>
          <Field label="Harmonics class">
            <Sel value={d.compliance.harmonics_class} onChange={v => set('compliance.harmonics_class', v)}
              options={['EN61000-3-2','EN61000-3-12']} />
          </Field>
          <Field label={`Leakage current limit (µA)${isMedical ? ' 🔒' : ''}`}>
            <Inp value={d.compliance.leakage_current_limit_ua} min={100} max={10000}
              disabled={isMedical} onChange={v => set('compliance.leakage_current_limit_ua', v)} />
            {isMedical && (
              <div style={{ marginTop: 6, padding: '6px 10px', borderRadius: 6,
                background: C.amberL, border: `1px solid ${C.amber}55`,
                fontSize: 11, color: C.amber, fontFamily: 'IBM Plex Mono,monospace',
                display: 'flex', alignItems: 'center', gap: 6 }}>
                🔒 Auto-set to 500 µA — IEC 60601-1 Medical requirement
              </div>
            )}
          </Field>
          <Field label="Surge level (IEC 61000-4-5)">
            <Sel value={d.compliance.surge_level} onChange={v => set('compliance.surge_level', v)}
              options={[
                '0.5kV L-L / 1kV L-G (Class A)',
                '1kV L-L / 2kV L-G (Class A)',
                '2kV L-L / 4kV L-G (Class B)',
                '4kV L-L / 8kV L-G (Class B)',
              ]} />
          </Field>
          <Field label="EFT (IEC 61000-4-4)">
            <Sel value={d.compliance.eft_level} onChange={v => set('compliance.eft_level', v)}
              options={[
                'Level 1 — 0.5 kV',
                'Level 2 — 1 kV',
                'Level 3 — 2 kV (EN 61000-4-4)',
                'Level 4 — 4 kV',
              ]} />
          </Field>
          <Field label="Magnetic field (IEC 61000-4-8)">
            <Sel value={d.compliance.magnetic_field_level} onChange={v => set('compliance.magnetic_field_level', v)}
              options={[
                'Level 1 — 1 A/m',
                'Level 2 — 3 A/m',
                'Level 3 — 10 A/m',
                'Level 4 — 30 A/m (EN 61000-4-8)',
                'Level 5 — 100 A/m',
              ]} />
          </Field>
          <Field label="Voltage dips (IEC 61000-4-11)">
            <Sel value={d.compliance.voltage_dips_class} onChange={v => set('compliance.voltage_dips_class', v)}
              options={[
                'Class 1 (EN 61000-4-11)',
                'Class 2 (EN 61000-4-11)',
                'Class 3 (EN 61000-4-11)',
              ]} />
          </Field>
        </div>
        <Field label="SEMI F47 (semiconductor equipment ride-through)">
          <div style={{ display: 'flex', gap: 10 }}>
            {[{v:false,l:'Not required'},{v:true,l:'Required — SEMI F47 compliant'}].map(opt => (
              <div key={String(opt.v)} onClick={() => set('compliance.semi_f47', opt.v)}
                style={{ flex: 1, padding: '8px 14px', borderRadius: 8, cursor: 'pointer',
                  border: `1.5px solid ${d.compliance.semi_f47 === opt.v ? C.accent : C.border}`,
                  background: d.compliance.semi_f47 === opt.v ? C.accentL : C.bg3,
                  fontSize: 12, color: d.compliance.semi_f47 === opt.v ? C.accent : C.muted,
                  fontFamily: 'IBM Plex Mono,monospace' }}>
                {d.compliance.semi_f47 === opt.v ? '● ' : '○ '}{opt.l}
              </div>
            ))}
          </div>
        </Field>
      </Card>

      <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 8 }}>
        <Btn onClick={() => onSubmit(d)} disabled={loading}>
          {loading
            ? <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ display:'inline-block',width:14,height:14,border:`2px solid ${C.border2}`,
                  borderTopColor:'#fff',borderRadius:'50%',animation:'spin .6s linear infinite'}}/> Running topology selection…
              </span>
            : 'Run topology selection →'}
        </Btn>
      </div>
    </div>
  )
}
