import { BinarySeeker } from '../lib/binaryseeker/mod.js'

const FlickType = ['none', 'up', 'left', 'right', 'down', 'down_left', 'down_right'] as const
type FlickType = (typeof FlickType)[number]
const StepType = ['visible', 'hidden', 'ignored'] as const
type StepType = (typeof StepType)[number]
const EaseType = ['linear', 'easeIn', 'easeOut', 'easeInOut', 'easeOutIn'] as const
export type EaseType = (typeof EaseType)[number]

export type Score = {
    metadata: {
        title: string
        author: string
        artist: string
        musicFile: string
        musicOffset: number
        jacketFile: string
    }
    events: {
        timeSignatures: {
            measure: number
            numerator: number
            denominator: number
        }[]
        bpmChanges: {
            tick: number
            bpm: number
        }[]
        hispeedChanges: {
            tick: number
            speed: number
            layer: number
            skip?: number
            ease?: number
            hideNotes?: boolean
        }[]
        skills: number[]
        fever: {
            start: number
            end: number
        }
    }
    taps: {
        tick: number
        lane: number
        width: number
        flickType: FlickType
        flags: {
            critical: boolean
            friction: boolean
            dummy?: boolean
        }
        layer: number
    }[]
    holds: {
        flags: {
            startHidden: boolean
            endHidden: boolean
            guide: boolean
            dummy?: boolean
        }
        start: {
            tick: number
            lane: number
            width: number
            flags: {
                critical: boolean
                friction: boolean
            }
            layer: number
            ease: EaseType
        }
        fadeType: number
        guideColor: number
        steps: {
            tick: number
            lane: number
            width: number
            type: StepType
            ease: EaseType
            layer: number
        }[]
        end: {
            tick: number
            lane: number
            width: number
            flickType: FlickType

            flags: {
                critical: boolean
                friction: boolean
            }

            layer: number
        }
    }[]
    damages: {
        tick: number
        lane: number
        width: number
        flickType: FlickType
        flags: {
            critical: boolean
            friction: boolean
            dummy?: boolean
        }

        layer: number
    }[]
    numLayers: number
}

/** Detect MMWS Type */
export const detectMMWSType = (mmws: Uint8Array): string => {
    const buffer = new BinarySeeker(mmws.buffer)
    const header = buffer.readString()

    return header
}

export const analyze = (mmws: Uint8Array): Score => {
    const buffer = new BinarySeeker(mmws.buffer)
    const header = buffer.readString()
    if (header !== 'MMWS' && header !== 'CCMMWS' && header !== 'UCMMWS') {
        throw new Error('Invalid MMWS file')
    }

    let version = 0
    let cyanvasVersion = 0
    let untitledVersion = 0

    if (header === 'UCMMWS') {
        untitledVersion = buffer.readInt32LE()
        cyanvasVersion = 6
        version = 4
    } else if (header === 'CCMMWS') {
        cyanvasVersion = Math.max(buffer.readInt16LE(), 1)
        version = buffer.readInt16LE()
    } else {
        version = buffer.readInt16LE()
        cyanvasVersion = buffer.readInt16LE()
    }

    if (version < 3 && header !== 'UCMMWS') {
        throw new Error('Unsupported MMWS version')
    }

    const metadataPointer = buffer.readUInt32LE()
    const eventsPointer = buffer.readUInt32LE()
    const tapsPointer = buffer.readUInt32LE()
    const holdsPointer = buffer.readUInt32LE()
    const damagesPointer = cyanvasVersion > 0 ? buffer.readUInt32LE() : 0
    const layersPointer = cyanvasVersion >= 4 ? buffer.readUInt32LE() : 0

    buffer.seek(metadataPointer)
    const metadata = {
        title: buffer.readString(),
        author: buffer.readString(),
        artist: buffer.readString(),
        musicFile: buffer.readString(),
        musicOffset: buffer.readFloat32LE(),
        jacketFile: version >= 2 ? buffer.readString() : '',
    }
    if (cyanvasVersion >= 1) {
        buffer.readInt32LE()
    }

    buffer.seek(eventsPointer)
    const events: Score['events'] = {
        timeSignatures: [],
        bpmChanges: [],
        hispeedChanges: [],
        skills: [],
        fever: {
            start: 0,
            end: 0,
        },
    }
    const timeSignaturesCount = buffer.readInt32LE()
    for (let i = 0; i < timeSignaturesCount; i++) {
        events.timeSignatures.push({
            measure: buffer.readInt32LE(),
            numerator: buffer.readInt32LE(),
            denominator: buffer.readInt32LE(),
        })
    }
    const bpmChangesCount = buffer.readInt32LE()
    for (let i = 0; i < bpmChangesCount; i++) {
        events.bpmChanges.push({
            tick: buffer.readInt32LE(),
            bpm: buffer.readFloat32LE(),
        })
    }

    if (version >= 3) {
        const hispeedChangesCount = buffer.readInt32LE()
        for (let i = 0; i < hispeedChangesCount; i++) {
            const tick = buffer.readInt32LE()
            const speed = buffer.readFloat32LE()
            const layer = cyanvasVersion >= 4 ? buffer.readInt32LE() : 0

            let skip = 0
            let ease = 0
            let hideNotes = false

            if (untitledVersion >= 2) {
                skip = buffer.readFloat32LE()
                ease = buffer.readInt16LE()
                hideNotes = !!buffer.readInt16LE()
            }

            events.hispeedChanges.push({
                tick,
                speed,
                layer,
                skip,
                ease,
                hideNotes,
            })
        }
    }

    if (version >= 2) {
        const skillsCount = buffer.readInt32LE()
        for (let i = 0; i < skillsCount; i++) {
            const skillTick = buffer.readInt32LE()
            events.skills.push(skillTick)
        }
        events.fever.start = buffer.readInt32LE()
        events.fever.end = buffer.readInt32LE()
    }

    buffer.seek(tapsPointer)

    const taps: Score['taps'] = []
    const tapsCount = buffer.readInt32LE()
    for (let i = 0; i < tapsCount; i++) {
        const tick = buffer.readInt32LE()
        const lane = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
        const width = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
        const layer = cyanvasVersion >= 4 ? buffer.readInt32LE() : 0

        const flickTypeRaw = buffer.readInt32LE()
        const flickType = FlickType[flickTypeRaw] || 'none'

        const flags = buffer.readInt32LE()
        taps.push({
            tick,
            lane,
            width,
            flickType,
            flags: {
                critical: !!(flags & (1 << 0)),
                friction: !!(flags & (1 << 1)),
                dummy: cyanvasVersion >= 6 && untitledVersion >= 1 ? !!(flags & (1 << 2)) : false,
            },
            layer,
        })
    }

    buffer.seek(holdsPointer)
    const holds: Score['holds'] = []
    const holdsCount = buffer.readInt32LE()
    for (let i = 0; i < holdsCount; i++) {
        const holdFlags = version >= 4 ? buffer.readInt32LE() : 0
        const startTick = buffer.readInt32LE()
        const startLane = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
        const startWidth = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
        const startLayer = cyanvasVersion >= 4 ? buffer.readInt32LE() : 0
        const startFlags = buffer.readInt32LE()
        const startEase = EaseType[buffer.readInt32LE() as 0 | 1 | 2]
        const fadeType = cyanvasVersion >= 2 ? buffer.readInt32LE() : 0
        const guideColor =
            cyanvasVersion >= 3 ? buffer.readInt32LE() : startFlags & (1 << 0) ? 4 : 2
        const stepsCount = buffer.readInt32LE()
        const steps: Score['holds'][0]['steps'] = []
        for (let j = 0; j < stepsCount; j++) {
            const tick = buffer.readInt32LE()
            const lane = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
            const width = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
            const layer = cyanvasVersion >= 4 ? buffer.readInt32LE() : 0

            buffer.readInt32LE()

            const type = StepType[buffer.readInt32LE()]
            const ease = EaseType[buffer.readInt32LE()]
            steps.push({
                tick,
                lane,
                width,
                type,
                ease,
                layer,
            })
        }
        const endTick = buffer.readInt32LE()
        const endLane = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
        const endWidth = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
        const endLayer = cyanvasVersion >= 4 ? buffer.readInt32LE() : 0

        const endFlickTypeRaw = buffer.readInt32LE()
        const endFlickType = FlickType[endFlickTypeRaw] || 'none'

        const endFlags = buffer.readInt32LE()

        holds.push({
            flags: {
                startHidden: !!(holdFlags & (1 << 0)),
                endHidden: !!(holdFlags & (1 << 1)),
                guide: !!(holdFlags & (1 << 2)),
                dummy: !!(holdFlags & (1 << 3)),
            },
            start: {
                tick: startTick,
                lane: startLane,
                width: startWidth,
                ease: startEase,
                flags: {
                    critical: !!(startFlags & (1 << 0)),
                    friction: !!(startFlags & (1 << 1)),
                },
                layer: startLayer,
            },
            fadeType,
            guideColor,
            steps,
            end: {
                tick: endTick,
                lane: endLane,
                width: endWidth,
                flags: {
                    critical: !!(endFlags & (1 << 0)),
                    friction: !!(endFlags & (1 << 1)),
                },
                flickType: endFlickType,
                layer: endLayer,
            },
        })
    }

    events.timeSignatures.sort((a, b) => a.measure - b.measure)
    events.bpmChanges.sort((a, b) => a.tick - b.tick)
    events.hispeedChanges.sort((a, b) => a.tick - b.tick)
    events.skills.sort((a, b) => a - b)
    taps.sort((a, b) => a.tick - b.tick)
    holds.sort((a, b) => a.start.tick - b.start.tick)

    const damages: Score['damages'] = []
    if (cyanvasVersion >= 1) {
        buffer.seek(damagesPointer)
        const damagesCount = buffer.readInt32LE()
        for (let i = 0; i < damagesCount; i++) {
            const tick = buffer.readInt32LE()
            const lane = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
            const width = cyanvasVersion >= 6 ? buffer.readFloat32LE() : buffer.readInt32LE()
            const layer = cyanvasVersion >= 4 ? buffer.readInt32LE() : 0

            const flickTypeRaw = buffer.readInt32LE()
            const flickType = FlickType[flickTypeRaw] || 'none'

            const flags = buffer.readInt32LE()
            damages.push({
                tick,
                lane,
                width,
                flickType,
                layer,
                flags: {
                    critical: !!(flags & (1 << 0)),
                    friction: !!(flags & (1 << 1)),
                    dummy:
                        cyanvasVersion >= 6 && untitledVersion >= 1 ? !!(flags & (1 << 2)) : false,
                },
            })
        }
        damages.sort((a, b) => a.tick - b.tick)
    }

    let numLayers = 1
    if (cyanvasVersion >= 4) {
        buffer.seek(layersPointer)
        numLayers = buffer.readInt32LE()
    }

    return {
        metadata,
        events,
        taps,
        holds,
        damages,
        numLayers,
    }
}
