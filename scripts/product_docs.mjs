import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomUUID } from 'node:crypto';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MANIFEST = 'docs/product/document-manifest.json';
const implementations = new Set(['code_exists', 'partial', 'not_implemented', 'deferred', 'pending_decision', 'docs_ready']);
const verifications = new Set(['not_run', 'historical_report_only', 'static_review', 'offline_passed', 'browser_passed', 'model_evaluated', 'user_accepted']);
export const sha256 = text => createHash('sha256').update(text).digest('hex');
export const safeLabel = label => String(label || 'snapshot').normalize('NFKC').replace(/[^\p{L}\p{N}_-]+/gu, '-').slice(0, 60) || 'snapshot';
export const fenceFor = text => '`'.repeat(Math.max(3, ...[...text.matchAll(/`+/g)].map(m => m[0].length + 1)));

function inside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

export function safeFile(root, relative, { allowDirectory = false } = {}) {
  if (path.isAbsolute(relative)) throw new Error(`Absolute path not allowed: ${relative}`);
  const base = fs.realpathSync(root);
  const resolved = path.resolve(base, relative);
  if (!inside(base, resolved)) throw new Error(`Outside repository: ${relative}`);
  const real = fs.realpathSync(resolved);
  if (!inside(base, real)) throw new Error(`Symlink outside repository: ${relative}`);
  const stat = fs.statSync(real);
  if (!stat.isFile() && !(allowDirectory && stat.isDirectory())) throw new Error(`Not a file: ${relative}`);
  return real;
}

function parse(root, relative) {
  return JSON.parse(fs.readFileSync(safeFile(root, relative), 'utf8'));
}

export function validateCatalog(prd, catalog, dataset) {
  const errors = [];
  const ids = [...prd.matchAll(/^### (R\d+) · /gm)].map(m => m[1]);
  const requirements = catalog.requirements || [];
  const tracked = requirements.map(r => r.id);
  if (!ids.length || new Set(ids).size !== ids.length) errors.push('PRD requirement IDs missing or duplicated');
  if (new Set(tracked).size !== tracked.length) errors.push('Duplicate tracked requirement IDs');
  if ([...ids].sort().join() !== [...tracked].sort().join()) errors.push('PRD and tracking IDs differ');
  for (const r of requirements) {
    if (!implementations.has(r.implementation)) errors.push(`${r.id}: invalid implementation`);
    if (!verifications.has(r.verification)) errors.push(`${r.id}: invalid verification`);
    if (!r.title || !r.next_delivery || !r.evidence?.length || !r.sources?.length) errors.push(`${r.id}: missing traceability`);
  }
  const cases = dataset.cases || [];
  if (cases.length < 40) errors.push('Expected at least 40 regression seed cases');
  if (new Set(cases.map(c => c.id)).size !== cases.length) errors.push('Duplicate case IDs');
  for (const c of cases) {
    const e = c.expected || {};
    if (!/^E\d+$/.test(c.id) || !c.context || !c.message || !e.intent) errors.push(`${c.id}: missing case fields`);
    if (!c.requirement_ids?.length || c.requirement_ids.some(id => !ids.includes(id))) errors.push(`${c.id}: unknown requirement`);
    if (!Array.isArray(e.allowed_actions) || !e.allowed_actions.length || !Array.isArray(e.forbidden_actions) || !e.forbidden_actions.length) {
      errors.push(`${c.id}: missing action assertions`);
      continue;
    }
    if (e.allowed_actions.some(a => e.forbidden_actions.includes(a))) errors.push(`${c.id}: contradictory actions`);
    if (!Number.isInteger(e.max_image_calls) || e.max_image_calls < 0) errors.push(`${c.id}: invalid call limit`);
    if (e.max_image_calls === 0 && !e.forbidden_actions.includes('generate_image')) errors.push(`${c.id}: zero-call case must forbid image generation`);
  }
  return errors;
}

export function check(root = ROOT) {
  const errors = [];
  const manifest = parse(root, MANIFEST);
  const files = manifest.managed_files;
  if (!Array.isArray(files) || !files.length || new Set(files).size !== files.length) throw new Error('Invalid manifest');
  let links = 0;
  const contents = new Map();
  for (const relative of files) {
    // Explicit documentation allowlist only; never scan .env, user uploads or generated art.
    if (!['PRD.md', 'AGENTS.md'].includes(relative) && !relative.startsWith('docs/')) throw new Error(`Not a managed document: ${relative}`);
    if (!/\.(md|json)$/.test(relative) || relative.includes('/snapshots/')) throw new Error(`Invalid managed extension/path: ${relative}`);
    const body = fs.readFileSync(safeFile(root, relative), 'utf8');
    contents.set(relative, body);
    if (relative.endsWith('.json')) {
      try { JSON.parse(body); } catch (error) { errors.push(`${relative}: ${error.message}`); }
    }
    if (!relative.endsWith('.md')) continue;
    for (const match of body.matchAll(/\[[^\]\n]+\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)/g)) {
      const raw = match[1].replace(/^<|>$/g, '');
      if (/^[a-z][a-z\d+.-]*:/i.test(raw) || raw.startsWith('#')) continue;
      const target = decodeURIComponent(raw.split(/[?#]/)[0]);
      try { safeFile(root, path.join(path.dirname(relative), target), { allowDirectory: true }); links++; }
      catch (error) { errors.push(`${relative}: broken/local unsafe link ${raw} (${error.message})`); }
    }
    for (const match of body.matchAll(/^```json\s*\n([\s\S]*?)^```\s*$/gm)) {
      try { JSON.parse(match[1]); } catch (error) { errors.push(`${relative}: invalid JSON example (${error.message})`); }
    }
  }
  const catalog = parse(root, 'docs/product/requirements.json');
  const dataset = parse(root, 'docs/evaluation/intent_cases.json');
  errors.push(...validateCatalog(contents.get('PRD.md') || '', catalog, dataset));
  const sources = contents.get('docs/product/来源与课程接入.md') || '';
  for (const r of catalog.requirements) {
    for (const ref of r.evidence) {
      try { safeFile(root, ref); } catch (error) { errors.push(`${r.id}: missing evidence ${ref}`); }
    }
    for (const id of r.sources) if (!sources.includes(id)) errors.push(`${r.id}: unknown source ${id}`);
  }
  if (errors.length) throw new Error(errors.join('\n'));
  return { files: files.length, links, requirements: catalog.requirements.length, seed_cases: dataset.cases.length, scope: 'document integrity only; not product/model evaluation' };
}

export function renderSnapshot(entries, { label, timestamp }) {
  return `# 产品文档快照\n\n时间：${timestamp}\n\n标签：${safeLabel(label)}\n\n此文件只新增，不覆盖。记录的是文档，不是模型评测或软件发布。\n\n` + entries.map(({ name, content }) => {
    const fence = fenceFor(content);
    return `## ${name}\n\nSHA256: ${sha256(content)}\n\n${fence}\n${content}${content.endsWith('\n') ? '' : '\n'}${fence}\n\n`;
  }).join('');
}

export function saveExclusive(directory, filename, body) {
  if (path.basename(filename) !== filename) throw new Error('Snapshot filename must be a basename');
  const target = path.join(directory, filename);
  fs.writeFileSync(target, body, { encoding: 'utf8', flag: 'wx', mode: 0o600 });
  return target;
}

export function snapshot(root = ROOT, label = 'snapshot') {
  check(root);
  const manifest = parse(root, MANIFEST);
  const entries = manifest.managed_files.map(name => ({ name, content: fs.readFileSync(safeFile(root, name), 'utf8') }));
  const timestamp = new Date().toISOString();
  const base = fs.realpathSync(root);
  const parent = path.dirname(safeFile(base, MANIFEST));
  const directory = path.join(parent, 'snapshots');
  fs.mkdirSync(directory, { recursive: true });
  if (!inside(base, fs.realpathSync(directory))) throw new Error('Snapshot directory outside repository');
  const filename = `${timestamp.replace(/[:.]/g, '-')}_${safeLabel(label)}_${randomUUID()}.md`;
  return saveExclusive(directory, filename, renderSnapshot(entries, { label, timestamp }));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const command = process.argv[2];
    if (command === 'check') console.log(JSON.stringify(check(), null, 2));
    else if (command === 'snapshot') console.log(snapshot(ROOT, process.argv[3]));
    else throw new Error('Usage: node scripts/product_docs.mjs check | snapshot [label]');
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
