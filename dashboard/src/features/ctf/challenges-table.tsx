import { Link } from '@tanstack/react-router'
import { statusClass } from './helpers'
import type { ScoreRow } from './types'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

export function ChallengesTable({ rows }: { rows: ScoreRow[] }) {
  if (!rows.length) {
    return (
      <div className='text-muted-foreground py-10 text-center text-sm'>
        暂无题目（等 Master 同步 state/SCOREBOARD.md）
      </div>
    )
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className='w-16'>ID</TableHead>
          <TableHead>题目</TableHead>
          <TableHead className='w-20'>分类</TableHead>
          <TableHead className='w-24'>当前分值</TableHead>
          <TableHead className='w-28'>状态</TableHead>
          <TableHead>Flag</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell className='font-mono text-xs'>{r.id}</TableCell>
            <TableCell>
              <Link
                to='/challenges/$challengeId'
                params={{ challengeId: r.id }}
                className='font-medium hover:underline'
              >
                {r.title || '(未命名)'}
              </Link>
            </TableCell>
            <TableCell className='text-xs'>{r.category}</TableCell>
            <TableCell className='text-xs'>{r.current_score || r.score}</TableCell>
            <TableCell>
              <Badge variant='outline' className={cn('font-mono text-[10px]', statusClass(r.status))}>
                {r.status || '-'}
              </Badge>
            </TableCell>
            <TableCell className='max-w-[220px] truncate font-mono text-xs'>
              {r.flag || '-'}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
