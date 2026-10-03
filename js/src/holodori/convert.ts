import { type LevelData, type LevelDataEntity } from '@sonolus/core'

const GUIDE_GHOST = 100
const GUIDE_NEUTRAL = 101
const GUIDE_BLACK = 108
const GUIDE_LAYER = 1
const RGB_FIELDS = new Set(['segmentRed', 'segmentGreen', 'segmentBlue'])

const noteArchetypes = new Set([
    'DamageNote',
    'AnchorNote',
    'TransientHiddenTickNote',
    'TransientHiddenDamageTickNote',
])
for (const critical of ['Normal', 'Critical']) {
    for (const position of ['', 'Head', 'Tail']) {
        for (const kind of ['Tap', 'Flick', 'Trace', 'TraceFlick', 'Release']) {
            noteArchetypes.add(`${critical}${position}${kind}Note`)
        }
    }
    noteArchetypes.add(`${critical}TickNote`)
}
for (const archetype of [...noteArchetypes]) noteArchetypes.add(`Fake${archetype}`)

const supportedArchetypes = new Set([
    ...noteArchetypes,
    'Initialization',
    '#BPM_CHANGE',
    '#TIMESCALE_GROUP',
    '#TIMESCALE_CHANGE',
    'Connector',
    'SimLine',
    'CameraChange',
    'Stage',
    'StageMaskChange',
    'StagePivotChange',
    'StageStyleChange',
    'StageTransformChange',
    'Skill',
    'FeverChance',
    'FeverStart',
])

const getValue = (entity: LevelDataEntity, name: string, fallback = 0): number => {
    const field = entity.data.find((field) => field.name === name)
    return field && 'value' in field ? field.value : fallback
}

const setValue = (entity: LevelDataEntity, name: string, value: number): void => {
    entity.data = entity.data.filter((field) => field.name !== name)
    entity.data.push({ name, value })
}

const clamp01 = (value: number): number => Math.max(0, Math.min(1, value))

/** Alpha values in Next Rush's draw order: white, R, G, B, Y, M, C, black. */
const getGuideAlphas = (entity: LevelDataEntity): number[] => {
    const channels = ['segmentRed', 'segmentGreen', 'segmentBlue']
        .map((name, index) => ({ value: clamp01(getValue(entity, name, 1)), index }))
        .sort((a, b) => a.value - b.value)
    const [low, middle, high] = channels
    const weights = Array<number>(8).fill(0)

    // Express RGB as white + a secondary + a primary + black (weights sum to 1).
    // Purple is treated as magenta. Secondary indices are C, M, Y respectively.
    weights[0] = low.value
    weights[[6, 5, 4][low.index]] = middle.value - low.value
    weights[high.index + 1] = high.value - middle.value
    weights[7] = 1 - high.value

    const alpha = clamp01(getValue(entity, 'segmentAlpha', 1))
    const alphas = Array<number>(8).fill(0)
    let above = 0
    for (let index = 7; index >= 0; index--) {
        const contribution = alpha * weights[index]
        const remaining = 1 - above
        alphas[index] = remaining > 0 ? clamp01(contribution / remaining) : 0
        above += contribution
    }
    return alphas
}

/** Convert Holodori LevelData to Next Rush LevelData without mutating the input. */
export const hldToLeveldata = (hld: LevelData, offset = 0): LevelData => {
    const byName = new Map<string, LevelDataEntity>()
    for (const entity of hld.entities) {
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
        do name = `hld-${nextId++}`
        while (usedNames.has(name))
        usedNames.add(name)
        return name
    }
    const converted = new Map<LevelDataEntity, LevelDataEntity>()
    const guideConnectors: LevelDataEntity[] = []
    const entities: LevelDataEntity[] = []
    const initialization = hld.entities.find((entity) => entity.archetype === 'Initialization')

    const copy = (source: LevelDataEntity, archetype = source.archetype): LevelDataEntity => ({
        archetype,
        name: source.name ?? newName(),
        data: source.data
            .filter((field) => !RGB_FIELDS.has(field.name))
            .map((field) => ({ ...field })),
    })
    const init = initialization ? copy(initialization) : { archetype: 'Initialization', data: [] }
    entities.push(init)
    if (initialization) converted.set(initialization, init)

    for (const source of hld.entities) {
        if (source.archetype === 'Initialization') continue
        const archetype = source.archetype === 'SkillActivationLine' ? 'Skill' : source.archetype
        if (!supportedArchetypes.has(archetype)) continue

        if (archetype === 'Connector') {
            const points = ['head', 'tail', 'segmentHead', 'segmentTail'].map((name) =>
                resolve(source, name),
            )
            if (points.some((point) => !point || !noteArchetypes.has(point.archetype))) continue
            if (getValue(points[2]!, 'segmentKind') === GUIDE_GHOST) {
                guideConnectors.push(source)
                continue
            }
        }
        if (
            archetype === 'SimLine' &&
            ['left', 'right'].some((name) => {
                const point = resolve(source, name)
                return !point || !noteArchetypes.has(point.archetype)
            })
        ) {
            continue
        }

        const entity = copy(source, archetype)
        if (archetype === 'Skill') {
            // Match the SUS -> USC -> LevelData Skill settings (engine defaults).
            entity.data = [{ name: '#BEAT', value: getValue(source, '#BEAT') }]
        } else if (noteArchetypes.has(archetype)) {
            const kind = getValue(source, 'segmentKind')
            if (kind === GUIDE_GHOST) setValue(entity, 'segmentKind', 0)
            if (kind >= GUIDE_NEUTRAL && kind <= GUIDE_BLACK) {
                setValue(entity, 'segmentLayer', GUIDE_LAYER)
                setValue(entity, 'segmentThroughJudgeLine', 1)
            }
        }
        converted.set(source, entity)
        entities.push(entity)
    }

    // Holodori allows overlapping slide heads to share one tap. Keep one tap/flick
    // head per overlapping pair and let the others accept that touch as traces.
    const seenHeads = new Set<LevelDataEntity>()
    const retainedHeadsByBeat = new Map<number, LevelDataEntity[]>()
    for (const [source] of converted) {
        if (source.archetype !== 'Connector') continue
        const segmentHead = resolve(source, 'segmentHead')!
        const kind = getValue(segmentHead, 'segmentKind')
        if (kind >= GUIDE_GHOST && kind <= GUIDE_BLACK) continue

        const head = converted.get(resolve(source, 'head')!)!
        if (seenHeads.has(head)) continue
        seenHeads.add(head)
        if (!/^(Normal|Critical)(Head|Tail)?(Tap|Flick)Note$/.test(head.archetype)) continue

        const beat = getValue(head, '#BEAT')
        const lane = getValue(head, 'lane')
        const size = getValue(head, 'size')
        const retainedHeads = retainedHeadsByBeat.get(beat) ?? []
        const overlaps = retainedHeads.some(
            (other) => Math.abs(lane - getValue(other, 'lane')) < size + getValue(other, 'size'),
        )
        if (overlaps) {
            head.archetype = head.archetype.endsWith('TapNote')
                ? head.archetype.replace('TapNote', 'TraceNote')
                : head.archetype.replace('FlickNote', 'TraceFlickNote')
        } else {
            retainedHeads.push(head)
            retainedHeadsByBeat.set(beat, retainedHeads)
        }
    }

    // Drop references to skipped entities and update names assigned to unnamed entities.
    for (const entity of entities) {
        entity.data = entity.data.flatMap((field): LevelDataEntity['data'] => {
            if (!('ref' in field)) return [field]
            const original = byName.get(field.ref)
            const target = original && converted.get(original)
            return target?.name === undefined ? [] : [{ name: field.name, ref: target.name }]
        })
    }

    const guideNotes = new Map<LevelDataEntity, Map<number, LevelDataEntity>>()
    const alphaCache = new Map<LevelDataEntity, number[]>()
    const alphasFor = (source: LevelDataEntity): number[] => {
        let alphas = alphaCache.get(source)
        if (!alphas) {
            alphas = getGuideAlphas(source)
            alphaCache.set(source, alphas)
        }
        return alphas
    }
    const guideNote = (source: LevelDataEntity, index: number): LevelDataEntity => {
        let layers = guideNotes.get(source)
        if (!layers) {
            layers = new Map()
            guideNotes.set(source, layers)
        }
        const existing = layers.get(index)
        if (existing) return existing

        // Use unscored anchors so RGB overlays never duplicate scored notes or active slides.
        const entity = copy(converted.get(source)!, 'AnchorNote')
        entity.name = newName()
        entity.data = entity.data.filter(
            (field) => !['next', 'prev', 'activeHead'].includes(field.name),
        )
        setValue(entity, 'segmentKind', GUIDE_NEUTRAL + index)
        setValue(entity, 'segmentAlpha', alphasFor(source)[index])
        setValue(entity, 'segmentLayer', GUIDE_LAYER)
        setValue(entity, 'segmentThroughJudgeLine', 1)
        layers.set(index, entity)
        entities.push(entity)
        return entity
    }

    for (const source of guideConnectors) {
        const head = resolve(source, 'head')!
        const tail = resolve(source, 'tail')!
        const segmentHead = resolve(source, 'segmentHead')!
        const segmentTail = resolve(source, 'segmentTail')!
        for (let index = 0; index < 8; index++) {
            if (alphasFor(segmentHead)[index] === 0 && alphasFor(segmentTail)[index] === 0) continue
            entities.push({
                archetype: 'Connector',
                name: newName(),
                data: [
                    { name: 'head', ref: guideNote(head, index).name! },
                    { name: 'tail', ref: guideNote(tail, index).name! },
                    { name: 'segmentHead', ref: guideNote(segmentHead, index).name! },
                    { name: 'segmentTail', ref: guideNote(segmentTail, index).name! },
                ],
            })
        }
    }
    for (const [source, layers] of guideNotes) {
        for (const [index, entity] of layers) {
            for (const name of ['next', 'prev']) {
                const original = resolve(source, name)
                const target = original && guideNotes.get(original)?.get(index)
                if (target?.name !== undefined) entity.data.push({ name, ref: target.name })
            }
        }
    }

    return { ...hld, bgmOffset: hld.bgmOffset + offset, entities }
}
