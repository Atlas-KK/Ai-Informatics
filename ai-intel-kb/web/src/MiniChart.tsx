import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

export default function MiniChart({ data }: { data: Record<string, number> }) {
  const element = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!element.current || element.current.clientWidth === 0) return
    const chart = echarts.init(element.current, undefined, { renderer: 'canvas' })
    chart.setOption({
      animation: false,
      color: ['#1890ff'],
      tooltip: { trigger: 'axis' },
      grid: { left: 96, right: 8, top: 8, bottom: 24 },
      xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f0f0' } } },
      yAxis: {
        type: 'category',
        data: Object.keys(data),
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [{ type: 'bar', barMaxWidth: 16, data: Object.values(data) }],
    })
    const resize = () => chart.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.dispose()
    }
  }, [data])

  return <div ref={element} className="mini-chart" role="img" aria-label="情报数量统计图" />
}
