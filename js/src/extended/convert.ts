import { type LevelData, type LevelDataEntity } from '@sonolus/core'

export interface ExtendedEntityDataField {
    name: string
    value?: number
    ref?: string
}

export interface ExtendedEntityData {
    archetype: string
    name?: string
    data: ExtendedEntityDataField[]
}

const ConnectorKind = {
    NONE: 0,
    ACTIVE_NORMAL: 1,
    ACTIVE_CRITICAL: 2,
    GUIDE_NEUTRAL: 101,
    GUIDE_RED: 102,
    GUIDE_GREEN: 103,
    GUIDE_BLUE: 104,
    GUIDE_YELLOW: 105,
    GUIDE_PURPLE: 106,
    GUIDE_CYAN: 107,
    GUIDE_BLACK: 108,
} as const

const FlickDirection = {
    UP_OMNI: 0,
    UP_LEFT: 1,
    UP_RIGHT: 2,
    DOWN_OMNI: 3,
    DOWN_LEFT: 4,
    DOWN_RIGHT: 5,
} as const

const EaseType = {
    NONE: 0,
    LINEAR: 1,
    IN_QUAD: 2,
    OUT_QUAD: 3,
    IN_OUT_QUAD: 4,
    OUT_IN_QUAD: 5,
} as const

const noteTypeMapping: Record<string, string> = {
    NormalTapNote: 'NormalTapNote',
    CriticalTapNote: 'CriticalTapNote',
    NormalFlickNote: 'NormalFlickNote',
    CriticalFlickNote: 'CriticalFlickNote',
    NormalSlideStartNote: 'NormalHeadTapNote',
    CriticalSlideStartNote: 'CriticalHeadTapNote',
    NormalSlideEndNote: 'NormalTailReleaseNote',
    CriticalSlideEndNote: 'CriticalTailReleaseNote',
    NormalSlideEndFlickNote: 'NormalTailFlickNote',
    CriticalSlideEndFlickNote: 'CriticalTailFlickNote',
    IgnoredSlideTickNote: 'TransientHiddenTickNote',
    NormalSlideTickNote: 'NormalTickNote',
    CriticalSlideTickNote: 'CriticalTickNote',
    HiddenSlideTickNote: 'AnchorNote',
    NormalAttachedSlideTickNote: 'NormalTickNote',
    CriticalAttachedSlideTickNote: 'CriticalTickNote',
    NormalTraceNote: 'NormalTraceNote',
    CriticalTraceNote: 'CriticalTraceNote',
    DamageNote: 'DamageNote',
    NormalTraceFlickNote: 'NormalTraceFlickNote',
    CriticalTraceFlickNote: 'CriticalTraceFlickNote',
    NonDirectionalTraceFlickNote: 'NormalTraceFlickNote',
    HiddenSlideStartNote: 'AnchorNote',
    NormalTraceSlideStartNote: 'NormalHeadTraceNote',
    CriticalTraceSlideStartNote: 'CriticalHeadTraceNote',
    NormalTraceSlideEndNote: 'NormalTailTraceNote',
    CriticalTraceSlideEndNote: 'CriticalTailTraceNote',
}

const activeConnectorKindMapping: Record<string, number> = {
    NormalSlideConnector: ConnectorKind.ACTIVE_NORMAL,
    CriticalSlideConnector: ConnectorKind.ACTIVE_CRITICAL,
}

const activeSlideStartArchetypes = new Set([
    'NormalSlideStartNote',
    'CriticalSlideStartNote',
    'HiddenSlideStartNote',
    'NormalTraceSlideStartNote',
    'CriticalTraceSlideStartNote',
])

const flickDirectionMapping: Record<number, number> = {
    [-1]: FlickDirection.UP_LEFT,
    0: FlickDirection.UP_OMNI,
    1: FlickDirection.UP_RIGHT,
}

const easeTypeMapping: Record<number, number> = {
    [-2]: EaseType.OUT_IN_QUAD,
    [-1]: EaseType.OUT_QUAD,
    0: EaseType.LINEAR,
    1: EaseType.IN_QUAD,
    2: EaseType.IN_OUT_QUAD,
}

const fadeAlphaMapping: Record<number, [number, number]> = {
    0: [1.0, 0.0],
    1: [1.0, 1.0],
    2: [0.0, 1.0],
}

const guideKindMapping: Record<number, number> = {
    0: ConnectorKind.GUIDE_NEUTRAL,
    1: ConnectorKind.GUIDE_RED,
    2: ConnectorKind.GUIDE_GREEN,
    3: ConnectorKind.GUIDE_BLUE,
    4: ConnectorKind.GUIDE_YELLOW,
    5: ConnectorKind.GUIDE_PURPLE,
    6: ConnectorKind.GUIDE_CYAN,
    7: ConnectorKind.GUIDE_BLACK,
}

interface BpmChangeInfo {
    beat: number
    bpm: number
    time: number
}

interface TimescaleChangeInfo {
    beat: number
    timeScale: number
}

class ExtData {
    entities: ExtendedEntityData[]
    byArch = new Map<string, { idx: number; e: ExtendedEntityData }[]>()
    byName = new Map<string, ExtendedEntityData>()
    indexByEntity = new Map<ExtendedEntityData, number>()
    notes: { idx: number; e: ExtendedEntityData }[] = []
    connectors: { idx: number; e: ExtendedEntityData }[] = []

    constructor(entities: ExtendedEntityData[]) {
        this.entities = entities
        entities.forEach((e, idx) => {
            const arch = e.archetype
            if (!this.byArch.has(arch)) this.byArch.set(arch, [])
            this.byArch.get(arch)?.push({ idx, e })

            if (e.name !== undefined && !this.byName.has(e.name)) this.byName.set(e.name, e)
            if (!this.indexByEntity.has(e)) this.indexByEntity.set(e, idx)

            if (arch in noteTypeMapping) this.notes.push({ idx, e })
            if (arch in activeConnectorKindMapping) this.connectors.push({ idx, e })
        })
    }

    get(idx: number) {
        return this.entities[idx]
    }

    getByArch(arch: string) {
        return this.byArch.get(arch) || []
    }
}

class EntityBuilder {
    archetype: string
    values: Record<string, number> = {}
    refs: Record<string, EntityBuilder> = {}

    constructor(archetype: string) {
        this.archetype = archetype
    }

    set(key: string, val: number | EntityBuilder) {
        if (val instanceof EntityBuilder) {
            this.refs[key] = val
        } else if (typeof val === 'number') {
            this.values[key] = val
        }
    }

    getBeat(): number {
        return this.values['#BEAT'] ?? -1
    }
}

interface ConnectorSegmentLink {
    head: EntityBuilder
    tail: EntityBuilder
}

interface ConnectorLink {
    head: EntityBuilder
    tail: EntityBuilder
    activeHead: EntityBuilder
    activeTail: EntityBuilder
    segments: ConnectorSegmentLink[]
}

function getField(e: ExtendedEntityData, name: string): number | string | undefined {
    const field = e.data.find((x) => x.name === name)
    if (!field) return undefined
    if (field.value !== undefined) return field.value
    if (field.ref !== undefined) return field.ref
    return undefined
}

function getNum(e: ExtendedEntityData, name: string, def = 0): number {
    const val = getField(e, name)
    return typeof val === 'number' ? val : def
}

function nearlyEqual(a: number, b: number) {
    return Math.abs(a - b) < 1e-6
}

function lerp(a: number, b: number, t: number) {
    return a + (b - a) * t
}

function unlerp(a: number, b: number, x: number) {
    return (x - a) / (b - a)
}

function clamp01(x: number) {
    return Math.min(1, Math.max(0, x))
}

function applyEase(type: number, x: number) {
    const t = clamp01(x)
    switch (type) {
        case EaseType.IN_QUAD:
            return t * t
        case EaseType.OUT_QUAD:
            return 1 - (1 - t) * (1 - t)
        case EaseType.IN_OUT_QUAD:
            return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2
        case EaseType.OUT_IN_QUAD:
            return t < 0.5
                ? (1 - (1 - 2 * t) * (1 - 2 * t)) / 2
                : 0.5 + ((2 * t - 1) * (2 * t - 1)) / 2
        default:
            return t
    }
}

function resolveOriginal(
    ext: ExtData,
    ref: number | string | undefined,
): ExtendedEntityData | undefined {
    if (typeof ref === 'number') return ext.get(ref)
    if (typeof ref === 'string') return ext.byName.get(ref)
    return undefined
}

export const extendedToLevelData = (data: LevelData, offset = 0): LevelData | undefined => {
    const ext = new ExtData(data.entities)

    const connectorsByHeadRef = new Map<number | string, { idx: number; e: ExtendedEntityData }[]>()
    const connectorsByTailRef = new Map<number | string, { idx: number; e: ExtendedEntityData }[]>()
    const connectorsByStartRef = new Map<
        number | string,
        { idx: number; e: ExtendedEntityData }[]
    >()
    const pushConnectorIndex = (
        map: Map<number | string, { idx: number; e: ExtendedEntityData }[]>,
        key: number | string | undefined,
        entry: { idx: number; e: ExtendedEntityData },
    ) => {
        if (key === undefined) return
        const list = map.get(key)
        if (list) list.push(entry)
        else map.set(key, [entry])
    }
    for (const entry of ext.connectors) {
        pushConnectorIndex(connectorsByHeadRef, getField(entry.e, 'head'), entry)
        pushConnectorIndex(connectorsByTailRef, getField(entry.e, 'tail'), entry)
        pushConnectorIndex(connectorsByStartRef, getField(entry.e, 'start'), entry)
    }
    const getConnectorsByHeadRef = (ref: number | string | undefined) =>
        ref === undefined ? [] : (connectorsByHeadRef.get(ref) ?? [])
    const getConnectorsByTailRef = (ref: number | string | undefined) =>
        ref === undefined ? [] : (connectorsByTailRef.get(ref) ?? [])
    const getConnectorsByStartRef = (ref: number | string | undefined) =>
        ref === undefined ? [] : (connectorsByStartRef.get(ref) ?? [])

    const finalEntities: EntityBuilder[] = []

    const defaultTsg = new EntityBuilder('#TIMESCALE_GROUP')
    finalEntities.push(defaultTsg)

    const init = new EntityBuilder('Initialization')
    finalEntities.push(init)

    const bpmChanges = ext
        .getByArch('#BPM_CHANGE')
        .map(({ e }) => ({ beat: getNum(e, '#BEAT'), bpm: getNum(e, '#BPM') }))
        .sort((a, b) => a.beat - b.beat)

    const bpmChangeInfos: BpmChangeInfo[] = []
    let lastBeat = 0
    let lastTime = 0
    let lastBpm = bpmChanges[0]?.bpm ?? 120

    for (const change of bpmChanges) {
        lastTime += ((change.beat - lastBeat) * 60) / lastBpm
        bpmChangeInfos.push({ ...change, time: lastTime })
        lastBeat = change.beat
        lastBpm = change.bpm
    }

    function beatToTime(beat: number) {
        if (bpmChangeInfos.length === 0) return (beat * 60) / 120

        let current = bpmChangeInfos[0]
        for (const change of bpmChangeInfos) {
            if (change.beat > beat) break
            current = change
        }
        return current.time + ((beat - current.beat) * 60) / current.bpm
    }

    function timeToBeat(time: number) {
        if (bpmChangeInfos.length === 0) return (time * 120) / 60

        let current = bpmChangeInfos[0]
        for (const change of bpmChangeInfos) {
            if (change.time > time) break
            current = change
        }
        return current.beat + ((time - current.time) * current.bpm) / 60
    }

    for (const { e } of ext.getByArch('#BPM_CHANGE')) {
        const bpm = new EntityBuilder('#BPM_CHANGE')
        bpm.set('#BEAT', getNum(e, '#BEAT'))
        bpm.set('#BPM', getNum(e, '#BPM'))
        finalEntities.push(bpm)
    }

    const timescaleGroupsByIndex = new Map<number, EntityBuilder>()
    const timescaleGroupsByName = new Map<string, EntityBuilder>()
    const timescaleChangesByIndex = new Map<number, TimescaleChangeInfo[]>()
    const timescaleChangesByName = new Map<string, TimescaleChangeInfo[]>()

    for (const { idx, e } of ext.getByArch('TimeScaleGroup')) {
        const group = new EntityBuilder('#TIMESCALE_GROUP')
        finalEntities.push(group)
        timescaleGroupsByIndex.set(idx, group)
        if (e.name) timescaleGroupsByName.set(e.name, group)

        let rawRef = getField(e, 'first')
        const changes: EntityBuilder[] = []
        const changeInfos: TimescaleChangeInfo[] = []

        while (rawRef !== undefined) {
            const raw = resolveOriginal(ext, rawRef)
            if (!raw) break

            changeInfos.push({
                beat: getNum(raw, '#BEAT'),
                timeScale: getNum(raw, 'timeScale'),
            })

            const change = new EntityBuilder('#TIMESCALE_CHANGE')
            change.set('#BEAT', getNum(raw, '#BEAT'))
            change.set('#TIMESCALE', getNum(raw, 'timeScale'))
            change.set('#TIMESCALE_SKIP', 0.0)
            change.set('#TIMESCALE_GROUP', group)
            change.set('#TIMESCALE_EASE', 0)
            change.set('hideNotes', 0)

            if (changes.length > 0) {
                changes[changes.length - 1].set('next', change)
            }
            changes.push(change)

            const nextRef = getField(raw, 'next')
            if (typeof nextRef === 'number' && nextRef <= 0) break
            rawRef = nextRef
        }

        if (changes.length > 0) {
            group.set('first', changes[0])
        }
        finalEntities.push(...changes)
        changeInfos.sort((a, b) => a.beat - b.beat)
        timescaleChangesByIndex.set(idx, changeInfos)
        if (e.name) timescaleChangesByName.set(e.name, changeInfos)
    }

    function getTSG(ref: number | string | undefined) {
        if (typeof ref === 'number') return timescaleGroupsByIndex.get(ref)
        if (typeof ref === 'string') return timescaleGroupsByName.get(ref)
        return undefined
    }

    function getTSGChanges(ref: number | string | undefined) {
        if (typeof ref === 'number') return timescaleChangesByIndex.get(ref) ?? []
        if (typeof ref === 'string') return timescaleChangesByName.get(ref) ?? []
        return []
    }

    function timeToScaledTime(time: number, changes: TimescaleChangeInfo[]) {
        if (changes.length === 0) return time

        const firstTime = beatToTime(changes[0].beat)
        if (time < firstTime) return time

        let scaledTime = firstTime
        for (let i = 0; i < changes.length; i++) {
            const start = changes[i]
            const startTime = beatToTime(start.beat)
            const endTime = i === changes.length - 1 ? undefined : beatToTime(changes[i + 1].beat)

            if (endTime === undefined || time < endTime) {
                return scaledTime + (time - startTime) * start.timeScale
            }

            scaledTime += (endTime - startTime) * start.timeScale
        }

        return time
    }

    function scaledTimeToTime(scaledTime: number, changes: TimescaleChangeInfo[]) {
        if (changes.length === 0) return scaledTime

        const firstTime = beatToTime(changes[0].beat)
        if (scaledTime < firstTime) return scaledTime

        let currentScaledTime = firstTime
        for (let i = 0; i < changes.length; i++) {
            const start = changes[i]
            const startTime = beatToTime(start.beat)
            const endTime = i === changes.length - 1 ? undefined : beatToTime(changes[i + 1].beat)

            if (endTime === undefined) {
                if (start.timeScale === 0) return Number.POSITIVE_INFINITY
                return startTime + (scaledTime - currentScaledTime) / start.timeScale
            }

            const nextScaledTime = currentScaledTime + (endTime - startTime) * start.timeScale
            const minScaledTime = Math.min(currentScaledTime, nextScaledTime)
            const maxScaledTime = Math.max(currentScaledTime, nextScaledTime)

            if (minScaledTime <= scaledTime && scaledTime <= maxScaledTime) {
                if (Math.abs(nextScaledTime - currentScaledTime) < 1e-6) return startTime
                return lerp(
                    startTime,
                    endTime,
                    unlerp(currentScaledTime, nextScaledTime, scaledTime),
                )
            }

            currentScaledTime = nextScaledTime
        }

        return scaledTime
    }

    const notesByIndex = new Map<number, EntityBuilder>()
    const notesByName = new Map<string, EntityBuilder>()
    const connectorsByIndex = new Map<number, ConnectorLink>()
    const connectorsByName = new Map<string, ConnectorLink>()

    for (const { idx, e } of ext.notes) {
        const arch = noteTypeMapping[e.archetype]
        if (!arch) continue

        const note = new EntityBuilder(arch)
        note.set('#BEAT', getNum(e, '#BEAT'))
        note.set('lane', getNum(e, 'lane', 0.0))
        note.set('size', getNum(e, 'size', 0.0))
        note.set(
            'direction',
            flickDirectionMapping[getNum(e, 'direction', 0)] ?? FlickDirection.UP_OMNI,
        )
        note.set('segmentKind', ConnectorKind.ACTIVE_NORMAL)
        note.set('segmentAlpha', 1)
        note.set('segmentLayer', 0)

        note.set('isAttached', 0)
        note.set('connectorEase', 0)
        note.set('isSeparator', 0)

        finalEntities.push(note)
        notesByIndex.set(idx, note)
        if (e.name) notesByName.set(e.name, note)
    }

    function getNote(ref: number | string | undefined) {
        if (typeof ref === 'number') return notesByIndex.get(ref)
        if (typeof ref === 'string') return notesByName.get(ref)
        return undefined
    }

    function getTimeScaleAt(changes: TimescaleChangeInfo[], beat: number) {
        const change = [...changes].reverse().find((change) => change.beat < beat - 1e-6)
        return change?.timeScale ?? 1
    }

    function shouldUseStartAsHead(
        startRef: number | string | undefined,
        headRef: number | string | undefined,
    ) {
        if (startRef === headRef) return false

        const start = resolveOriginal(ext, startRef)
        const head = resolveOriginal(ext, headRef)
        if (!start || !head) return false
        if (head.archetype !== 'HiddenSlideStartNote') return false
        if (!activeSlideStartArchetypes.has(start.archetype)) return false

        return (
            nearlyEqual(getNum(start, '#BEAT'), getNum(head, '#BEAT')) &&
            nearlyEqual(getNum(start, 'lane'), getNum(head, 'lane')) &&
            nearlyEqual(getNum(start, 'size'), getNum(head, 'size'))
        )
    }

    function createConnectorAnchor(
        beat: number,
        lane: number,
        size: number,
        tsg: EntityBuilder | undefined,
        kind: number,
    ) {
        const anchor = new EntityBuilder('AnchorNote')
        anchor.set('#BEAT', beat)
        anchor.set('lane', lane)
        anchor.set('size', size)
        anchor.set('direction', FlickDirection.UP_OMNI)
        anchor.set('#TIMESCALE_GROUP', tsg || defaultTsg)
        anchor.set('isAttached', 0)
        anchor.set('connectorEase', EaseType.LINEAR)
        anchor.set('isSeparator', 0)
        anchor.set('segmentKind', kind)
        anchor.set('segmentAlpha', 1)
        anchor.set('segmentLayer', 0)
        finalEntities.push(anchor)
        return anchor
    }

    function getConnectorSplitAnchors(
        headOriginal: ExtendedEntityData,
        tailOriginal: ExtendedEntityData,
        tsg: EntityBuilder | undefined,
        kind: number,
        ease: number,
    ) {
        const headBeat = getNum(headOriginal, '#BEAT')
        const tailBeat = getNum(tailOriginal, '#BEAT')
        if (tailBeat <= headBeat) return []

        const headTsgRef = getField(headOriginal, 'timeScaleGroup')
        const tailTsgRef = getField(tailOriginal, 'timeScaleGroup')
        const headChanges = getTSGChanges(headTsgRef)
        const tailChanges = getTSGChanges(tailTsgRef)
        const splitBeats = headChanges
            .filter((change) => {
                if (!(headBeat + 1e-6 < change.beat && change.beat < tailBeat - 1e-6)) return false
                return !nearlyEqual(change.timeScale, getTimeScaleAt(headChanges, change.beat))
            })
            .map(({ beat }) => beat)

        if (splitBeats.length === 0) return []

        const headScaledTime = timeToScaledTime(beatToTime(headBeat), headChanges)
        const tailScaledTime = timeToScaledTime(beatToTime(tailBeat), tailChanges)
        if (Math.abs(tailScaledTime - headScaledTime) < 1e-6) return []

        if (ease !== EaseType.LINEAR) {
            const sampleCount = 8
            for (let i = 1; i < sampleCount; i++) {
                const scaledTime = lerp(headScaledTime, tailScaledTime, i / sampleCount)
                const beat = timeToBeat(scaledTimeToTime(scaledTime, headChanges))
                if (Number.isFinite(beat) && headBeat + 1e-6 < beat && beat < tailBeat - 1e-6) {
                    splitBeats.push(beat)
                }
            }
        }

        const uniqueSplitBeats = [...splitBeats]
            .sort((a, b) => a - b)
            .filter((beat, i, beats) => i === 0 || !nearlyEqual(beat, beats[i - 1]))

        const headLane = getNum(headOriginal, 'lane')
        const tailLane = getNum(tailOriginal, 'lane')
        const headSize = getNum(headOriginal, 'size')
        const tailSize = getNum(tailOriginal, 'size')

        return uniqueSplitBeats.map((beat) => {
            const scaledTime = timeToScaledTime(beatToTime(beat), headChanges)
            const frac = unlerp(headScaledTime, tailScaledTime, scaledTime)
            const easedFrac = applyEase(ease, frac)
            const lane = lerp(headLane, tailLane, easedFrac)
            const size = lerp(headSize, tailSize, easedFrac)

            return createConnectorAnchor(beat, lane, size, tsg, kind)
        })
    }

    function isReverseHiddenPopConnector(
        headOriginal: ExtendedEntityData | undefined,
        tailOriginal: ExtendedEntityData | undefined,
    ) {
        if (!headOriginal || !tailOriginal) return false
        if (headOriginal.archetype !== 'HiddenSlideStartNote') return false
        if (tailOriginal.archetype !== 'HiddenSlideTickNote') return false

        return getNum(tailOriginal, '#BEAT') < getNum(headOriginal, '#BEAT') - 1e-6
    }

    function isSlideTickRef(ref: number | string | undefined) {
        return [
            'IgnoredSlideTickNote',
            'NormalSlideTickNote',
            'CriticalSlideTickNote',
            'HiddenSlideTickNote',
            'NormalAttachedSlideTickNote',
            'CriticalAttachedSlideTickNote',
        ].includes(resolveOriginal(ext, ref)?.archetype ?? '')
    }

    function isScoredSlideTickRef(ref: number | string | undefined) {
        return [
            'NormalSlideTickNote',
            'CriticalSlideTickNote',
            'NormalAttachedSlideTickNote',
            'CriticalAttachedSlideTickNote',
        ].includes(resolveOriginal(ext, ref)?.archetype ?? '')
    }

    function getUltimateTailRef(
        archetype: string,
        startRef: number | string | undefined,
        tailRef: number | string | undefined,
    ) {
        let ultimateTailRef = tailRef
        let ultimateTailBeat = getNum(
            resolveOriginal(ext, tailRef) ?? { archetype: '', data: [] },
            '#BEAT',
        )
        const visited = new Set<string>()

        function visit(headRef: number | string | undefined) {
            const key = `${String(startRef)}|${String(headRef)}`
            if (headRef === undefined || visited.has(key)) return
            visited.add(key)

            const headConnectors = getConnectorsByHeadRef(headRef)
            const nextConnectors = headConnectors.filter(
                (c) => c.e.archetype === archetype && getField(c.e, 'start') === startRef,
            )
            if (nextConnectors.length === 0) {
                nextConnectors.push(...headConnectors.filter((c) => c.e.archetype === archetype))
            }

            if (nextConnectors.length === 0) {
                const beat = getNum(
                    resolveOriginal(ext, headRef) ?? { archetype: '', data: [] },
                    '#BEAT',
                )
                if (beat >= ultimateTailBeat) {
                    ultimateTailBeat = beat
                    ultimateTailRef = headRef
                }
                return
            }

            for (const nextConnector of nextConnectors) {
                visit(getField(nextConnector.e, 'tail'))
            }
        }

        visit(tailRef)
        if (isScoredSlideTickRef(ultimateTailRef)) {
            for (const connector of getConnectorsByStartRef(startRef)) {
                if (connector.e.archetype !== archetype) continue

                const candidateTailRef = getField(connector.e, 'tail')
                const candidateTailBeat = getNum(
                    resolveOriginal(ext, candidateTailRef) ?? { archetype: '', data: [] },
                    '#BEAT',
                )
                if (candidateTailBeat > ultimateTailBeat) {
                    ultimateTailBeat = candidateTailBeat
                    ultimateTailRef = candidateTailRef
                }
            }
        }
        return ultimateTailRef
    }

    function getUltimateStartRef(
        archetype: string,
        startRef: number | string | undefined,
        headRef: number | string | undefined,
    ) {
        if (!isSlideTickRef(headRef)) return startRef

        let ultimateStartRef = startRef
        const visited = new Set<string>()

        function visit(currentHeadRef: number | string | undefined) {
            const key = `${archetype}|${String(currentHeadRef)}`
            if (currentHeadRef === undefined || visited.has(key)) return
            visited.add(key)
            if (!isSlideTickRef(currentHeadRef)) return

            const tailConnectors = getConnectorsByTailRef(currentHeadRef)
            let previousConnectors = tailConnectors.filter((c) => c.e.archetype === archetype)
            if (previousConnectors.length === 0) {
                previousConnectors = tailConnectors.filter(
                    (c) => c.e.archetype in activeConnectorKindMapping,
                )
            }

            for (const previousConnector of previousConnectors) {
                const previousStartRef = getField(previousConnector.e, 'start')
                ultimateStartRef = previousStartRef

                visit(getField(previousConnector.e, 'head'))
            }
        }

        visit(headRef)
        return ultimateStartRef
    }

    function setInferredActiveHead(note: EntityBuilder, activeHead: EntityBuilder) {
        if (note.refs.activeHead) return

        note.set('activeHead', activeHead)
    }

    function isIgnoredSlideTickRef(ref: number | string | undefined) {
        return resolveOriginal(ext, ref)?.archetype === 'IgnoredSlideTickNote'
    }

    function getNextConnectorWithHead(
        archetype: string,
        startRef: number | string | undefined,
        headRef: number | string | undefined,
    ) {
        const headConnectors = getConnectorsByHeadRef(headRef)
        return (
            headConnectors.find(
                ({ e }) => e.archetype === archetype && getField(e, 'start') === startRef,
            ) ?? headConnectors.find(({ e }) => e.archetype === archetype)
        )
    }

    function resolveConnectorTailRef(
        archetype: string,
        startRef: number | string | undefined,
        tailRef: number | string | undefined,
    ) {
        const skippedNoteRefs: (number | string)[] = []
        const skippedConnectors: { idx: number; e: ExtendedEntityData }[] = []
        const visited = new Set<string>()
        let resolvedTailRef = tailRef

        while (isIgnoredSlideTickRef(resolvedTailRef)) {
            if (resolvedTailRef === undefined) break

            const key = String(resolvedTailRef)
            if (visited.has(key)) break
            visited.add(key)
            skippedNoteRefs.push(resolvedTailRef)

            const nextConnector = getNextConnectorWithHead(archetype, startRef, resolvedTailRef)
            if (!nextConnector) break

            skippedConnectors.push(nextConnector)
            resolvedTailRef = getField(nextConnector.e, 'tail')
        }

        return { tailRef: resolvedTailRef, skippedNoteRefs, skippedConnectors }
    }

    function refKey(ref: number | string | undefined) {
        const original = resolveOriginal(ext, ref)
        const index = original ? (ext.indexByEntity.get(original) ?? -1) : -1

        return index >= 0 ? `index:${index}` : `${typeof ref}:${String(ref)}`
    }

    function getRefBeat(ref: number | string | undefined) {
        return getNum(resolveOriginal(ext, ref) ?? { archetype: '', data: [] }, '#BEAT')
    }

    function getConnectorActiveStartRef(
        archetype: string,
        startRef: number | string | undefined,
        headRef: number | string | undefined,
        endRef: number | string | undefined,
    ) {
        if (endRef !== undefined) return startRef

        return getUltimateStartRef(archetype, startRef, headRef)
    }

    const activeTailRefsByStart = new Map<string, number | string | undefined>()

    function getActiveTailRef(activeStartRef: number | string | undefined) {
        const key = refKey(activeStartRef)
        if (activeTailRefsByStart.has(key)) return activeTailRefsByStart.get(key)

        let activeTailRef: number | string | undefined
        let activeTailBeat = Number.NEGATIVE_INFINITY

        for (const { e } of ext.connectors) {
            const startRef = getField(e, 'start')
            const headRef = getField(e, 'head')
            if (isIgnoredSlideTickRef(headRef)) continue

            const endRef = getField(e, 'end')
            const connectorActiveStartRef = getConnectorActiveStartRef(
                e.archetype,
                startRef,
                headRef,
                endRef,
            )
            if (refKey(connectorActiveStartRef) !== key) continue

            const { tailRef } = resolveConnectorTailRef(e.archetype, startRef, getField(e, 'tail'))
            const candidateTailRef =
                endRef ?? getUltimateTailRef(e.archetype, activeStartRef, tailRef)
            const candidateTailBeat = getRefBeat(candidateTailRef)
            if (candidateTailBeat >= activeTailBeat) {
                activeTailBeat = candidateTailBeat
                activeTailRef = candidateTailRef
            }
        }

        activeTailRefsByStart.set(key, activeTailRef)
        return activeTailRef
    }

    for (const { idx, e } of ext.connectors) {
        const startRef = getField(e, 'start')
        const headRef = getField(e, 'head')
        if (isIgnoredSlideTickRef(headRef)) continue

        const { tailRef, skippedNoteRefs, skippedConnectors } = resolveConnectorTailRef(
            e.archetype,
            startRef,
            getField(e, 'tail'),
        )
        if (isIgnoredSlideTickRef(tailRef)) continue

        const tail = getNote(tailRef)
        const rawHeadOriginal = resolveOriginal(ext, headRef)
        const tailOriginal = resolveOriginal(ext, tailRef)
        const rawHead = getNote(headRef)

        const endRef = getField(e, 'end')
        const activeStartRef = getConnectorActiveStartRef(e.archetype, startRef, headRef, endRef)
        const activeHead = getNote(activeStartRef)
        const usesStartAsHead = shouldUseStartAsHead(startRef, headRef)
        const head = usesStartAsHead ? activeHead : rawHead
        const headOriginal = resolveOriginal(ext, usesStartAsHead ? startRef : headRef)

        let activeTail = getNote(endRef ?? getActiveTailRef(activeStartRef))

        if (!activeTail) {
            activeTail = getNote(getActiveTailRef(activeStartRef))
        }

        if (!activeTail) {
            activeTail = tail
        }

        if (!head || !tail || !activeHead || !activeTail) continue

        const kind = activeConnectorKindMapping[e.archetype]
        const ease = easeTypeMapping[getNum(e, 'ease')] ?? EaseType.LINEAR
        const tsg = headOriginal ? getTSG(getField(headOriginal, 'timeScaleGroup')) : undefined
        const reverseHiddenPopConnector = isReverseHiddenPopConnector(rawHeadOriginal, tailOriginal)
        const splitAnchors =
            headOriginal && tailOriginal && !reverseHiddenPopConnector
                ? getConnectorSplitAnchors(headOriginal, tailOriginal, tsg, kind, ease)
                : []
        const segmentEase = splitAnchors.length > 0 ? EaseType.LINEAR : ease
        const segmentNotes = [head, ...splitAnchors, tail]
        const segments: ConnectorSegmentLink[] = []

        if (reverseHiddenPopConnector && rawHeadOriginal && tailOriginal) {
            const segmentHead = createConnectorAnchor(
                getNum(rawHeadOriginal, '#BEAT'),
                getNum(rawHeadOriginal, 'lane'),
                getNum(rawHeadOriginal, 'size'),
                getTSG(getField(rawHeadOriginal, 'timeScaleGroup')) ?? tsg,
                kind,
            )
            const connector = new EntityBuilder('Connector')
            connector.set('head', head)
            connector.set('tail', tail)
            connector.set('segmentHead', segmentHead)
            connector.set('segmentTail', tail)
            connector.set('legacyHiddenPop', 1)
            connector.set('activeHead', activeHead)
            connector.set('activeTail', activeTail)
            finalEntities.push(connector)
            setInferredActiveHead(segmentHead, activeHead)
            segments.push({ head: segmentHead, tail })
        } else {
            for (let i = 0; i < segmentNotes.length - 1; i++) {
                const segmentHead = segmentNotes[i]
                const segmentTail = segmentNotes[i + 1]

                const connector = new EntityBuilder('Connector')
                connector.set('head', segmentHead)
                connector.set('tail', segmentTail)
                connector.set('segmentHead', segmentHead)
                connector.set('segmentTail', segmentTail)
                connector.set('activeHead', activeHead)
                connector.set('activeTail', activeTail)
                finalEntities.push(connector)
                segments.push({ head: segmentHead, tail: segmentTail })
            }
        }

        const connectorLink: ConnectorLink = {
            head,
            tail,
            activeHead,
            activeTail,
            segments,
        }

        for (const segmentHead of segmentNotes.slice(0, -1)) {
            segmentHead.set('connectorEase', segmentEase)
            segmentHead.set('segmentKind', kind)
            segmentHead.set('segmentAlpha', 1)
        }

        tail.set('segmentKind', kind)
        tail.set('segmentAlpha', 1)
        activeHead.set('segmentKind', kind)
        for (const segmentNote of segmentNotes) {
            setInferredActiveHead(segmentNote, activeHead)
        }
        setInferredActiveHead(activeTail, activeHead)
        for (const skippedNoteRef of skippedNoteRefs) {
            const skippedNote = getNote(skippedNoteRef)
            if (!skippedNote) continue

            skippedNote.set('attachHead', head)
            skippedNote.set('attachTail', tail)
            skippedNote.set('isAttached', 1)
            setInferredActiveHead(skippedNote, activeHead)
        }

        connectorsByIndex.set(idx, connectorLink)
        if (e.name) connectorsByName.set(e.name, connectorLink)
        for (const skippedConnector of skippedConnectors) {
            connectorsByIndex.set(skippedConnector.idx, connectorLink)
            if (skippedConnector.e.name)
                connectorsByName.set(skippedConnector.e.name, connectorLink)
        }
    }

    function getConn(ref: number | string | undefined) {
        if (typeof ref === 'number') return connectorsByIndex.get(ref)
        if (typeof ref === 'string') return connectorsByName.get(ref)
        return undefined
    }

    function getAttachSegment(conn: ConnectorLink, beat: number) {
        for (const segment of conn.segments) {
            const headBeat = segment.head.getBeat()
            const tailBeat = segment.tail.getBeat()
            const minBeat = Math.min(headBeat, tailBeat)
            const maxBeat = Math.max(headBeat, tailBeat)

            if (minBeat - 1e-6 <= beat && beat <= maxBeat + 1e-6) {
                return segment
            }
        }

        return { head: conn.head, tail: conn.tail }
    }

    for (const [idx, note] of notesByIndex.entries()) {
        const e = ext.get(idx)

        const tsgRef = getField(e, 'timeScaleGroup')
        const tsg = getTSG(tsgRef)
        note.set('#TIMESCALE_GROUP', tsg || defaultTsg)

        const attachRef = getField(e, 'attach')
        if (attachRef !== undefined) {
            const attachConn = getConn(attachRef)
            if (attachConn) {
                const attachSegment = getAttachSegment(attachConn, getNum(e, '#BEAT'))
                note.set('attachHead', attachSegment.head)
                note.set('attachTail', attachSegment.tail)
                note.set('isAttached', 1)
            }
        }

        const slideRef = getField(e, 'slide')
        if (slideRef !== undefined) {
            const slideConn = getConn(slideRef)
            if (slideConn) {
                note.set('activeHead', slideConn.activeHead)
            }
        }
    }

    for (const { e } of ext.getByArch('SimLine')) {
        const a = getNote(getField(e, 'a'))
        const b = getNote(getField(e, 'b'))
        if (a && b) {
            const sim = new EntityBuilder('SimLine')
            sim.set('left', a)
            sim.set('right', b)
            finalEntities.push(sim)
        }
    }

    const anchorsByBeat = new Map<number, EntityBuilder[]>()
    const anchorPositions = new Map<EntityBuilder, Set<string>>()

    function getAnchor(
        beat: number,
        lane: number,
        size: number,
        tsg: EntityBuilder | undefined,
        pos: string,
        segmentKind = -1,
        segmentAlpha = -1,
        connectorEase = -1,
    ) {
        const anchorTsg = tsg ?? defaultTsg
        const anchors = anchorsByBeat.get(beat) || []
        for (const anchor of anchors) {
            const positions = anchorPositions.get(anchor)
            if (positions?.has(pos)) continue

            if (
                anchor.values.lane === lane &&
                anchor.values.size === size &&
                anchor.refs['#TIMESCALE_GROUP'] === anchorTsg &&
                (segmentKind === -1 ||
                    anchor.values.segmentKind === segmentKind ||
                    anchor.values.segmentKind === -1) &&
                (segmentAlpha === -1 ||
                    anchor.values.segmentAlpha === segmentAlpha ||
                    anchor.values.segmentAlpha === -1) &&
                (connectorEase === -1 ||
                    anchor.values.connectorEase === connectorEase ||
                    anchor.values.connectorEase === -1)
            ) {
                if (segmentKind !== -1 && anchor.values.segmentKind === -1)
                    anchor.set('segmentKind', segmentKind)
                if (segmentAlpha !== -1 && anchor.values.segmentAlpha === -1)
                    anchor.set('segmentAlpha', segmentAlpha)
                if (connectorEase !== -1 && anchor.values.connectorEase === -1)
                    anchor.set('connectorEase', connectorEase)

                positions?.add(pos)
                return anchor
            }
        }

        const newAnchor = new EntityBuilder('AnchorNote')
        newAnchor.set('#BEAT', beat)
        newAnchor.set('lane', lane)
        newAnchor.set('size', size)
        newAnchor.set('direction', FlickDirection.UP_OMNI)
        newAnchor.set('#TIMESCALE_GROUP', anchorTsg)
        newAnchor.set('segmentKind', segmentKind)
        newAnchor.set('segmentAlpha', segmentAlpha)
        newAnchor.set('segmentLayer', 0)
        newAnchor.set('connectorEase', connectorEase)

        newAnchor.set('isAttached', 0)
        newAnchor.set('isSeparator', 0)

        finalEntities.push(newAnchor)

        if (!anchorsByBeat.has(beat)) anchorsByBeat.set(beat, [])
        anchorsByBeat.get(beat)?.push(newAnchor)
        anchorPositions.set(newAnchor, new Set([pos]))

        return newAnchor
    }

    for (const { e } of ext.getByArch('Guide')) {
        const startBeat = getNum(e, 'startBeat')
        const startLane = getNum(e, 'startLane')
        const startSize = getNum(e, 'startSize')
        const startTsg = getTSG(getField(e, 'startTimeScaleGroup'))

        const headBeat = getNum(e, 'headBeat')
        const headLane = getNum(e, 'headLane')
        const headSize = getNum(e, 'headSize')
        const headTsg = getTSG(getField(e, 'headTimeScaleGroup'))

        const tailBeat = getNum(e, 'tailBeat')
        const tailLane = getNum(e, 'tailLane')
        const tailSize = getNum(e, 'tailSize')
        const tailTsg = getTSG(getField(e, 'tailTimeScaleGroup'))

        const endBeat = getNum(e, 'endBeat')
        const endLane = getNum(e, 'endLane')
        const endSize = getNum(e, 'endSize')
        const endTsg = getTSG(getField(e, 'endTimeScaleGroup'))

        const ease = easeTypeMapping[getNum(e, 'ease', 0)] ?? EaseType.LINEAR
        const [startAlpha, endAlpha] = fadeAlphaMapping[getNum(e, 'fade', 1)] ?? [1.0, 1.0]
        const kind = guideKindMapping[getNum(e, 'color', 0)] ?? ConnectorKind.GUIDE_NEUTRAL

        const start = getAnchor(
            startBeat,
            startLane,
            startSize,
            startTsg,
            'segment_head',
            kind,
            startAlpha,
        )
        const end = getAnchor(endBeat, endLane, endSize, endTsg, 'segment_tail', kind, endAlpha)
        const head = getAnchor(headBeat, headLane, headSize, headTsg, 'head', kind, -1, ease)
        const tail = getAnchor(tailBeat, tailLane, tailSize, tailTsg, 'tail', kind)

        const connector = new EntityBuilder('Connector')
        connector.set('head', head)
        connector.set('tail', tail)
        connector.set('segmentHead', start)
        connector.set('segmentTail', end)
        finalEntities.push(connector)
    }

    for (const list of anchorsByBeat.values()) {
        for (const anchor of list) {
            if (anchor.values.segmentKind === -1)
                anchor.set('segmentKind', ConnectorKind.GUIDE_NEUTRAL)
            if (anchor.values.segmentAlpha === -1) anchor.set('segmentAlpha', 1.0)
            if (anchor.values.connectorEase === -1) anchor.set('connectorEase', EaseType.LINEAR)
        }
    }

    finalEntities.sort((a, b) => {
        const isAInit = a.archetype === 'Initialization' ? 1 : 0
        const isBInit = b.archetype === 'Initialization' ? 1 : 0
        if (isAInit !== isBInit) return isBInit - isAInit

        return a.getBeat() - b.getBeat()
    })

    for (const e of finalEntities) {
        if (e.archetype === 'Connector') {
            const head = e.refs.head
            const tail = e.refs.tail
            if (head && tail) {
                head.set('next', tail)
            }
        }
    }

    const entityToName = new Map<EntityBuilder, string>()
    finalEntities.forEach((e, i) => {
        entityToName.set(e, i.toString(16))
    })

    const serializedEntities: LevelDataEntity[] = finalEntities.map((e) => {
        const data: ({ name: string; value: number } | { name: string; ref: string })[] = []

        for (const [key, val] of Object.entries(e.values)) {
            data.push({ name: key, value: val })
        }
        for (const [key, refObj] of Object.entries(e.refs)) {
            data.push({ name: key, ref: entityToName.get(refObj) ?? '' })
        }

        return {
            archetype: e.archetype,
            name: entityToName.get(e) ?? '',
            data,
        }
    })

    return {
        bgmOffset: data.bgmOffset + offset,
        entities: serializedEntities,
    }
}
