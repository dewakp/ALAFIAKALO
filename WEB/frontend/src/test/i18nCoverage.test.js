import { describe, it, expect } from 'vitest';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { extract, cleanJSXText } = require('../../scripts/i18n-extract.cjs');

describe('every screen reads its text from the catalog', () => {
  it('has no hard-coded UI text left to extract', () => {
    // 63 pages rendered English in every language because two of them used t().
    // A new literal is a new screen that ships English-only: run
    // `node scripts/i18n-extract.cjs --apply` and translate the new keys.
    const report = extract({ root: path.resolve(__dirname, '../..') });
    expect(report.added).toEqual([]);
  }, 60_000);

  it('reads JSX text the way JSX renders it', () => {
    // A key must hold what English shows, or the translation is of something else.
    expect(cleanJSXText('\n    Page ')).toBe('Page ');
    expect(cleanJSXText('  Save')).toBe('  Save');
    expect(cleanJSXText('Hello\n      world\n  ')).toBe('Hello world');
    expect(cleanJSXText('\n   \n')).toBe('');
  });
});
