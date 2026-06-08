c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

old = "      const d = await step7RunSizing({"
new = """      const sizingReq = {"""

old2 = """      }) as any"""
new2 = """      }
      console.log('Sending to run-sizing:', JSON.stringify(sizingReq, null, 2))
      const d = await step7RunSizing(sizingReq) as any"""

c = c.replace(old, new, 1)
c = c.replace(old2, new2, 1)
open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done')