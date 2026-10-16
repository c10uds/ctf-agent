/** 解析 snapshot.environments_md 中当前开启的动态环境 */
export interface ActiveEnvironment {
  challengeId: string
  entry: string
  startedAt: string
  purpose: string
}

export function parseActiveEnvironment(md: string | undefined): ActiveEnvironment | null {
  if (!md) return null
  if (md.includes('当前无开启的环境')) return null
  for (const line of md.split('\n')) {
    const t = line.trim()
    if (!t.startsWith('|')) continue
    if (/^\|[\s\-|]+\|?$/.test(t)) continue // 分隔行 | --- | --- |
    if (t.includes('题目ID')) continue // 表头
    const cells = t
      .split('|')
      .slice(1, -1)
      .map((c) => c.trim())
    if (cells.length >= 4 && cells[0]) {
      return { challengeId: cells[0], entry: cells[1], startedAt: cells[2], purpose: cells[3] }
    }
  }
  return null
}
