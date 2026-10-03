const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Run only the pure result-rendering functions; no browser or network is involved.
const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');
const helpers = source.slice(source.indexOf('function renderDocumentBlocks('), source.indexOf('async function documentPage('));
const escaping = source.split('\n').find(line => line.startsWith('const esc = '));
const block = (id, text, type = 'paragraph') => ({id, text, type});
function render(doc, mode = 'changes') {
  return vm.runInNewContext(`${escaping}\nlet compareMode = mode;\n${helpers}\n({html: displayBlocks(doc), statistic: revisionStatistic(doc)});`, {doc, mode});
}

test('recomposed changes show both full documents, even with more new paragraphs', () => {
  const doc = {
    original: [block('old', 'Original <script>source</script>')],
    revised: [block('new-title', 'A new title', 'heading'), block('new-1', 'First new paragraph'), block('new-2', 'Last new paragraph')],
    report: {structure_recomposed: true, revised_paragraphs: 2, changed_blocks: null},
  };
  const {html, statistic} = render(doc);
  assert.match(html, /Before · Original document/);
  assert.match(html, /After · Refined document/);
  assert.match(html, /Original &lt;script&gt;source&lt;\/script&gt;/);
  assert.match(html, /<h3 dir="auto">A new title<\/h3>/);
  assert.match(html, /First new paragraph/);
  assert.match(html, /Last new paragraph/);
  assert.doesNotMatch(html, /<script>|<del|<ins/);
  assert.match(statistic, /Refined paragraphs/);
  assert.match(statistic, /<strong>2<\/strong>/);
});

test('recomposed documents with the same paragraph count still avoid positional diff', () => {
  const doc = {
    original: [block('old-1', 'First thought'), block('old-2', 'Second thought')],
    revised: [block('new-1', 'Second thought, expanded'), block('new-2', 'First thought, moved')],
    report: {structure_recomposed: true},
  };
  const {html, statistic} = render(doc);
  assert.match(html, /Paragraphs were reorganized/);
  assert.doesNotMatch(html, /<del|<ins/);
  assert.match(statistic, /<strong>2<\/strong>/);
  assert.doesNotMatch(render(doc, 'original').html, /Second thought, expanded/);
  assert.doesNotMatch(render(doc, 'revised').html, /Before · Original document/);
});

test('the entire 12000-word source and output remain visible', () => {
  const original = Array.from({length: 120}, (_, i) => block(`old-${i}`, Array(100).fill(`source-${i}`).join(' ')));
  const revised = Array.from({length: 150}, (_, i) => block(`new-${i}`, Array(80).fill(`output-${i}`).join(' ')));
  const {html, statistic} = render({original, revised, report: {structure_recomposed: true}});
  for (const item of [...original, ...revised]) assert.ok(html.includes(item.text));
  assert.equal((html.match(/<p dir="auto">/g) || []).length, 270);
  assert.match(statistic, /<strong>150<\/strong>/);
});

test('legacy documents retain positional highlighting and passages-edited label', () => {
  const doc = {
    original: [block('same', 'Unchanged'), block('edit', 'Before')],
    revised: [block('same', 'Unchanged'), block('edit', 'After')],
    report: {changed_blocks: 1},
  };
  const {html, statistic} = render(doc);
  assert.match(html, /<p dir="auto">Unchanged<\/p>/);
  assert.match(html, /<del class="diff-del">Before<\/del>/);
  assert.match(html, /<ins class="diff-add">After<\/ins>/);
  assert.match(statistic, /Passages edited/);
  assert.match(statistic, /<strong>1<\/strong>/);
});
