import { USC } from './index.js'

/** Check if it is USC */
export function isUSC(data: unknown): data is USC {
    return (
        typeof data === 'object' &&
        data !== null &&
        'objects' in data &&
        Array.isArray((data as any).objects)
    )
}
