c = open('app/main.py', encoding='utf-8').read()

old = '''        sup_tag = (supplier.lower().replace(" ","_")
                   .replace("magnetics_inc","magnetics_inc")
                   .replace("ferroxcube","ferroxcube").replace("tdk","tdk"))'''

new = '        sup_tag = supplier.lower().replace(" ","_").replace(".","").replace(",","")'

c = c.replace(old, new)
open('app/main.py', 'w', encoding='utf-8').write(c)
print('Done' if 'replace(".","")' in c else 'FAILED - pattern not found')