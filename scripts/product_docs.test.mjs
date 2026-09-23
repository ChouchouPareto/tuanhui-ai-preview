import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ROOT, check, validateCatalog, safeFile, safeLabel, fenceFor, sha256, renderSnapshot, saveExclusive } from './product_docs.mjs';

const read = relative => JSON.parse(fs.readFileSync(path.join(ROOT, relative), 'utf8'));
const prd = fs.readFileSync(path.join(ROOT, 'PRD.md'), 'utf8');
const catalog = read('docs/product/requirements.json');
const dataset = read('docs/evaluation/intent_cases.json');

test('current managed documents and references are internally consistent', () => {
  const result = check();
  assert.equal(result.requirements, 20);
  assert.ok(result.seed_cases >= 40);
});

test('duplicate requirements and unknown case references are rejected', () => {
  const badCatalog = structuredClone(catalog);
  badCatalog.requirements.push(badCatalog.requirements[0]);
  const badCases = structuredClone(dataset);
  badCases.cases[0].requirement_ids = ['R999'];
  const errors = validateCatalog(prd, badCatalog, badCases).join('\n');
  assert.match(errors, /Duplicate tracked/);
  assert.match(errors, /unknown requirement/);
});

test('invalid statuses and contradictory side-effect assertions are rejected', () => {
  const badCatalog = structuredClone(catalog);
  badCatalog.requirements[0].verification = 'everything_done';
  const badCases = structuredClone(dataset);
  badCases.cases[0].expected.allowed_actions.push('generate_image');
  assert.match(validateCatalog(prd, badCatalog, badCases).join('\n'), /invalid verification/);
  assert.match(validateCatalog(prd, badCatalog, badCases).join('\n'), /contradictory actions/);
});

test('zero-call cases must explicitly forbid generation', () => {
  const bad = structuredClone(dataset);
  bad.cases[0].expected.forbidden_actions = ['overwrite_original'];
  assert.match(validateCatalog(prd, catalog, bad).join('\n'), /must forbid/);
});

test('snapshot label cannot contain path separators and fences preserve nested examples', () => {
  assert.equal(safeLabel('../../中文/label'), '-中文-label');
  const content = '```json\n{}\n```\n';
  assert.equal(fenceFor(content), '````');
  const output = renderSnapshot([{ name: 'example.md', content }], { label: 'test', timestamp: 'fixed' });
  assert.ok(output.includes(`SHA256: ${sha256(content)}`));
  assert.ok(output.includes(`\n\n\`\`\`\`\n${content}\`\`\`\``));
});

test('snapshot exclusive write refuses an existing backup', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'tuanhui-docs-test-'));
  try {
    const target = saveExclusive(directory, 'backup.md', 'original');
    assert.throws(() => saveExclusive(directory, 'backup.md', 'changed'), { code: 'EEXIST' });
    assert.equal(fs.readFileSync(target, 'utf8'), 'original');
  } finally { fs.rmSync(directory, { recursive: true }); }
});

test('source path cannot escape repository, including through symlinks', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'tuanhui-docs-path-test-'));
  try {
    const repo = path.join(directory, 'repo');
    fs.mkdirSync(repo);
    const outside = path.join(directory, 'outside.md');
    fs.writeFileSync(outside, 'not project data');
    fs.symlinkSync(outside, path.join(repo, 'escape.md'));
    assert.throws(() => safeFile(repo, '../outside.md'), /Outside repository/);
    assert.throws(() => safeFile(repo, 'escape.md'), /Symlink outside/);
  } finally { fs.rmSync(directory, { recursive: true }); }
});

test('directory links are valid but directories cannot be snapshotted as files', () => {
  assert.ok(safeFile(ROOT, 'docs/product', { allowDirectory: true }));
  assert.throws(() => safeFile(ROOT, 'docs/product'), /Not a file/);
});
