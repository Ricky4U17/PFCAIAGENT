c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

# Fix: extract result from top.result not top directly
old = "      const top = d.top_5?.[0] ?? null"
new = "      const top = d.top_5?.[0]?.result ?? null"

c = c.replace(old, new)
open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done' if old in open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read() == False else 'Fixed')