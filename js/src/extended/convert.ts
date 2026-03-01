import { type LevelData, type LevelDataEntity } from '@sonolus/core'

export type ExtendedEntityDataField = {
    name: string
    value?: number
    ref?: string
}

export type ExtendedEntityData = {
    archetype: string
    name?: string
    data: ExtendedEntityDataField[]
}

export type ExtendedLevelData = {
    bgmOffset: number
    entities: ExtendedEntityData[]
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

class ExtData {
    entities: ExtendedEntityData[]
    byArch = new Map<string, { idx: number; e: ExtendedEntityData }[]>()
    notes: { idx: number; e: ExtendedEntityData }[] = []
    connectors: { idx: number; e: ExtendedEntityData }[] = []

    constructor(entities: ExtendedEntityData[]) {
        this.entities = entities
        entities.forEach((e, idx) => {
            const arch = e.archetype
            if (!this.byArch.has(arch)) this.byArch.set(arch, [])
            this.byArch.get(arch)!.push({ idx, e })

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

function getField(e: ExtendedEntityData, name: string): any {
    const field = e.data.find((x) => x.name === name)
    if (!field) return undefined
    if (field.value !== undefined) return field.value
    if (field.ref !== undefined) return field.ref
    return undefined
}

function getNum(e: ExtendedEntityData, name: string, def: number = 0): number {
    const val = getField(e, name)
    return typeof val === 'number' ? val : def
}

function resolveOriginal(
    ext: ExtData,
    ref: number | string | undefined,
): ExtendedEntityData | undefined {
    if (typeof ref === 'number') return ext.get(ref)
    if (typeof ref === 'string') return ext.entities.find((x) => x.name === ref)
    return undefined
}

export const extendedToLevelData = (data: ExtendedLevelData, offset = 0): LevelData | undefined => {
    const ext = new ExtData(data.entities)

    if (ext.getByArch('TimeScaleGroup').length === 0) return undefined

    const finalEntities: EntityBuilder[] = []

    const init = new EntityBuilder('Initialization')
    finalEntities.push(init)

    for (const { e } of ext.getByArch('#BPM_CHANGE')) {
        const bpm = new EntityBuilder('#BPM_CHANGE')
        bpm.set('#BEAT', getNum(e, '#BEAT'))
        bpm.set('#BPM', getNum(e, '#BPM'))
        finalEntities.push(bpm)
    }

    const timescaleGroupsByIndex = new Map<number, EntityBuilder>()
    const timescaleGroupsByName = new Map<string, EntityBuilder>()

    for (const { idx, e } of ext.getByArch('TimeScaleGroup')) {
        const group = new EntityBuilder('#TIMESCALE_GROUP')
        finalEntities.push(group)
        timescaleGroupsByIndex.set(idx, group)
        if (e.name) timescaleGroupsByName.set(e.name, group)

        let rawRef = getField(e, 'first')
        const changes: EntityBuilder[] = []

        while (rawRef !== undefined) {
            const raw = resolveOriginal(ext, rawRef)
            if (!raw) break

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
    }

    function getTSG(ref: any) {
        if (typeof ref === 'number') return timescaleGroupsByIndex.get(ref)
        if (typeof ref === 'string') return timescaleGroupsByName.get(ref)
        return undefined
    }

    const notesByIndex = new Map<number, EntityBuilder>()
    const notesByName = new Map<string, EntityBuilder>()
    const connectorsByIndex = new Map<number, EntityBuilder>()
    const connectorsByName = new Map<string, EntityBuilder>()

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

        note.set('isAttached', 0)
        note.set('connectorEase', 0)
        note.set('isSeparator', 0)

        finalEntities.push(note)
        notesByIndex.set(idx, note)
        if (e.name) notesByName.set(e.name, note)
    }

    function getNote(ref: any) {
        if (typeof ref === 'number') return notesByIndex.get(ref)
        if (typeof ref === 'string') return notesByName.get(ref)
        return undefined
    }

    for (const { idx, e } of ext.connectors) {
        const head = getNote(getField(e, 'head'))
        const tail = getNote(getField(e, 'tail'))
        const segmentHead = getNote(getField(e, 'start'))
        const segmentTail = getNote(getField(e, 'end'))

        if (!head || !tail || !segmentHead || !segmentTail) continue

        const connector = new EntityBuilder('Connector')
        connector.set('head', head)
        connector.set('tail', tail)
        connector.set('segmentHead', segmentHead)
        connector.set('segmentTail', segmentTail)
        connector.set('activeHead', segmentHead)
        connector.set('activeTail', segmentTail)

        head.set('connectorEase', easeTypeMapping[getNum(e, 'ease')] ?? EaseType.LINEAR)

        const kind = activeConnectorKindMapping[e.archetype]
        head.set('segmentKind', kind)
        tail.set('segmentKind', kind)
        segmentHead.set('segmentKind', kind)

        finalEntities.push(connector)
        connectorsByIndex.set(idx, connector)
        if (e.name) connectorsByName.set(e.name, connector)
    }

    function getConn(ref: any) {
        if (typeof ref === 'number') return connectorsByIndex.get(ref)
        if (typeof ref === 'string') return connectorsByName.get(ref)
        return undefined
    }

    for (const [idx, note] of notesByIndex.entries()) {
        const e = ext.get(idx)

        const tsgRef = getField(e, 'timeScaleGroup')
        const tsg = getTSG(tsgRef)
        if (tsg) note.set('#TIMESCALE_GROUP', tsg)

        const attachRef = getField(e, 'attach')
        if (attachRef !== undefined && attachRef !== -1 && attachRef !== 0 && attachRef !== '0') {
            const attachConn = getConn(attachRef)
            if (attachConn && attachConn.refs['head'] && attachConn.refs['tail']) {
                note.set('attachHead', attachConn.refs['head'])
                note.set('attachTail', attachConn.refs['tail'])
                note.set('isAttached', 1)
            }
        }

        const slideRef = getField(e, 'slide')
        if (slideRef !== undefined && slideRef !== -1 && slideRef !== 0 && slideRef !== '0') {
            const slideConn = getConn(slideRef)
            if (slideConn && slideConn.refs['activeHead']) {
                note.set('activeHead', slideConn.refs['activeHead'])
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
        segmentKind: number = -1,
        segmentAlpha: number = -1,
        connectorEase: number = -1,
    ) {
        const anchors = anchorsByBeat.get(beat) || []
        for (const anchor of anchors) {
            const positions = anchorPositions.get(anchor)
            if (positions && positions.has(pos)) continue

            if (
                anchor.values['lane'] === lane &&
                anchor.values['size'] === size &&
                anchor.refs['#TIMESCALE_GROUP'] === tsg &&
                (segmentKind === -1 ||
                    anchor.values['segmentKind'] === segmentKind ||
                    anchor.values['segmentKind'] === -1) &&
                (segmentAlpha === -1 ||
                    anchor.values['segmentAlpha'] === segmentAlpha ||
                    anchor.values['segmentAlpha'] === -1) &&
                (connectorEase === -1 ||
                    anchor.values['connectorEase'] === connectorEase ||
                    anchor.values['connectorEase'] === -1)
            ) {
                if (segmentKind !== -1 && anchor.values['segmentKind'] === -1)
                    anchor.set('segmentKind', segmentKind)
                if (segmentAlpha !== -1 && anchor.values['segmentAlpha'] === -1)
                    anchor.set('segmentAlpha', segmentAlpha)
                if (connectorEase !== -1 && anchor.values['connectorEase'] === -1)
                    anchor.set('connectorEase', connectorEase)

                positions?.add(pos)
                return anchor
            }
        }

        const newAnchor = new EntityBuilder('AnchorNote')
        newAnchor.set('#BEAT', beat)
        newAnchor.set('lane', lane)
        newAnchor.set('size', size)
        if (tsg) newAnchor.set('#TIMESCALE_GROUP', tsg)
        newAnchor.set('segmentKind', segmentKind)
        newAnchor.set('segmentAlpha', segmentAlpha)
        newAnchor.set('connectorEase', connectorEase)

        newAnchor.set('isAttached', 0)
        newAnchor.set('isSeparator', 0)

        finalEntities.push(newAnchor)

        if (!anchorsByBeat.has(beat)) anchorsByBeat.set(beat, [])
        anchorsByBeat.get(beat)!.push(newAnchor)
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
            if (anchor.values['segmentKind'] === -1)
                anchor.set('segmentKind', ConnectorKind.GUIDE_NEUTRAL)
            if (anchor.values['segmentAlpha'] === -1) anchor.set('segmentAlpha', 1.0)
            if (anchor.values['connectorEase'] === -1) anchor.set('connectorEase', EaseType.LINEAR)
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
            const head = e.refs['head']
            const tail = e.refs['tail']
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
            data.push({ name: key, ref: entityToName.get(refObj)! })
        }

        return {
            archetype: e.archetype,
            name: entityToName.get(e)!,
            data,
        }
    })

    return {
        bgmOffset: data.bgmOffset + offset,
        entities: serializedEntities,
    }
}
