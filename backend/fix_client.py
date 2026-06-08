c = open('../frontend/src/api/client.ts', encoding='utf-8').read()

c = c.replace(
    "post(`/mode-b/step7/suppliers?material_type=${material_type}`, null, 'GET')",
    "get(`/mode-b/step7/suppliers?material_type=${material_type}`)"
)

open('../frontend/src/api/client.ts', 'w', encoding='utf-8').write(c)
print('Done')