c = open('../frontend/src/api/client.ts', encoding='utf-8').read()

get_fn = """async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`) }
  return res.json() as Promise<T>
}
"""

# Remove all occurrences then add back once
c = c.replace(get_fn, '')
c = c.replace('async function post', get_fn + 'async function post')

open('../frontend/src/api/client.ts', 'w', encoding='utf-8').write(c)
print('Done - get() count:', c.count('async function get'))