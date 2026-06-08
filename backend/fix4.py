c = open('../frontend/src/components/ControllerHITL.tsx', encoding='utf-8').read()

old = "const analogChips = nPhases === 3 ? CHIPS.analog_3phase : isInterleaved ? CHIPS.analog : CHIPS.analog_single"

new = "const isInterl = isInterleaved || (selectedTopology || '').toLowerCase().includes('interleaved')\n  const analogChips = nPhases === 3 ? CHIPS.analog_3phase : isInterl ? CHIPS.analog : CHIPS.analog_single"

c = c.replace(old, new)
open('../frontend/src/components/ControllerHITL.tsx', 'w', encoding='utf-8').write(c)
print('Done')