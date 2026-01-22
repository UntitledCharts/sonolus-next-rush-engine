export * from './reader.js'
export * from './writer.js'

import { BinaryReader } from './reader.js'

/**
 * Alias of BinaryReader, for compatibility with the old name.
 * @deprecated Use BinaryReader instead.
 */
export const BinarySeeker = BinaryReader
/**
 * Alias of BinaryReader, for compatibility with the old name.
 * @deprecated Use BinaryReader instead.
 */
export type BinarySeeker = BinaryReader

export default BinarySeeker
