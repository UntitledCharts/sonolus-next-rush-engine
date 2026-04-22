/** Check if it is PJSK */
export const isPJSK = (data: unknown): boolean => {
    if (typeof data !== 'object' || data === null) return false

    const hasNotes = 'notes' in data && Array.isArray((data as Record<string, unknown>).objects)
    const hasVersionOrOffset = 'version' in data || 'offset' in data

    return hasNotes && hasVersionOrOffset
}
