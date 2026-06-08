c = open('../frontend/src/components/Step7Wizard.tsx', encoding='utf-8').read()

# Fix custom_core null
c = c.replace('custom_core: cc ?? {}', 'custom_core: cc ?? undefined')
c = c.replace('custom_core: cc,', 'custom_core: cc ?? undefined,')

# Fix n_top back to 5
c = c.replace('n_top:1,', 'n_top:5,')

open('../frontend/src/components/Step7Wizard.tsx', 'w', encoding='utf-8').write(c)
print('Done')