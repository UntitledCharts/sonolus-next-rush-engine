import { type LevelData, type LevelDataEntity } from '@sonolus/core'

const startArchetypes = new Map([
    ['Sirius Hold Start', 'NormalHeadTapNote'],
    ['Sirius Critical Hold Start', 'CriticalHeadTapNote'],
    ['Sirius Scratch Hold Start', 'NormalHeadTapNote'],
    ['Sirius Critical Scratch Hold Start', 'CriticalHeadTapNote'],
])
const endArchetypes = new Set([
    'Sirius Hold End',
    'Sirius Nontail Hold End',
    'Sirius Scratch Hold End',
    'Sirius Nontail Scratch Hold End',
])

const getValue = (entity: LevelDataEntity, name: string, fallback = 0): number => {
    const field = entity.data.find((field) => field.name === name)
    return field && 'value' in field ? field.value : fallback
}
const setRef = (entity: LevelDataEntity, name: string, target: LevelDataEntity): void => {
    entity.data = entity.data.filter((field) => field.name !== name)
    entity.data.push({ name, ref: target.name! })
}
const setValue = (entity: LevelDataEntity, name: string, value: number): void => {
    entity.data = entity.data.filter((field) => field.name !== name)
    entity.data.push({ name, value })
}
const geometryKey = (entity: LevelDataEntity): string =>
    `${getValue(entity, 'lane')}:${getValue(entity, 'laneLength', 1)}`
const isCriticalHold = (entity: LevelDataEntity): boolean =>
    [101, 111].includes(getValue(entity, 'holdType') % 1000)

/** Convert Sirius LevelData, whose note "beat" fields are seconds, without mutation. */
export const siriusToLeveldata = (sirius: LevelData, offset = 0): LevelData => {
    const usedNames = new Set(
        sirius.entities.flatMap((entity) => (entity.name === undefined ? [] : [entity.name])),
    )
    let nextId = 0
    const newName = (): string => {
        let name: string
        do name = `sirius-${nextId++}`
        while (usedNames.has(name))
        usedNames.add(name)
        return name
    }
    const entities: LevelDataEntity[] = []
    const create = (
        archetype: string,
        data: LevelDataEntity['data'],
        source?: LevelDataEntity,
    ): LevelDataEntity => {
        const entity = { archetype, name: source?.name ?? newName(), data }
        entities.push(entity)
        return entity
    }
    create(
        'Initialization',
        [],
        sirius.entities.find((entity) => entity.archetype === 'Sirius Initialization'),
    )
    // Upstream SUS -> TXT -> LevelData already resolves BPM changes to seconds.
    // At 60 BPM the target #BEAT values retain those exact times.
    create('#BPM_CHANGE', [
        { name: '#BEAT', value: 0 },
        { name: '#BPM', value: 60 },
    ])
    const group = create('#TIMESCALE_GROUP', [])
    const speeds: { beat: number; speed: number; source?: LevelDataEntity }[] = sirius.entities
        .filter((entity) => entity.archetype === '#TIMESCALE_CHANGE')
        .map((entity) => ({
            beat: getValue(entity, '#BEAT'),
            speed: getValue(entity, '#TIMESCALE', 1),
            source: entity,
        }))
        .sort((a, b) => a.beat - b.beat)
    if (speeds.length === 0 || speeds[0].beat > 0) {
        speeds.unshift({ beat: 0, speed: 1, source: undefined })
    }
    let previousChange: LevelDataEntity | undefined
    for (const speed of speeds) {
        const change = create(
            '#TIMESCALE_CHANGE',
            [
                { name: '#BEAT', value: speed.beat },
                { name: '#TIMESCALE', value: speed.speed },
                { name: '#TIMESCALE_SKIP', value: 0 },
                { name: '#TIMESCALE_EASE', value: 0 },
                { name: '#TIMESCALE_GROUP', ref: group.name! },
            ],
            speed.source,
        )
        setRef(previousChange ?? group, previousChange ? 'next' : 'first', change)
        previousChange = change
    }

    const createNote = (
        archetype: string,
        source: LevelDataEntity,
        beat = getValue(source, 'beat'),
        retainName = true,
        scratchSpan = false,
    ): LevelDataEntity => {
        let left = getValue(source, 'lane', 1)
        let width = getValue(source, 'laneLength', 1)
        const scratch = getValue(source, 'scratchLength')
        if (scratchSpan && scratch !== 0) {
            if (scratch < 0) left += width + scratch
            width = Math.abs(scratch)
        }
        return create(
            archetype,
            [
                { name: '#BEAT', value: beat },
                // Sirius lanes start at 1; Next Rush has edges at -6 and 6.
                { name: 'lane', value: left + width / 2 - 7 },
                { name: 'size', value: width / 2 },
                { name: 'direction', value: scratch < 0 ? 1 : scratch > 0 ? 2 : 0 },
                { name: 'isAttached', value: 0 },
                { name: 'connectorEase', value: 1 },
                { name: 'isSeparator', value: 0 },
                { name: 'segmentKind', value: archetype.startsWith('Critical') ? 2 : 1 },
                { name: 'segmentAlpha', value: 1 },
                { name: '#TIMESCALE_GROUP', ref: group.name! },
            ],
            retainName ? source : undefined,
        )
    }
    const notes = new Map<LevelDataEntity, LevelDataEntity>()
    const starts = new Map<string, LevelDataEntity[]>()
    const midpoints = new Map<string, LevelDataEntity[]>()
    const simNotes = new Map<number, LevelDataEntity[]>()
    const addSimNote = (source: LevelDataEntity, note: LevelDataEntity): void => {
        const beat = getValue(source, 'beat')
        const atBeat = simNotes.get(beat) ?? []
        atBeat.push(note)
        simNotes.set(beat, atBeat)
    }
    for (const source of sirius.entities) {
        let archetype = startArchetypes.get(source.archetype)
        if (archetype) {
            const key = geometryKey(source)
            const atLane = starts.get(key) ?? []
            atLane.push(source)
            starts.set(key, atLane)
        } else {
            switch (source.archetype) {
                case 'Sirius Normal Note':
                    archetype = 'NormalTapNote'
                    break
                case 'Sirius Critical Note':
                    archetype = 'CriticalTapNote'
                    break
                case 'Sirius Flick Note':
                    archetype = 'NormalFlickNote'
                    break
                case 'Sirius Sound':
                    archetype = isCriticalHold(source) ? 'CriticalTickNote' : 'NormalTickNote'
                    break
                case 'Sirius Hold Eighth':
                    archetype = 'TransientHiddenTickNote'
                    break
                default:
                    if (!endArchetypes.has(source.archetype)) continue
                    archetype = source.archetype.includes('Nontail')
                        ? 'AnchorNote'
                        : source.archetype.includes('Scratch')
                          ? 'NormalTailTraceFlickNote'
                          : 'NormalTailTraceNote'
                    break
            }
        }
        const note = createNote(
            archetype,
            source,
            getValue(source, 'beat'),
            true,
            endArchetypes.has(source.archetype) && !source.archetype.includes('Nontail'),
        )
        notes.set(source, note)
        if (source.archetype === 'Sirius Sound' || source.archetype === 'Sirius Hold Eighth') {
            const key = geometryKey(source)
            const atLane = midpoints.get(key) ?? []
            atLane.push(source)
            midpoints.set(key, atLane)
        } else if (!source.archetype.includes('Nontail')) {
            addSimNote(source, note)
        }
    }
    for (const atLane of midpoints.values()) {
        atLane.sort((a, b) => getValue(a, 'beat') - getValue(b, 'beat'))
    }

    const usedStarts = new Set<LevelDataEntity>()
    const previousHolds = new Map<string, { end: number; critical: boolean }>()
    const ends = sirius.entities
        .filter((entity) => endArchetypes.has(entity.archetype))
        .sort((a, b) => getValue(a, 'stBeat') - getValue(b, 'stBeat'))
    for (const source of ends) {
        const startBeat = getValue(source, 'stBeat')
        const endBeat = getValue(source, 'beat')
        const tail = notes.get(source)!
        if (endBeat <= startBeat) {
            // Upstream SoundPurple creates a scratch judgement with no hold body.
            tail.archetype = tail.archetype.replace('Tail', '')
            continue
        }
        const key = geometryKey(source)
        const startSource = starts
            .get(key)
            ?.find((note) => !usedStarts.has(note) && getValue(note, 'beat') === startBeat)
        const points = (midpoints.get(key) ?? []).filter(
            (note) => getValue(note, 'beat') > startBeat && getValue(note, 'beat') < endBeat,
        )
        const previous = previousHolds.get(key)
        const critical = startSource
            ? startSource.archetype.includes('Critical')
            : points.some(isCriticalHold) || (previous?.end === startBeat && previous.critical)
        previousHolds.set(key, { end: endBeat, critical })
        if (critical && tail.archetype.startsWith('Normal')) {
            tail.archetype = tail.archetype.replace('Normal', 'Critical')
            setValue(tail, 'segmentKind', 2)
        }
        const head = startSource
            ? notes.get(startSource)!
            : createNote('AnchorNote', source, startBeat, false)
        if (startSource) usedStarts.add(startSource)
        setValue(head, 'segmentKind', critical ? 2 : 1)

        // Scratch tails can extend beyond the hold body. Keep an unscored body
        // endpoint so the connector stays at the original lane and width.
        const bodyTail =
            getValue(tail, 'lane') !== getValue(head, 'lane') ||
            getValue(tail, 'size') !== getValue(head, 'size')
                ? createNote('AnchorNote', source, endBeat, false)
                : tail
        const chain = [head, ...points.map((point) => notes.get(point)!), bodyTail]
        if (bodyTail !== tail) chain.push(tail)
        for (const [index, point] of chain.entries()) {
            setRef(point, 'activeHead', head)
            setValue(point, 'segmentKind', critical ? 2 : 1)
            if (index > 0) setRef(point, 'prev', chain[index - 1])
            if (index < chain.length - 1) setRef(point, 'next', chain[index + 1])
        }
        for (const point of points) {
            if (point.archetype !== 'Sirius Hold Eighth') continue
            const tick = notes.get(point)!
            setValue(tick, 'isAttached', 1)
            setRef(tick, 'attachHead', head)
            setRef(tick, 'attachTail', bodyTail)
        }
        const joints = [
            head,
            ...points
                .filter((point) => point.archetype === 'Sirius Sound')
                .map((point) => notes.get(point)!),
            bodyTail,
        ]
        for (let index = 1; index < joints.length; index++) {
            const connector = create('Connector', [])
            for (const [name, target] of [
                ['head', joints[index - 1]],
                ['tail', joints[index]],
                ['segmentHead', head],
                ['segmentTail', bodyTail],
                ['activeHead', head],
                ['activeTail', tail],
            ] as const) {
                setRef(connector, name, target)
            }
        }
    }

    for (const source of sirius.entities) {
        if (source.archetype !== 'Sirius Sync Line') continue
        const candidates = [...(simNotes.get(getValue(source, 'beat')) ?? [])].sort(
            (a, b) => getValue(a, 'lane') - getValue(b, 'lane'),
        )
        if (candidates.length < 2) continue
        const line = create('SimLine', [], source)
        setRef(line, 'left', candidates[0])
        setRef(line, 'right', candidates[candidates.length - 1])
    }
    return { ...sirius, bgmOffset: sirius.bgmOffset + offset, entities }
}
