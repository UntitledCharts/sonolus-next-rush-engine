import {
    USC,
    USCObject,
    USCSlideNote,
    USCGuideNote,
    USCSingleNote,
    USCBpmChange,
    USCTimeScaleChange,
    USCConnectionStartNote,
    USCConnectionTickNote,
    USCConnectionEndNote,
    USCConnectionAttachNote,
    USCGuideMidpointNote,
    USCSkill,
    USCFever,
} from '../usc/index.js'

const FlickDirection = {
    Default: 0,
    Left: 1,
    Right: 2,
    None: 3,
} as const

const EasingType = {
    Linear: 0,
    EaseIn: 1,
    EaseOut: 2,
} as const

const TickType = {
    Normal: 0,
    Hidden: 1,
    Skip: 2,
} as const

type PJSKNote = {
    id: number
    type: string
    beat: number
    lane: number
    size: number
    isGold?: boolean
    isTrace?: boolean
    isHidden?: boolean
    isGuide?: boolean
    flickDir?: number
    speed?: number
    BPM?: number
    easingType?: number
    tickType?: number
    nextNode?: number
    prevNode?: number
    isEvent?: boolean
}

type PJSKData = {
    offset: number
    notes: PJSKNote[]
}

/** Convert a pjsk to a USC */
export const pjskToUSC = (json: string | PJSKData): USC => {
    const pjsk: PJSKData = typeof json === 'string' ? JSON.parse(json) : json
    const objects: USCObject[] = []

    const noteMap = new Map<number, PJSKNote>()
    pjsk.notes.forEach((note, index) => {
        const id = note.id ?? index
        note.id = id
        noteMap.set(id, note)
    })

    const processedIds = new Set<number>()
    const timeScaleChanges: { beat: number; timeScale: number }[] = []

    for (const note of pjsk.notes) {
        if (processedIds.has(note.id)) continue

        const baseProps = {
            beat: note.beat,
            timeScaleGroup: 0,
        }

        switch (note.type) {
            case 'BPMChange':
                objects.push({
                    type: 'bpm',
                    beat: note.beat,
                    bpm: note.BPM ?? 120,
                } as USCBpmChange)
                break

            case 'HiSpeed':
                timeScaleChanges.push({
                    beat: note.beat,
                    timeScale: note.speed ?? 1,
                })
                break

            case 'Skill':
                objects.push({
                    type: 'skill',
                    beat: note.beat,
                } as USCSkill)
                break

            case 'FeverChance':
                objects.push({
                    type: 'feverChance',
                    beat: note.beat,
                } as USCFever)
                break

            case 'FeverStart':
                objects.push({
                    type: 'feverStart',
                    beat: note.beat,
                } as USCFever)
                break

            case 'Tap':
                objects.push({
                    ...baseProps,
                    type: 'single',
                    lane: note.lane,
                    size: note.size,
                    critical: note.isGold ?? false,
                    trace: note.isTrace ?? false,
                    direction: mapDirection(note.flickDir),
                } as USCSingleNote)
                break

            case 'HoldStart': {
                const chain: PJSKNote[] = []
                let current: PJSKNote | undefined = note

                while (current) {
                    chain.push(current)
                    processedIds.add(current.id)
                    if (current.nextNode !== undefined) {
                        current = noteMap.get(current.nextNode)
                    } else {
                        current = undefined
                    }
                }

                if (note.isGuide) {
                    const midpoints: USCGuideMidpointNote[] = chain.map((n) => ({
                        beat: n.beat,
                        lane: n.lane,
                        size: n.size,
                        ease: mapEase(n.easingType),
                        timeScaleGroup: 0,
                    }))

                    objects.push({
                        type: 'guide',
                        color: note.isGold ? 'yellow' : 'green',
                        fade: 'none',
                        midpoints,
                    } as USCGuideNote)
                } else {
                    const connections: (
                        | USCConnectionStartNote
                        | USCConnectionTickNote
                        | USCConnectionEndNote
                        | USCConnectionAttachNote
                    )[] = chain.map((n, idx) => {
                        const isStart = idx === 0
                        const isEnd = idx === chain.length - 1

                        const common = {
                            beat: n.beat,
                            timeScaleGroup: 0,
                            lane: n.lane,
                            size: n.size,
                            critical: n.isGold ?? false,
                        }

                        if (isStart) {
                            return {
                                ...common,
                                type: 'start',
                                ease: mapEase(n.easingType),
                                judgeType: n.isHidden ? 'none' : n.isTrace ? 'trace' : 'normal',
                            } as USCConnectionStartNote
                        } else if (isEnd) {
                            return {
                                ...common,
                                type: 'end',
                                judgeType: n.isHidden ? 'none' : n.isTrace ? 'trace' : 'normal',
                                direction: mapDirection(n.flickDir),
                            } as USCConnectionEndNote
                        } else {
                            const tickType = n.tickType ?? TickType.Normal

                            if (tickType === TickType.Skip) {
                                return {
                                    type: 'attach',
                                    beat: n.beat,
                                    critical: n.isGold ?? false,
                                    timeScaleGroup: 0,
                                } as USCConnectionAttachNote
                            } else {
                                const isCritical =
                                    tickType === TickType.Hidden ? false : (n.isGold ?? false)

                                return {
                                    ...common,
                                    type: 'tick',
                                    critical: isCritical,
                                    ease: mapEase(n.easingType),
                                } as USCConnectionTickNote
                            }
                        }
                    })

                    objects.push({
                        type: 'slide',
                        critical: chain.some((n) => n.isGold),
                        connections: connections as any,
                    } as USCSlideNote)
                }
                break
            }
        }
    }

    if (timeScaleChanges.length > 0) {
        objects.push({
            type: 'timeScaleGroup',
            changes: timeScaleChanges,
        } as USCTimeScaleChange)
    }

    return {
        offset: pjsk.offset,
        objects,
    }
}

function mapDirection(dir?: number): 'left' | 'up' | 'right' | undefined {
    if (dir === undefined || dir === FlickDirection.None) return undefined
    switch (dir) {
        case FlickDirection.Left:
            return 'left'
        case FlickDirection.Right:
            return 'right'
        case FlickDirection.Default:
            return 'up'
        default:
            return undefined
    }
}

function mapEase(ease?: number): 'linear' | 'in' | 'out' {
    switch (ease) {
        case EasingType.EaseIn:
            return 'in'
        case EasingType.EaseOut:
            return 'out'
        case EasingType.Linear:
        default:
            return 'linear'
    }
}
