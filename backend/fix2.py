c = open('../frontend/src/components/ControllerHITL.tsx', encoding='utf-8').read()

old = "  analog: ["
new = """  analog: [
    {'name':'UCC28070A (TI)',     'why':'Dedicated 2-phase interleaved CCM PFC. 180 deg phase shift hardwired.'},
    {'name':'NCP1631 (ON Semi)', 'why':'2-phase interleaved PFC, programmable dead-time, OVP/OCP.'},
    {'name':'FAN9612 (ON Semi)', 'why':'Master-slave 2-phase interleaved PFC.'},
  ],
  analog_3phase: [
    {'name':'FAN9613 (ON Semi)', 'why':'Dedicated 3-phase interleaved CCM PFC. Built-in 120 deg phase shift. No external sync needed.'},
    {'name':'UCC28070A x3 + sync', 'why':'Three UCC28070A with external 120 deg RC phase-shift network.'},
  ],"""

c = c.replace(old, new, 1)

old2 = "const analogChips = isInterleaved ? CHIPS.analog : CHIPS.analog_single"
new2 = "const analogChips = nPhases === 3 ? CHIPS.analog_3phase : isInterleaved ? CHIPS.analog : CHIPS.analog_single"
c = c.replace(old2, new2)

open('../frontend/src/components/ControllerHITL.tsx', 'w', encoding='utf-8').write(c)
print('Done')