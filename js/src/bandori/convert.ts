import { type LevelData, type LevelDataEntity } from '@sonolus/core'

// Fit seven equal Bandori lanes across the static stage without camera zoom.
const LANE_SCALE = 12 / 7
const NOTE_SIZE = LANE_SCALE / 2

const noteArchetypes: ReadonlyMap<string, string> = new Map([
    ['TapNote', 'NormalTapNote'],
    ['FlickNote', 'NormalFlickNote'],
    ['DirectionalFlickNote', 'NormalFlickNote'],
    ['SlideStartNote', 'NormalHeadTapNote'],
    ['SlideTickNote', 'NormalTickNote'],
    ['SlideEndNote', 'NormalTailReleaseNote'],
    ['SlideEndFlickNote', 'NormalTailFlickNote'],
    ['IgnoredNote', 'AnchorNote'],
])

const getValue = (entity: LevelDataEntity, name: string, fallback = 0): number => {
    const field = entity.data.find((field) => field.name === name)
    return field && 'value' in field ? field.value : fallback
}

const setRef = (entity: LevelDataEntity, name: string, target: LevelDataEntity): void => {
    entity.data = entity.data.filter((field) => field.name !== name)
    entity.data.push({ name, ref: target.name! })
}

/** Convert Bandori engine LevelData (not a Bestdori chart) without mutating it. */
export const bandoriToLeveldata = (bandori: LevelData, offset = 0): LevelData => {
    const byName = new Map<string, LevelDataEntity>()
    for (const entity of bandori.entities) {
        if (entity.name !== undefined) byName.set(entity.name, entity)
    }
    const resolve = (entity: LevelDataEntity, name: string): LevelDataEntity | undefined => {
        const field = entity.data.find((field) => field.name === name)
        return field && 'ref' in field ? byName.get(field.ref) : undefined
    }

    const usedNames = new Set(byName.keys())
    let nextId = 0
    const newName = (): string => {
        let name: string
        do name = `bandori-${nextId++}`
        while (usedNames.has(name))
        usedNames.add(name)
        return name
    }
    const create = (
        archetype: string,
        data: LevelDataEntity['data'],
        source?: LevelDataEntity,
    ): LevelDataEntity => ({ archetype, name: source?.name ?? newName(), data })

    const initialization = create(
        'Initialization',
        [],
        bandori.entities.find((entity) => entity.archetype === 'Initialization'),
    )
    const group = create('#TIMESCALE_GROUP', [])
    const change = create('#TIMESCALE_CHANGE', [
        { name: '#BEAT', value: 0 },
        { name: '#TIMESCALE', value: 1 },
        { name: '#TIMESCALE_SKIP', value: 0 },
        { name: '#TIMESCALE_EASE', value: 0 },
        { name: '#TIMESCALE_GROUP', ref: group.name! },
    ])
    setRef(group, 'first', change)
    const entities = [initialization, group, change]
    const notes = new Map<LevelDataEntity, LevelDataEntity>()

    for (const source of bandori.entities) {
        if (source.archetype === '#BPM_CHANGE') {
            entities.push(
                create(
                    '#BPM_CHANGE',
                    [
                        { name: '#BEAT', value: getValue(source, '#BEAT') },
                        { name: '#BPM', value: getValue(source, '#BPM') },
                    ],
                    source,
                ),
            )
            continue
        }
        const archetype = noteArchetypes.get(source.archetype)
        if (!archetype) continue

        const directional = source.archetype === 'DirectionalFlickNote'
        const width = directional ? getValue(source, 'size', 1) : 1
        const direction = directional ? (getValue(source, 'direction') < 0 ? -1 : 1) : 0
        // A directional flick's lane is its starting lane, not its center.
        const lane = getValue(source, 'lane') + (direction * (width - 1)) / 2
        const note = create(
            archetype,
            [
                { name: '#BEAT', value: getValue(source, '#BEAT') },
                { name: 'lane', value: lane * LANE_SCALE },
                { name: 'size', value: width * NOTE_SIZE },
                { name: 'direction', value: direction < 0 ? 1 : direction > 0 ? 2 : 0 },
                { name: 'isAttached', value: 0 },
                { name: 'connectorEase', value: 1 },
                { name: 'isSeparator', value: 0 },
                { name: 'segmentKind', value: 1 },
                { name: 'segmentAlpha', value: 1 },
                { name: '#TIMESCALE_GROUP', ref: group.name! },
            ],
            source,
        )
        notes.set(source, note)
        entities.push(note)
    }

    const resolveNote = (entity: LevelDataEntity, name: string): LevelDataEntity | undefined => {
        const source = resolve(entity, name)
        return source && notes.get(source)
    }
    for (const [source, note] of notes) {
        const first = source.archetype === 'SlideStartNote' ? note : resolveNote(source, 'first')
        if (first) setRef(note, 'activeHead', first)
        const prev = resolveNote(source, 'prev')
        if (prev) setRef(note, 'prev', prev)
    }

    for (const source of bandori.entities) {
        if (
            source.archetype === 'StraightSlideConnector' ||
            source.archetype === 'CurvedSlideConnector'
        ) {
            const head = resolveNote(source, 'head')
            const tail = resolveNote(source, 'tail')
            const start = resolveNote(source, 'start')
            const end = resolveNote(source, 'end')
            const firstSource = resolve(source, 'first')
            const first = firstSource && notes.get(firstSource)
            if (!head || !tail || !start || !end || !first || !firstSource) continue
            const last = resolveNote(firstSource, 'last') ?? end

            // Both Bandori connector types interpolate linearly between their
            // explicit points; "curved" only selects a different skin sprite.
            const connector = create('Connector', [], source)
            for (const [name, target] of [
                ['head', head],
                ['tail', tail],
                ['segmentHead', start],
                ['segmentTail', end],
                ['activeHead', first],
                ['activeTail', last],
            ] as const) {
                setRef(connector, name, target)
            }
            setRef(head, 'next', tail)
            setRef(tail, 'prev', head)
            setRef(head, 'activeHead', first)
            setRef(tail, 'activeHead', first)
            entities.push(connector)
        } else if (source.archetype === 'SimLine') {
            const a = resolveNote(source, 'a')
            const b = resolveNote(source, 'b')
            if (!a || !b) continue
            const [left, right] = getValue(a, 'lane') <= getValue(b, 'lane') ? [a, b] : [b, a]
            const simLine = create('SimLine', [], source)
            setRef(simLine, 'left', left)
            setRef(simLine, 'right', right)
            entities.push(simLine)
        }
    }

    return { ...bandori, bgmOffset: bandori.bgmOffset + offset, entities }
}
