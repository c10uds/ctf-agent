import { useState } from 'react'
import { AlertTriangle, Cpu, RefreshCw, RotateCcw } from 'lucide-react'
import { useAppState } from '../lib/store'
import { socket } from '../lib/ws'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../components/ui/card'
import { Dialog } from '../components/ui/dialog'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { Select } from '../components/ui/select'
import { Separator } from '../components/ui/separator'

export function ModelsPage() {
  const state = useAppState()
  const modelState = state.model
  const [baseUrl, setBaseUrl] = useState(() => localStorage.getItem('debug-console.base_url') ?? '')
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('debug-console.api_key') ?? '')
  const [model, setModel] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const canOperate = state.wsConnected && state.agent.agent_connected

  const fetchModels = async () => {
    if (!baseUrl.trim()) {
      setFetchMsg('请先填写 Base URL')
      return
    }
    setFetching(true)
    setFetchMsg(null)
    try {
      const params = new URLSearchParams({ base_url: baseUrl.trim(), api_key: apiKey })
      const res = await fetch(`/api/models?${params}`)
      const data = (await res.json()) as { models?: string[]; error?: string }
      setModels(data.models ?? [])
      setFetchMsg(
        data.error ? `拉取失败：${data.error}` : `成功拉取 ${data.models?.length ?? 0} 个模型`,
      )
    } catch (err) {
      setModels([])
      setFetchMsg(`拉取失败：${String(err)}`)
    } finally {
      setFetching(false)
    }
  }

  const apply = () => {
    const m = model.trim()
    if (!m || !canOperate) return
    localStorage.setItem('debug-console.base_url', baseUrl.trim())
    localStorage.setItem('debug-console.api_key', apiKey)
    socket.send({ type: 'set_model', base_url: baseUrl.trim(), api_key: apiKey, model: m })
  }

  const restart = () => {
    socket.send({ type: 'restart_master' })
    setConfirmOpen(false)
  }

  return (
    <div className="scroll-thin h-full overflow-auto">
      <div className="mx-auto max-w-2xl space-y-4 p-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-slate-400" />
              当前模型状态
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-slate-500">生效中：</span>
              <span className="font-mono">{modelState.current ?? '—'}</span>
              {modelState.current && <Badge variant="success">当前</Badge>}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-500">待生效：</span>
              {modelState.pending ? (
                <>
                  <span className="font-mono">{modelState.pending}</span>
                  <Badge variant="warning">重启 Master 后生效</Badge>
                </>
              ) : (
                <span className="text-slate-400">无</span>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>模型配置</CardTitle>
            <CardDescription>修改 Master 使用的模型提供方与模型</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="base-url">Base URL</Label>
              <Input
                id="base-url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="api-key">API Key</Label>
              <Input
                id="api-key"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="model">模型名</Label>
              <div className="flex gap-2">
                <Input
                  id="model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="可手输，或先拉取列表后从下拉选择"
                />
                <Button
                  variant="outline"
                  onClick={fetchModels}
                  disabled={fetching || !baseUrl.trim()}
                >
                  <RefreshCw className={fetching ? 'animate-spin' : ''} />
                  拉取模型列表
                </Button>
              </div>
              {models.length > 0 && (
                <Select value="" onChange={(e) => setModel(e.target.value)} className="mt-1">
                  <option value="" disabled>
                    从拉取结果中选择（{models.length} 个）…
                  </option>
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </Select>
              )}
              {fetchMsg && <p className="text-xs text-slate-500">{fetchMsg}</p>}
            </div>
            <Button onClick={apply} disabled={!canOperate || !model.trim()}>
              应用
            </Button>
            {!canOperate && (
              <p className="text-xs text-amber-600">容器 Agent 未连接，指令将无法送达。</p>
            )}
          </CardContent>
        </Card>

        <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          模型变更在下一轮 Master 重启后生效；点立即重启会中断当前进行中的分析。
        </div>

        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-red-600">危险操作</CardTitle>
            <CardDescription>重启容器内的 Master 进程，使待生效模型立即启用</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              variant="destructive"
              onClick={() => setConfirmOpen(true)}
              disabled={!canOperate}
            >
              <RotateCcw />
              立即重启 Master
            </Button>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="确认重启 Master？"
        description="重启会中断当前所有进行中的分析任务，待生效模型将立即启用。"
      >
        <Separator className="my-2" />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => setConfirmOpen(false)}>
            取消
          </Button>
          <Button variant="destructive" onClick={restart}>
            确认重启
          </Button>
        </div>
      </Dialog>
    </div>
  )
}
