c = open('../frontend/src/api/client.ts', encoding='utf-8').read()

get_fn = """async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
  return res.json() as Promise<T>
}
"""

c = c.replace('async function post', get_fn + 'async function post')
open('../frontend/src/api/client.ts', 'w', encoding='utf-8').write(c)
print('Done')