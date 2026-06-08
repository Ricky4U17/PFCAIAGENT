c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

c = c.replace(
    'custom_core: cc,',
    'custom_core: cc ?? {},'
)

open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done')