import { LevelData } from '@sonolus/core'

/** Check if it is Level Data */
export function isLevelData(data: unknown): data is LevelData {
    return (
        typeof data === 'object' &&
        data !== null &&
        'entities' in data &&
        Array.isArray((data as any).entities)
    )
}
