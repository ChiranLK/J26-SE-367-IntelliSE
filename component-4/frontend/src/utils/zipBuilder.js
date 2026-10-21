/**
 * Pure JavaScript ZIP archive generator using standard Web APIs.
 * Creates standard uncompressed (store-only, method 0) ZIP files compatible with
 * Python zipfile.ZipFile and standard archive extraction utilities.
 */

// Precomputed CRC-32 table for fast checksumming
const CRC_TABLE = new Uint32Array(256);
for (let i = 0; i < 256; i++) {
  let c = i;
  for (let k = 0; k < 8; k++) {
    c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
  }
  CRC_TABLE[i] = c >>> 0;
}

/**
 * Calculates standard CRC-32 checksum for a byte array.
 * @param {Uint8Array} bytes
 * @returns {number} 32-bit unsigned integer
 */
export function calculateCrc32(bytes) {
  let crc = 0 ^ (-1);
  for (let i = 0; i < bytes.length; i++) {
    crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ bytes[i]) & 0xFF];
  }
  return (crc ^ (-1)) >>> 0;
}

/**
 * Creates a standard uncompressed ZIP File from an array of file descriptors.
 * @param {Array<{ name: string, data: string | Uint8Array | ArrayBuffer }>} files
 * @param {string} [archiveName='project_submission.zip']
 * @returns {File}
 */
export function buildZipArchive(files, archiveName = 'project_submission.zip') {
  const encoder = new TextEncoder();
  const localChunks = [];
  const centralChunks = [];
  let localOffset = 0;

  for (const file of files) {
    // Normalize relative path, strip leading slashes and drive letters
    const cleanName = file.name
      .replace(/\\/g, '/')
      .replace(/^([a-zA-Z]:|\/)+/, '')
      .replace(/^\/+/, '');

    const nameBytes = encoder.encode(cleanName || 'unnamed_file.py');

    let dataBytes;
    if (typeof file.data === 'string') {
      dataBytes = encoder.encode(file.data);
    } else if (file.data instanceof Uint8Array) {
      dataBytes = file.data;
    } else if (file.data instanceof ArrayBuffer) {
      dataBytes = new Uint8Array(file.data);
    } else {
      dataBytes = new Uint8Array(0);
    }

    const crc = calculateCrc32(dataBytes);
    const size = dataBytes.byteLength;

    // 1. Local File Header (30 bytes)
    const localHeader = new ArrayBuffer(30);
    const lv = new DataView(localHeader);
    lv.setUint32(0, 0x04034B50, true);       // Local file header signature
    lv.setUint16(4, 20, true);               // Version needed to extract (2.0)
    lv.setUint16(6, 0x0800, true);           // Flags (Bit 11: UTF-8 encoding)
    lv.setUint16(8, 0, true);                // Compression method (0 = Store)
    lv.setUint16(10, 0, true);               // Mod time
    lv.setUint16(12, 0, true);               // Mod date
    lv.setUint32(14, crc, true);             // CRC-32
    lv.setUint32(18, size, true);            // Compressed size
    lv.setUint32(22, size, true);            // Uncompressed size
    lv.setUint16(26, nameBytes.length, true);// File name length
    lv.setUint16(28, 0, true);               // Extra field length

    localChunks.push(new Uint8Array(localHeader), nameBytes, dataBytes);

    // 2. Central Directory Header (46 bytes)
    const centralHeader = new ArrayBuffer(46);
    const cv = new DataView(centralHeader);
    cv.setUint32(0, 0x02014B50, true);       // Central directory header signature
    cv.setUint16(4, 20, true);               // Version made by (2.0)
    cv.setUint16(6, 20, true);               // Version needed (2.0)
    cv.setUint16(8, 0x0800, true);           // Flags (UTF-8)
    cv.setUint16(10, 0, true);               // Compression method (0 = Store)
    cv.setUint16(12, 0, true);               // Mod time
    cv.setUint16(14, 0, true);               // Mod date
    cv.setUint32(16, crc, true);             // CRC-32
    cv.setUint32(20, size, true);            // Compressed size
    cv.setUint32(24, size, true);            // Uncompressed size
    cv.setUint16(28, nameBytes.length, true);// File name length
    cv.setUint16(30, 0, true);               // Extra field length
    cv.setUint16(32, 0, true);               // Comment length
    cv.setUint16(34, 0, true);               // Disk number start
    cv.setUint16(36, 0, true);               // Internal file attributes
    cv.setUint32(38, (0o100644 << 16) >>> 0, true); // External file attributes (regular file 0644)
    cv.setUint32(42, localOffset, true);     // Relative offset of local header

    centralChunks.push(new Uint8Array(centralHeader), nameBytes);

    localOffset += 30 + nameBytes.length + size;
  }

  const centralOffset = localOffset;
  let centralSize = 0;
  for (const chunk of centralChunks) {
    centralSize += chunk.byteLength;
  }

  // 3. End of Central Directory Record (22 bytes)
  const eocd = new ArrayBuffer(22);
  const ev = new DataView(eocd);
  ev.setUint32(0, 0x06054B50, true);         // EOCD signature
  ev.setUint16(4, 0, true);                  // Disk number
  ev.setUint16(6, 0, true);                  // Start disk
  ev.setUint16(8, files.length, true);       // Central directory records on this disk
  ev.setUint16(10, files.length, true);      // Total central directory records
  ev.setUint32(12, centralSize, true);       // Central directory size
  ev.setUint32(16, centralOffset, true);     // Central directory offset
  ev.setUint16(20, 0, true);                 // Comment length

  const allChunks = [...localChunks, ...centralChunks, new Uint8Array(eocd)];
  return new File(allChunks, archiveName, { type: 'application/zip' });
}
