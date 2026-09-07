import type { Tier } from '../types'

export const tierLabels: Record<Tier, string> = {
  MUST_READ: '必读',
  IMPORTANT: '重要',
  EXTENDED: '扩展',
}

export const tierColors: Record<Tier, string> = {
  MUST_READ: 'red',
  IMPORTANT: 'gold',
  EXTENDED: 'blue',
}

export const scoreDimensionLabels: Record<string, string> = {
  source_authority: '来源权威性',
  timeliness: '及时性',
  reach: '传播范围',
  information_density: '信息密度',
  innovation: '创新性',
}

export const scoreDimensions = Object.keys(scoreDimensionLabels)
