/**
 * Move the web app's hard-coded UI text into src/locales/en.json as t() calls.
 *
 *   docker compose --profile test run --rm frontend-test node scripts/i18n-extract.cjs [--apply]
 *
 * src/test/i18nCoverage.test.js runs this without --apply and fails if it would
 * add a key, so new screens cannot ship English-only.
 *
 * Sources are edited by splicing at parser locations, never by reprinting the
 * AST, so every line the conversion does not touch stays byte-identical. A
 * second run converts only what is new.
 *
 * 1. JSX text and the placeholder, title, alt, aria-label and label attributes.
 *    - Text mixed with simple expressions becomes ONE key with interpolation, so
 *      the translator controls word order:
 *          Page {safePage} of {totalPages}  ->  "Page {{safePage}} of {{totalPages}}"
 *    - A string literal inside the text is text: `our{' '}` is "our ".
 *    - One conditional choosing between two literals becomes two sentences:
 *          {n} patient{n !== 1 ? 's' : ''}  ->  "{{n}} patients" | "{{n}} patient"
 *    - Whitespace follows JSX's own rules (Babel's cleanJSXElementLiteralChild).
 *
 * 2. Labels held in data — `{ to: '/labs', label: 'Lab Tests' }`.
 *    - At module scope the property becomes a getter, `get label() { return t(…) }`:
 *      a value computed at import would never change language.
 *    - Inside a function, only objects in an array (option lists, tabs) convert.
 *    - Never an object passed to a call — that is a payload or initial state.
 *    - Never a lone lowercase word ("breakfast") — that is an identifier.
 *    - Never a list whose labels the file compares or looks up: Wellness matches
 *      WHATIF_INPUTS[].label against the backend's biomarker names, and a
 *      translated label would silently match nothing (CLAUDE.md §3aw).
 *
 * 3. Messages — alert(), confirm(), set…Error/Message/Status(…) and the
 *    fallback in apiErrorMessage / firebaseErrorMessage(err, '…'). Only a
 *    sentence (a space, or closing punctuation): setStatus('loading') is a
 *    state, not a message.
 *
 * `t` is src/i18n.js's plain function, not the hook, so it works in any function;
 * main.jsx remounts the app when the language changes. Where a file already
 * binds its own `t` (`.map((t) => …)`), the import is aliased to `translate`.
 */
const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const traverse = require('@babel/traverse').default;

const ATTRS = new Set(['placeholder', 'title', 'alt', 'aria-label', 'label']);
const VERBATIM = new Set(['pre', 'code', 'style', 'script']);
const INLINE = new Set([
  'Identifier', 'MemberExpression', 'OptionalMemberExpression', 'CallExpression', 'OptionalCallExpression',
  'BinaryExpression', 'LogicalExpression', 'ConditionalExpression', 'TemplateLiteral', 'StringLiteral',
  'NumericLiteral', 'UnaryExpression',
]);
const UTILITY_OBJECTS = /^(Math|Number|String|JSON|Object|Array|Date|Intl)$/;
const DATA_LABELS = /^(label|title|subtitle|description|desc|placeholder|hint|heading|tooltip|text|cta|helperText|emptyText)$/;
const MESSAGE_CALL = /^(alert|confirm|set\w*(Error|Message|Notice|Success|Warning|Info|Status|Toast|Feedback))$/;
const FALLBACK_CALL = /^(apiErrorMessage|firebaseErrorMessage)$/;
const MESSAGE_FIELDS = /^(text|message|title|detail)$/;
const LOOKUP_METHODS = /^(startsWith|endsWith|includes|indexOf|localeCompare|has|get)$/;

const worded = (text) =>
  !/:\/\/|\S+@\S+\.\w/.test(text) && (text.match(/\p{L}{2,}/gu) || []).some((w) => w !== w.toUpperCase());
const sentence = (text) => worded(text) && (/\s/.test(text.trim()) || /[.!?…:]$/.test(text.trim()));
const identifierLike = (text) => /^[a-z][a-z0-9_]*$/.test(text);

/** What JSX renders for a text child — Babel's cleanJSXElementLiteralChild. */
function cleanJSXText(value) {
  const lines = value.split(/\r\n|\n|\r/);
  let lastNonEmpty = 0;
  lines.forEach((line, i) => { if (/[^ \t]/.test(line)) lastNonEmpty = i; });
  let out = '';
  lines.forEach((line, i) => {
    let text = line.replace(/\t/g, ' ');
    if (i !== 0) text = text.replace(/^[ ]+/, '');
    if (i !== lines.length - 1) text = text.replace(/[ ]+$/, '');
    if (text) out += text + (i !== lastNonEmpty ? ' ' : '');
  });
  return out;
}

/** The value of a string literal or an expression-free template, else null. */
function literal(node) {
  if (node.type === 'StringLiteral') return node.value;
  if (node.type === 'TemplateLiteral' && !node.expressions.length) return node.quasis[0].value.cooked;
  return null;
}

function someNode(node, test) {
  if (!node || typeof node !== 'object') return false;
  if (test(node)) return true;
  return Object.keys(node).some((key) => {
    if (key === 'loc' || key === 'start' || key === 'end' || key === 'extra') return false;
    const value = node[key];
    return Array.isArray(value) ? value.some((v) => someNode(v, test)) : value && typeof value === 'object' && someNode(value, test);
  });
}

const containsJSX = (node) => someNode(node, (n) => n.type === 'JSXElement' || n.type === 'JSXFragment' || /Function/.test(n.type || ''));

// `{icon} Save`, with icon holding an element, would render "[object Object] Save"
// once interpolated into a string. A value named like an element ends the run.
const ELEMENT_NAME = /(icon|spinner|children|avatar|badge|element|node|component|svg|image|img|logo|indicator)s?$/i;
const namesAnElement = (node) => someNode(node, (n) => n.type === 'Identifier' && ELEMENT_NAME.test(n.name));

function placeholderName(node) {
  for (let guard = 0; guard < 20 && node; guard++) {
    if (node.type === 'Identifier') return node.name;
    if (node.type === 'MemberExpression' || node.type === 'OptionalMemberExpression') {
      if (!node.computed && node.property.type === 'Identifier' && node.property.name !== 'length') return node.property.name;
      node = node.object;
    } else if (node.type === 'CallExpression' || node.type === 'OptionalCallExpression') {
      const callee = node.callee;
      // num(users.total), Math.round(score * 100): the argument names the value, not the helper.
      const helper = callee.type === 'Identifier'
        || (callee.type === 'MemberExpression' && callee.object.type === 'Identifier' && UTILITY_OBJECTS.test(callee.object.name));
      node = helper && node.arguments[0] ? node.arguments[0] : callee.object || callee;
    } else if (node.type === 'LogicalExpression' || node.type === 'BinaryExpression') {
      node = node.left;
    } else {
      break;
    }
  }
  return 'value';
}

function slugOf(text) {
  const words = text.replace(/\{\{\w+\}\}/g, ' ').toLowerCase().match(/[a-z0-9]+/g) || [];
  let slug = '';
  for (const word of words) {
    if (slug.length + word.length + 1 > 40) break;
    slug = slug ? `${slug}_${word}` : word;
  }
  return /^[a-z]/.test(slug) ? slug : `text_${slug}`.replace(/_$/, '');
}

function namespaceFor(file, bases) {
  const base = path.basename(file).replace(/\.jsx?$/, '');
  const ns = bases.get(base) > 1 ? `${path.basename(path.dirname(file))}_${base}` : base;
  return ns.replace(/[^A-Za-z0-9_]/g, '_');
}

function listFiles(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!['test', 'locales', '__tests__'].includes(entry.name)) listFiles(full, out);
    } else if (/\.jsx$/.test(entry.name) && !/\.test\.jsx$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function i18nSpecifier(file, i18nFile) {
  const spec = path.relative(path.dirname(file), i18nFile).replace(/\\/g, '/').replace(/\.js$/, '');
  return spec.startsWith('.') ? spec : `./${spec}`;
}

/** `ARRAY.prop` pairs the file uses as lookup keys, so their labels must stay English. */
function lookupLabels(ast) {
  const keyed = new Set();
  traverse(ast, {
    MemberExpression(p) {
      const { object, property, computed } = p.node;
      if (computed || object.type !== 'Identifier' || property.type !== 'Identifier' || !DATA_LABELS.test(property.name)) return;
      let use = p;   // step through x.label.toLowerCase().trim()
      while (use.parentPath.isMemberExpression({ object: use.node }) && use.parentPath.parentPath.isCallExpression()
        && !LOOKUP_METHODS.test(use.parentPath.node.property.name || '')) {
        use = use.parentPath.parentPath;
      }
      const parent = use.parentPath;
      const lookup = (parent.isBinaryExpression() && /^[!=]==?$/.test(parent.node.operator))
        || (parent.isCallExpression() && use.listKey === 'arguments' && parent.node.callee.type === 'MemberExpression'
          && LOOKUP_METHODS.test(parent.node.callee.property.name || ''))
        || (parent.isMemberExpression({ object: use.node }) && LOOKUP_METHODS.test(parent.node.property.name || ''))
        || (parent.isMemberExpression() && parent.node.computed && use.key === 'property')
        || parent.isSwitchStatement() || parent.isSwitchCase();
      if (!lookup) return;
      const binding = p.scope.getBinding(object.name);
      if (!binding) return;
      const fn = binding.path.parentPath;
      if (binding.kind === 'param' && fn.parentPath && fn.parentPath.isCallExpression()
        && fn.parentPath.node.callee.type === 'MemberExpression' && fn.parentPath.node.callee.object.type === 'Identifier') {
        keyed.add(`${fn.parentPath.node.callee.object.name}.${property.name}`);
      } else if (binding.path.isVariableDeclarator() && binding.path.parentPath.parentPath.isForOfStatement()
        && binding.path.parentPath.parentPath.node.right.type === 'Identifier') {
        keyed.add(`${binding.path.parentPath.parentPath.node.right.name}.${property.name}`);
      } else {
        keyed.add(`${object.name}.${property.name}`);
      }
    },
  });
  return keyed;
}

function convertFile(file, src, ns, catalog, report, i18nFile) {
  const ast = parser.parse(src, { sourceType: 'module', plugins: ['jsx'] });
  const spec = i18nSpecifier(file, i18nFile);
  const imports = ast.program.body.filter((node) => node.type === 'ImportDeclaration');
  const i18nImport = imports.find((node) => [spec, `${spec}.js`].includes(node.source.value));
  const imported = i18nImport && i18nImport.specifiers.find(
    (s) => s.type === 'ImportSpecifier' && (s.imported.name || s.imported.value) === 't');

  const bound = new Set();
  traverse(ast, {
    Scope(p) {
      for (const [name, binding] of Object.entries(p.scope.bindings)) {
        if (!imported || binding.path.node !== imported) bound.add(name);
      }
    },
  });
  // A re-run reuses the import it already added, under whatever name it has.
  const T = imported ? imported.local.name : bound.has('t') ? (bound.has('translate') ? 'i18nT' : 'translate') : 't';

  const keys = catalog[ns] || (catalog[ns] = {});
  const keyFor = (text) => {
    const existing = Object.entries(keys).find(([, value]) => value === text);
    if (existing) return `${ns}.${existing[0]}`;
    const slug = slugOf(text);
    let name = slug;
    for (let n = 2; name in keys; n++) name = `${slug}_${n}`;
    keys[name] = text;
    report.keys++;
    report.added.push(`${path.basename(file)}: ${ns}.${name} = ${JSON.stringify(text)}`);
    return `${ns}.${name}`;
  };
  const call = (key, options) => `${T}('${key}'${options.length ? `, { ${options.join(', ')} }` : ''})`;
  const edits = [];
  const sample = (kind, before, after) => {
    const list = report.samples[kind] || (report.samples[kind] = []);
    if (list.length < 14) list.push(`${ns}: ${before.replace(/\s+/g, ' ').slice(0, 70)}  =>  ${after}`);
  };

  const placeholders = (used, options, expr) => {
    const base = placeholderName(expr).replace(/^\W+|\W+$/g, '') || 'value';
    const count = (used.get(base) || 0) + 1;
    used.set(base, count);
    const name = count === 1 ? base : `${base}${count}`;
    const code = src.slice(expr.start, expr.end);
    options.push(code === name ? name : `${name}: ${code}`);
    return `{{${name}}}`;
  };

  // ── 1. JSX text ────────────────────────────────────────────────────────────
  function convertRun(run) {
    // Blank text and `{' '}` at a run's edges stay where they are. A VALUE at an
    // edge stays in the run: "{count} patients" is one sentence, and a language
    // that puts the number last has to be able to move it.
    const blank = (c) => (c.type === 'JSXText' ? !cleanJSXText(c.value) : (literal(c.expression) ?? 'x').trim() === '');
    while (run.length && blank(run[0])) run.shift();
    while (run.length && blank(run[run.length - 1])) run.pop();
    if (!run.some((c) => c.type === 'JSXText')) return;

    const choice = run.find((c) => c.type === 'JSXExpressionContainer' && c.expression.type === 'ConditionalExpression'
      && literal(c.expression.consequent) !== null && literal(c.expression.alternate) !== null);

    const build = (branch) => {
      const used = new Map();
      const options = [];
      let text = '';
      for (const child of run) {
        if (child.type === 'JSXText') {
          text += cleanJSXText(child.value);
          continue;
        }
        const expr = child.expression;
        if (child === choice) text += literal(branch === 'yes' ? expr.consequent : expr.alternate);
        else if (literal(expr) !== null) text += literal(expr);
        else text += placeholders(used, options, expr);
      }
      return { text: text.trim(), options };
    };

    const yes = build('yes');
    const no = choice ? build('no') : null;
    const words = (text) => worded(text.replace(/\{\{\w+\}\}/g, ' '));
    if (!words(yes.text) && !(no && words(no.text))) return;

    const first = run[0];
    const last = run[run.length - 1];
    const rawFirst = src.slice(first.start, first.end);
    const rawLast = src.slice(last.start, last.end);
    const start = first.start + (rawFirst.length - rawFirst.replace(/^\s+/, '').length);
    const end = last.end - (rawLast.length - rawLast.replace(/\s+$/, '').length);

    let code;
    if (no) {
      const test = src.slice(choice.expression.test.start, choice.expression.test.end);
      code = `{(${test}) ? ${call(keyFor(yes.text), yes.options)} : ${call(keyFor(no.text), no.options)}}`;
      report.choices += 1;
    } else {
      code = `{${call(keyFor(yes.text), yes.options)}}`;
      report[yes.options.length ? 'merged runs' : 'text'] += 1;
    }
    edits.push({ start, end, code });
    if (no || yes.options.length) sample('jsx', src.slice(start, end), no ? `"${yes.text}" | "${no.text}"` : `"${yes.text}"`);
  }

  function convertChildren(children) {
    let run = [];
    for (const child of children) {
      if (child.type === 'JSXText'
        || (child.type === 'JSXExpressionContainer' && INLINE.has(child.expression.type)
          && !containsJSX(child.expression) && !namesAnElement(child.expression))) {
        run.push(child);
      } else {
        convertRun(run);
        run = [];
      }
    }
    convertRun(run);
  }

  // ── 3. messages ────────────────────────────────────────────────────────────
  function convertMessage(node) {
    const used = new Map();
    const options = [];
    let text;
    if (node.type === 'StringLiteral') {
      text = node.value;
    } else if (node.type === 'TemplateLiteral') {
      if (node.expressions.some((e) => containsJSX(e))) return;
      text = node.quasis.map((q, i) => q.value.cooked + (node.expressions[i] ? placeholders(used, options, node.expressions[i]) : '')).join('');
    } else {
      return;
    }
    if (!sentence(text.replace(/\{\{\w+\}\}/g, ' x '))) return;
    const code = call(keyFor(text.trim()), options);
    edits.push({ start: node.start, end: node.end, code });
    report.messages += 1;
    sample('messages', src.slice(node.start, node.end), `"${text.trim()}"`);
  }

  const keyed = lookupLabels(ast);

  traverse(ast, {
    JSXElement(p) {
      const tag = p.node.openingElement.name.name;
      if (VERBATIM.has(tag)) { report['skipped: verbatim tag'] += 1; return; }
      convertChildren(p.node.children);
    },
    JSXFragment(p) { convertChildren(p.node.children); },
    JSXAttribute(p) {
      const value = p.node.value;
      const name = p.node.name.name;
      if (!value || value.type !== 'StringLiteral' || !ATTRS.has(name) || !worded(value.value)) return;
      edits.push({ start: value.start, end: value.end, code: `{${call(keyFor(value.value.trim()), [])}}` });
      report.attributes += 1;
    },

    // ── 2. labels held in data ───────────────────────────────────────────────
    ObjectProperty(p) {
      const { key, value, computed } = p.node;
      const name = computed ? null : key.type === 'Identifier' ? key.name : key.type === 'StringLiteral' ? key.value : null;
      if (!name || !DATA_LABELS.test(name) || value.type !== 'StringLiteral') return;
      const text = value.value.trim();
      if (!worded(text) || identifierLike(text)) return;

      let q = p.parentPath;   // the ObjectExpression
      let inArray = false;
      let declared = null;
      for (;;) {
        const parent = q.parentPath;
        if (!parent) break;
        if (parent.isArrayExpression()) inArray = true;
        else if (!(parent.isObjectProperty() || parent.isObjectExpression() || parent.isSpreadElement())) {
          if ((parent.isCallExpression() || parent.isNewExpression() || parent.isOptionalCallExpression()) && q.listKey === 'arguments') {
            report['skipped: object passed to a call'] += 1;
            return;
          }
          if (parent.isVariableDeclarator() && parent.node.id.type === 'Identifier') declared = parent.node.id.name;
          break;
        }
        q = parent;
      }
      if (declared && keyed.has(`${declared}.${name}`)) {
        report['kept English: compared or looked up'] += 1;
        report.samples.kept = [...new Set([...(report.samples.kept || []), `${ns}: ${declared}[].${name}`])];
        return;
      }

      const moduleScope = !p.getFunctionParent();
      if (moduleScope) {
        if (!declared) return;
        const prop = /^[A-Za-z_$][\w$]*$/.test(name) ? name : `[${JSON.stringify(name)}]`;
        edits.push({ start: p.node.start, end: p.node.end, code: `get ${prop}() { return ${call(keyFor(text), [])}; }` });
        report['data labels (getter)'] += 1;
        sample('data', src.slice(p.node.start, p.node.end), `getter "${text}"`);
      } else if (inArray) {
        edits.push({ start: value.start, end: value.end, code: call(keyFor(text), []) });
        report['data labels (in render)'] += 1;
        sample('data', src.slice(p.node.start, p.node.end), `"${text}"`);
      }
    },

    CallExpression(p) {
      const callee = p.node.callee;
      const calleeName = callee.type === 'Identifier' ? callee.name
        : callee.type === 'MemberExpression' && !callee.computed && callee.object.type === 'Identifier'
          && callee.object.name === 'window' ? callee.property.name : null;
      if (!calleeName) return;
      let target;
      if (MESSAGE_CALL.test(calleeName)) target = p.node.arguments[0];
      else if (FALLBACK_CALL.test(calleeName)) target = p.node.arguments[1];
      if (!target) return;
      if (target.type === 'ObjectExpression') {
        for (const prop of target.properties) {
          const field = prop.type === 'ObjectProperty' && !prop.computed && (prop.key.name || prop.key.value);
          if (field && MESSAGE_FIELDS.test(field)) convertMessage(prop.value);
        }
      } else if (target.type === 'ConditionalExpression') {
        convertMessage(target.consequent);
        convertMessage(target.alternate);
      } else {
        convertMessage(target);
      }
    },
  });

  if (!edits.length) return null;
  edits.sort((a, b) => a.start - b.start);
  const kept = [];
  for (const edit of edits) {
    if (kept.length && edit.start < kept[kept.length - 1].end) { report['skipped: overlapping'] += 1; continue; }
    kept.push(edit);
  }
  let out = src;
  for (const edit of kept.reverse()) out = out.slice(0, edit.start) + edit.code + out.slice(edit.end);
  report.files += 1;
  return imported ? out : addImport(out, spec, T);
}

function addImport(src, spec, T) {
  const specifier = T === 't' ? 't' : `t as ${T}`;
  const ast = parser.parse(src, { sourceType: 'module', plugins: ['jsx'] });
  const imports = ast.program.body.filter((node) => node.type === 'ImportDeclaration');
  const existing = imports.find((node) => [spec, `${spec}.js`].includes(node.source.value));
  if (existing) {
    const named = existing.specifiers.filter((s) => s.type === 'ImportSpecifier');
    if (named.length) {
      const lastNamed = named[named.length - 1];
      return src.slice(0, lastNamed.end) + `, ${specifier}` + src.slice(lastNamed.end);
    }
    const lastSpec = existing.specifiers[existing.specifiers.length - 1];
    return src.slice(0, lastSpec.end) + `, { ${specifier} }` + src.slice(lastSpec.end);
  }
  const at = imports.length ? imports[imports.length - 1].end : 0;
  return src.slice(0, at) + `\nimport { ${specifier} } from '${spec}';` + src.slice(at);
}

/** Scan (and with apply, rewrite) a frontend. Returns the report; report.added lists new keys. */
function extract({ root = process.cwd(), apply = false } = {}) {
  const srcDir = path.join(root, 'src');
  const enFile = path.join(srcDir, 'locales', 'en.json');
  const i18nFile = path.join(srcDir, 'i18n.js');
  const files = listFiles(srcDir);
  const bases = new Map();
  files.forEach((file) => {
    const base = path.basename(file).replace(/\.jsx$/, '');
    bases.set(base, (bases.get(base) || 0) + 1);
  });

  const catalog = JSON.parse(fs.readFileSync(enFile, 'utf8'));
  const report = {
    files: 0, keys: 0, text: 0, 'merged runs': 0, choices: 0, attributes: 0,
    'data labels (getter)': 0, 'data labels (in render)': 0, messages: 0,
    'kept English: compared or looked up': 0, 'skipped: object passed to a call': 0,
    'skipped: verbatim tag': 0, 'skipped: overlapping': 0, samples: {}, added: [],
  };
  const changed = new Map();
  for (const file of files) {
    const src = fs.readFileSync(file, 'utf8');
    const out = convertFile(file, src, namespaceFor(file, bases), catalog, report, i18nFile);
    if (out !== null) changed.set(file, out);
  }
  for (const ns of Object.keys(catalog)) {
    if (catalog[ns] && typeof catalog[ns] === 'object' && !Object.keys(catalog[ns]).length) delete catalog[ns];
  }
  if (apply) {
    for (const [file, out] of changed) fs.writeFileSync(file, out);
    fs.writeFileSync(enFile, `${JSON.stringify(catalog, null, 2)}\n`);
  }
  return report;
}

module.exports = { extract, cleanJSXText };

if (require.main === module) {
  const apply = process.argv.includes('--apply');
  const { samples, added, ...counts } = extract({ apply });
  console.log(JSON.stringify(counts, null, 1));
  for (const [kind, list] of Object.entries(samples)) console.log(`── ${kind}\n${list.join('\n')}`);
  if (apply) console.log(`applied: ${counts.files} files, ${counts.keys} keys in src/locales/en.json`);
}
