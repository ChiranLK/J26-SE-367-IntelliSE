import { describe, it, expect } from 'vitest';
import { calculateCrc32, buildZipArchive } from '../utils/zipBuilder';

describe('Pure JS ZIP Builder Utility', () => {
  it('calculates deterministic CRC-32 checksums', () => {
    const encoder = new TextEncoder();
    const data1 = encoder.encode('hello world');
    const crc1 = calculateCrc32(data1);
    expect(crc1).toBe(0x0D4A1185);

    const empty = new Uint8Array(0);
    expect(calculateCrc32(empty)).toBe(0);
  });

  it('builds a valid ZIP File instance with correct headers and file entries', async () => {
    const files = [
      { name: 'main.py', data: 'def solve(): return 42\n' },
      { name: 'utils/helper.py', data: 'def help(): pass\n' },
    ];

    const zipFile = buildZipArchive(files, 'test_project.zip');
    expect(zipFile).toBeInstanceOf(File);
    expect(zipFile.name).toBe('test_project.zip');
    expect(zipFile.type).toBe('application/zip');
    expect(zipFile.size).toBeGreaterThan(0);

    const buffer = await zipFile.arrayBuffer();
    const view = new DataView(buffer);

    // Verify first 4 bytes are standard ZIP local header signature 0x04034B50
    expect(view.getUint32(0, true)).toBe(0x04034B50);
  });
});
