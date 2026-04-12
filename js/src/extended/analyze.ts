import { LevelData } from '@sonolus/core'

/** Check if it is chcy Level Data */
export function isExtendedLevelData(data: unknown): data is LevelData {
    return (
        typeof data === 'object' &&
        data !== null &&
        'entities' in data &&
        Array.isArray((data as any).entities) &&
        (data as any).entities.some((e: any) => e.archetype === 'TimeScaleGroup')
    )
}
