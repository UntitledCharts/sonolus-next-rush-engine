import { type LevelData } from '@sonolus/core'

import { isLevelData } from '../LevelData/analyze.js'

const bandoriArchetypes = new Set([
    'TapNote',
    'FlickNote',
    'DirectionalFlickNote',
    'SlideStartNote',
    'SlideTickNote',
    'SlideEndNote',
    'SlideEndFlickNote',
    'IgnoredNote',
    'StraightSlideConnector',
    'CurvedSlideConnector',
])

/** Shared system entities alone cannot identify an empty Bandori chart. */
export const isBandoriLevelData = (input: unknown): input is LevelData =>
    isLevelData(input) && input.entities.some((entity) => bandoriArchetypes.has(entity?.archetype))
