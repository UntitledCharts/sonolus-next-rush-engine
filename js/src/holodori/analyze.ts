import { type LevelData } from '@sonolus/core'

import { isLevelData } from '../LevelData/analyze.js'

/** Holodori LevelData contains measure lines, which Next Rush does not use. */
export const isHolodoriLevelData = (input: unknown): input is LevelData =>
    isLevelData(input) && input.entities.some((entity) => entity?.archetype === 'MeasureLine')
