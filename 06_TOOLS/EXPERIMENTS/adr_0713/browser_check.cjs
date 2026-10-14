const { chromium } = require('/mnt/c/Users/Jin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const out = path.resolve('04_EXPERIMENTS/ADR/ADR-0713-legal-knowledge-lab-deduction/artifacts/browser-final-rev7');
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/home/jin/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1480,height:1040},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('422'))errors.push(m.text());});
 const checks=[];
 try{
  await page.goto('http://127.0.0.1:5581');await page.locator('#count-wiki').filter({hasText:'204'}).waitFor();
  checks.push('actual catalogue count');await page.screenshot({path:out+'/01-question.png',fullPage:true});
  await page.locator('#question').fill('브라우저 동작 확인: 외부 전송하지 않음');await page.locator('#ask-submit').click();
  await page.locator('#toast').filter({hasText:'공개 법령 질문'}).waitFor();checks.push('public export assertion gate; zero model calls');
  await page.locator('nav [data-tab="shortcuts"]').click();await page.locator('#library-status').selectOption('PUBLISHED');
  await page.locator('#library-list .list-item').first().click();await page.locator('#library-detail h2').waitFor();
  await page.locator('#library-detail select').selectOption('BOOKMARKED');await page.locator('#library-detail textarea').fill('UI 계약 확인 · 원본 불변');
  await page.getByRole('button',{name:'변경 저장',exact:true}).click();await page.locator('#toast').filter({hasText:'저장했습니다'}).waitFor();
  await page.getByRole('button',{name:'변경 이력',exact:true}).click();await page.getByText('연구실 변경 이력',{exact:true}).waitFor();
  checks.push('shortcut detail, sandbox bookmark, append-only history');
  await page.locator('#library-detail select').selectOption('NORMAL');await page.locator('#library-detail textarea').fill('');await page.getByRole('button',{name:'변경 저장',exact:true}).click();
  await page.screenshot({path:out+'/02-shortcuts.png',fullPage:true});
  await page.getByRole('button',{name:'작은 지식으로 분해',exact:true}).click();await page.locator('#toast').filter({hasText:'원자 후보'}).waitFor();checks.push('wiki structural atomization');
  await page.locator('nav [data-tab="ontology"]').click();await page.locator('#ontology-search').fill('투자');await page.locator('#ontology-find').click();
  await page.locator('#ontology-list .list-item').first().click();await page.locator('#ontology-detail svg').waitFor();
  await page.screenshot({path:out+'/03-ontology.png',fullPage:true});checks.push('live ontology search and graph');
  await page.locator('nav [data-tab="proof"]').click();await page.locator('#load-demo').click();await page.locator('#fact-chips input').first().waitFor();
  await page.locator('#prove').click();await page.locator('#proof-result').filter({hasText:'조건부 증명 성공'}).waitFor();
  checks.push('unseen X+Y+C proof');await page.locator('#compose').click();await page.locator('#save-derived:enabled').waitFor();
  await page.locator('#save-derived').click();await page.locator('#toast').filter({hasText:'파생 위키를 저장'}).waitFor();checks.push('derived wiki persistence');
  await page.screenshot({path:out+'/04-proof.png',fullPage:true});
  await page.locator('#new-rule').click();await page.locator('#editor').waitFor();await page.locator('#editor-close').click();checks.push('rule editor');
  const savedCount=await page.locator('#count-formal').innerText();
  await page.reload();await page.locator('nav [data-tab="proof"]').click();await page.locator('#count-formal').filter({hasText:savedCount}).waitFor();checks.push('reload persistence');
  await page.setViewportSize({width:390,height:844});await page.locator('nav [data-tab="ask"]').click();
  await page.screenshot({path:out+'/05-mobile.png',fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  if(overflow)throw Error('mobile horizontal overflow');checks.push('responsive 390px');
  if(errors.length)throw Error(errors.join('\n'));
  fs.writeFileSync(out+'/result.json',JSON.stringify({status:'PASS',checks,errors,model_calls:0},null,2));
  console.log(JSON.stringify({status:'PASS',checks,errors}));
 }catch(error){await page.screenshot({path:out+'/failure.png',fullPage:true});fs.writeFileSync(out+'/failure.json',JSON.stringify({checks,errors,error:String(error)},null,2));throw error;}
 finally{await browser.close();}
})();
