import { type LevelData } from '@sonolus/core'

import { isLevelData } from '../LevelData/analyze.js'

/** Sirius prefixes its gameplay and system archetypes, including empty charts. */
export const isSiriusLevelData = (input: unknown): input is LevelData =>
    isLevelData(input) && input.entities.some((entity) => entity?.archetype?.startsWith('Sirius '))
