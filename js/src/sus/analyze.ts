type Line = [string, string]

type MeasureChange = [number, number]
type TimeScaleGroupChange = [number, string]

type Meta = Map<string, string[]>

type BarLengthObject = {
    measure: number
    length: number
}

type RawObject = {
    tick: number
    value: string
}

export type TimeScaleChangeObject = {
    tick: number
    timeScale: number
}

export type BpmChangeObject = {
    tick: number
    bpm: number
}

export type NoteObject = {
    tick: number
    lane: number
    width: number
    type: number
    timeScaleGroup: number
}

export type SlideObject = {
    type: number
    notes: NoteObject[]
}

export type Score = {
    offset: number
    ticksPerBeat: number
    timeScaleChanges: TimeScaleChangeObject[][]
    bpmChanges: BpmChangeObject[]
    tapNotes: NoteObject[]
    directionalNotes: NoteObject[]
    slides: SlideObject[]
    meta: Meta
}

type ToTick = (measure: number, p: number, q: number) => number

export const analyze = (sus: string): Score => {
    if (!sus || sus.trim().length === 0) {
        throw new Error('The sus file does not exist')
    }
    const { lines, measureChanges, timeScaleGroupChanges, meta } = parse(sus)

    const offset = -+(meta.get('WAVEOFFSET') || '0')
    if (Number.isNaN(offset)) throw new Error('Unexpected offset')

    const ticksPerBeat = getTicksPerBeat(meta)
    if (!ticksPerBeat) throw new Error('Missing or unexpected ticks per beat')

    const barLengths = getBarLengths(lines, measureChanges)

    const toTick = getToTick(barLengths, ticksPerBeat)

    const bpms = new Map<string, number>()
    const bpmChanges: BpmChangeObject[] = []
    const timeScaleGroups = new Map<string, number>()
    const timeScaleChanges: TimeScaleChangeObject[][] = []
    const tapNotes: NoteObject[] = []
    const directionalNotes: NoteObject[] = []
    const streams = new Map<string, SlideObject>()

    for (const [, timeScaleGroup] of timeScaleGroupChanges) {
        if (timeScaleGroups.has(timeScaleGroup)) continue
        timeScaleGroups.set(timeScaleGroup, timeScaleGroups.size)
        timeScaleChanges.push([])
    }

    // Time Scale Changes
    for (const line of lines) {
        const [header] = line
        if (header.length === 5 && header.startsWith('TIL')) {
            const timeScaleGroup = header.substring(3, 5)
            const timeScaleIndex = timeScaleGroups.get(timeScaleGroup)
            if (timeScaleIndex === undefined) {
                continue
            }
            timeScaleChanges[timeScaleIndex].push(...toTimeScaleChanges(line, toTick))
        }
    }
    lines.forEach((line, index) => {
        const [header, data] = line
        const measureOffset = measureChanges.find(([changeIndex]) => changeIndex <= index)?.[1] ?? 0
        const timeScaleGroupName =
            timeScaleGroupChanges.find(([changeIndex]) => changeIndex <= index)?.[1] ?? '00'
        let timeScaleGroup = timeScaleGroups.get(timeScaleGroupName)
        if (timeScaleGroup === undefined) {
            timeScaleGroup = timeScaleGroups.size
            timeScaleGroups.set(timeScaleGroupName, timeScaleGroups.size)
            timeScaleChanges.push([])
        }

        // Hispeed definitions
        if (header.length === 5 && header.startsWith('TIL')) {
            return
        }

        // BPM
        if (header.length === 5 && header.startsWith('BPM')) {
            bpms.set(header.substring(3), +data)
            return
        }

        // BPM Changes
        if (header.length === 5 && header.endsWith('08')) {
            bpmChanges.push(...toBpmChanges(line, measureOffset, bpms, toTick))
            return
        }

        // Tap Notes
        if (header.length === 5 && header[3] === '1') {
            tapNotes.push(...toNotes(line, measureOffset, timeScaleGroup, toTick))
            return
        }

        // Streams
        if (header.length === 6 && (header[3] === '3' || header[3] === '9')) {
            const key = `${header[5]}-${header[3]}`
            const stream = streams.get(key)

            if (stream) {
                stream.notes.push(...toNotes(line, measureOffset, timeScaleGroup, toTick))
            } else {
                streams.set(key, {
                    type: +header[3],
                    notes: toNotes(line, measureOffset, timeScaleGroup, toTick),
                })
            }
            return
        }

        // Directional Notes
        if (header.length === 5 && header[3] === '5') {
            directionalNotes.push(...toNotes(line, measureOffset, timeScaleGroup, toTick))
            return
        }
    })

    const slides = [...streams.values()].flatMap(toSlides)

    return {
        offset,
        ticksPerBeat,
        timeScaleChanges,
        bpmChanges,
        tapNotes,
        directionalNotes,
        slides,
        meta,
    }
}

const parse = (
    sus: string,
): {
    lines: Line[]
    measureChanges: MeasureChange[]
    timeScaleGroupChanges: TimeScaleGroupChange[]
    meta: Meta
} => {
    const lines: Line[] = []
    const measureChanges: MeasureChange[] = []
    const timeScaleGroupChanges: TimeScaleGroupChange[] = []
    const meta: Meta = new Map()

    sus.split('\n')
        .map((line) => line.trim())
        .filter((line) => line.startsWith('#'))
        .forEach((line) => {
            const isLine = line.includes(':')

            const index = line.indexOf(isLine ? ':' : ' ')
            if (index === -1) return

            const left = line.substring(1, index).trim()
            const right = line.substring(index + 1).trim()

            if (isLine) {
                lines.push([left, right])
            } else if (left === 'MEASUREBS') {
                measureChanges.unshift([lines.length, +right])
            } else if (left === 'HISPEED') {
                timeScaleGroupChanges.unshift([lines.length, right])
            } else {
                if (!meta.has(left)) meta.set(left, [])
                meta.get(left)?.push(right)
            }
        })

    return {
        lines,
        measureChanges,
        timeScaleGroupChanges,
        meta,
    }
}

const getTicksPerBeat = (meta: Map<string, string[]>) => {
    const request = meta.get('REQUEST')
    if (!request) return

    const tpbRequest = request.find((r) => JSON.parse(r).startsWith('ticks_per_beat'))
    if (!tpbRequest) return

    return +JSON.parse(tpbRequest).split(' ')[1]
}

const getBarLengths = (lines: Line[], measureChanges: MeasureChange[]) => {
    const barLengths: BarLengthObject[] = []

    lines.forEach((line, index) => {
        const [header, data] = line

        if (header.length !== 5) return
        if (!header.endsWith('02')) return

        const measure =
            +header.substring(0, 3) +
            (measureChanges.find(([changeIndex]) => changeIndex <= index)?.[1] ?? 0)
        if (Number.isNaN(measure)) return

        barLengths.push({ measure, length: +data })
    })

    return barLengths
}

const getToTick = (barLengths: BarLengthObject[], ticksPerBeat: number): ToTick => {
    let ticks = 0
    const bars = barLengths
        .sort((a, b) => a.measure - b.measure)
        .map(({ measure, length }, i, values) => {
            if (i) {
                const prev = values[i - 1]
                ticks += (measure - prev.measure) * prev.length * ticksPerBeat
            }

            return { measure, ticksPerMeasure: length * ticksPerBeat, ticks }
        })
        .reverse()

    return (measure, p, q) => {
        const bar = bars.find((bar) => measure >= bar.measure)
        if (!bar) throw new Error('Unexpected missing bar')

        return (
            bar.ticks +
            (measure - bar.measure) * bar.ticksPerMeasure +
            (p * bar.ticksPerMeasure) / q
        )
    }
}

const toBpmChanges = (
    line: Line,
    measureOffset: number,
    bpms: Map<string, number>,
    toTick: ToTick,
) =>
    toRaws(line, measureOffset, toTick).map(({ tick, value }) => ({
        tick,
        bpm: bpms.get(value) ?? 0,
    }))

const toTimeScaleChanges = ([, data]: Line, toTick: ToTick) => {
    if (!data.startsWith('"') || !data.endsWith('"'))
        throw new Error('Unexpected time scale changes')

    return data
        .slice(1, -1)
        .split(',')
        .map((segment) => segment.trim())
        .filter((segment) => !!segment)
        .map((segment) => {
            const [l, rest] = segment.split("'")
            const [m, r] = rest.split(':')

            const measure = +l
            const tick = +m
            const timeScale = +r

            if (Number.isNaN(measure) || Number.isNaN(tick) || Number.isNaN(timeScale))
                throw new Error('Unexpected time scale change')

            return {
                tick: toTick(measure, 0, 1) + tick,
                timeScale,
            }
        })
        .sort((a, b) => a.tick - b.tick)
}

const toNotes = (line: Line, measureOffset: number, timeScaleGroup: number, toTick: ToTick) => {
    const [header] = line
    const lane = parseInt(header[4], 36)

    return toRaws(line, measureOffset, toTick).map(({ tick, value }) => {
        const width = parseInt(value[1], 36)

        return {
            tick,
            lane,
            width,
            type: parseInt(value[0], 36),
            timeScaleGroup,
        }
    })
}

const toSlides = (stream: SlideObject) => {
    const slides: SlideObject[] = []

    let notes: NoteObject[] | undefined
    for (const note of stream.notes.sort((a, b) => a.tick - b.tick)) {
        if (!notes) {
            notes = []
            slides.push({
                type: stream.type,
                notes,
            })
        }

        notes.push(note)

        if (note.type === 2) {
            notes = undefined
        }
    }

    return slides
}

const toRaws = ([header, data]: Line, measureOffset: number, toTick: ToTick) => {
    const measure = +header.substring(0, 3) + measureOffset
    return (data.match(/.{2}/g) ?? [])
        .map(
            (value, i, values) =>
                value !== '00' && {
                    tick: toTick(measure, i, values.length),
                    value,
                },
        )
        .filter((object): object is RawObject => !!object)
}
