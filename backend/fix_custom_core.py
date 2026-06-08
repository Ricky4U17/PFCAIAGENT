c = open('app/main.py', encoding='utf-8').read()

c = c.replace(
    'custom_core: dict = None',
    'custom_core: dict = {}'
)

open('app/main.py', 'w', encoding='utf-8').write(c)
print('Done')