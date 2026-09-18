// Usage: NODE_PATH=<playwright package root> node this.cjs <demo-folder> <chromium-path>
// The demo is explicitly synthetic. No web server or external requests are used.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
(async () => {
  const root = path.resolve(process.argv[2]);
  const browser = await chromium.launch({headless: true, executablePath: process.argv[3], args:['--no-sandbox']});
  try {
    const page = await browser.newPage({acceptDownloads:true,viewport:{width:1280,height:900}});
    const errors=[],external=[];
    page.on('pageerror', e=>errors.push(e.message));
    page.on('request', r=>{if(/^https?:/.test(r.url()))external.push(r.url())});
    async function save(selector, filename) {
      const waiting=page.waitForEvent('download');await page.click(selector);
      const download=await waiting;await download.saveAs(path.join(root,filename));
      return JSON.parse(await fs.readFile(path.join(root,filename),'utf8'));
    }
    await page.goto(pathToFileURL(path.join(root,'authoring/review.html')).href);
    await page.fill('#reviewer','브라우저 모의 검토자');
    await page.check('#checked');await page.click('#approve');
    assert.match(await page.textContent('#message'),/승인 완료/);
    await save('#save','author-work.json');
    const draft=await save('#download','browser-reviewed.json');
    assert.equal(draft.cases[0].review.status,'approved');
    await page.fill('#question','수정한 모의 질문');
    const changed=await save('#download','browser-unapproved.json');
    assert.equal(changed.cases[0].review.status,'draft');
    await page.setInputFiles('#restore',path.join(root,'author-work.json'));
    await page.waitForFunction(()=>document.getElementById('summary').textContent.includes('승인 1문항'));
    assert.match(await page.textContent('#summary'),/승인 1문항/);

    await page.goto(pathToFileURL(path.join(root,'answers/answer-review.html')).href);
    assert.match(await page.textContent('#editor'),/모의 답변/);
    await page.click('#complete');
    assert.match(await page.textContent('#message'),/모든 항목/);
    await page.fill('#reviewer','브라우저 모의 채점자');
    for (const select of await page.locator('[data-judge]').all()) await select.selectOption('true');
    await page.click('#complete');
    await save('#save','answer-work.json');
    const review=await save('#export','browser-answers-reviewed.json');
    assert.ok(review.reviews[0].by);
    await page.selectOption('[data-judge="citations_supported"]','false');
    const pending=await save('#export','browser-answers-pending.json');
    assert.equal(pending.reviews[0].by,'');
    await page.setInputFiles('#restore',path.join(root,'answer-work.json'));
    await page.waitForFunction(()=>document.getElementById('summary').textContent.includes('채점 완료 1문항'));
    assert.match(await page.textContent('#summary'),/채점 완료 1문항/);
    const wrong=JSON.parse(await fs.readFile(path.join(root,'answer-work.json'),'utf8'));
    wrong.review.run_binding='other-run';
    await fs.writeFile(path.join(root,'wrong-work.json'),JSON.stringify(wrong));
    await page.setInputFiles('#restore',path.join(root,'wrong-work.json'));
    await page.waitForFunction(()=>document.getElementById('message').textContent.includes('다른 골든 또는 평가'));
    assert.match(await page.textContent('#message'),/다른 골든 또는 평가/);
    await page.screenshot({path:path.join(root,'answer-review-preview.png'),fullPage:true});
    assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
    console.log(JSON.stringify({passed:true,pageErrors:errors.length,externalRequests:external.length}));
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
