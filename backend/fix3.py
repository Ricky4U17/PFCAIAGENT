c = open('../frontend/src/components/ControllerHITL.tsx', encoding='utf-8').read()

# Find and replace the entire CHIPS block
old = "const CHIPS: Record<string,{name:string;why:string}[]> = {"
end_marker = "export const ControllerHITL"

start = c.find(old)
end = c.find(end_marker)

new_chips = """const CHIPS: Record<string,{name:string;why:string}[]> = {
  digital: [
    {name:'TI C2000',            why:'Purpose-built DSP for PFC/motor. Adaptive dead-time, CLA co-processor, Medical ecosystem.'},
    {name:'STM32G4 + MCSDK',     why:'170 MHz Cortex-M4 + FPU. TIM_HR for high-res PWM. Cost-effective for 2-phase interleaved.'},
    {name:'dsPIC33CK',           why:'Dual-core DSC. Motor + PFC on one die. Compact Medical board designs.'},
  ],
  analog: [
    {name:'UCC28070A (TI)',       why:'Dedicated 2-phase interleaved CCM PFC. 180 deg phase shift hardwired. SiC-capable gate drive.'},
    {name:'NCP1631 (ON Semi)',    why:'2-phase interleaved PFC, programmable dead-time, OVP/OCP. Medical supply chain.'},
    {name:'FAN9612 (ON Semi)',    why:'Master-slave 2-phase interleaved PFC. Strong Medical leakage track record.'},
  ],
  analog_3phase: [
    {name:'FAN9613 (ON Semi)',    why:'Dedicated 3-phase interleaved CCM PFC. Built-in 120 deg phase shift. No external sync network needed.'},
    {name:'UCC28070A x3 + sync', why:'Three UCC28070A with external 120 deg RC phase-shift network. More complex but available.'},
  ],
  analog_single: [
    {name:'TI UC3854',           why:'Classic single-phase CCM PFC. Mature, long supply history.'},
    {name:'Infineon ICE3PCS01G', why:'Single-phase CCM with integrated gate drive and OVP.'},
    {name:'ON NCP1654',          why:'Fixed-frequency CCM with burst mode for wide load range.'},
  ],
}
"""

c = c[:start] + new_chips + c[end:]
open('../frontend/src/components/ControllerHITL.tsx', 'w', encoding='utf-8').write(c)
print('Done')