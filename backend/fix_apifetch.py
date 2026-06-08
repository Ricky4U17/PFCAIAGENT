c = open('../frontend/src/api/client.ts', encoding='utf-8').read()

# Replace all apiFetch calls with correct function
c = c.replace("apiFetch('/mode-b/step7/material-comparison', null, 'GET')", 
              "get('/mode-b/step7/material-comparison')")

c = c.replace("apiFetch(`/mode-b/step7/suppliers?material_type=${material_type}`, null, 'GET')",
              "get(`/mode-b/step7/suppliers?material_type=${material_type}`)")

# Replace any remaining apiFetch with post
c = c.replace('apiFetch(', 'post(')

open('../frontend/src/api/client.ts', 'w', encoding='utf-8').write(c)
print('Done')
print('apiFetch remaining:', c.count('apiFetch'))
print('get() calls:', c.count("get('/mode-b"))