const {chromium}=require('/mnt/c/Users/Jin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/home/jin/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome',args:['--no-sandbox','--disable-background-networking'],env:{...process.env,LD_LIBRARY_PATH:'/tmp/comparison-browser-libs/usr/lib/x86_64-linux-gnu'}});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('file://'+path.join(__dirname,'SAMPLE/index.html'));
  if(await page.locator('#shown').innerText()!=='11행 표시')throw Error('initial count');
  await page.locator('#q').fill('신상품');if(await page.locator('tr.hit:visible').count()!==1)throw Error('term filter');
  await page.addStyleTag({content:"@font-face{font-family:KoreanPreview;src:url('file:///mnt/c/Windows/Fonts/malgun.ttf')}body{font-family:KoreanPreview,sans-serif}"});await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:path.join(__dirname,'PREVIEW.png')});
  await page.locator('#q').fill('');await page.locator('#status').selectOption('BROKEN');if(await page.locator('tr.hit:visible').count()!==4)throw Error('status filter');
  await page.locator('#status').selectOption('NEARBY_REFERENCE');await page.locator('tr.hit:visible a').first().click();
  if(!(await page.locator('body').innerText()).includes('제20조 대상 원문'))throw Error('target source not rendered');
  if(errors.length)throw Error(errors.join('\n'));
  fs.writeFileSync(path.join(__dirname,'BROWSER_VALIDATION.json'),JSON.stringify({status:'PASS',checks:['all 11 rows','신상품 search 1 row','BROKEN filter 4 rows','target raw text link','no script errors'],scope:'local synthetic HTML only'},null,2));
  console.log('PASS: local HTML search, status filter, target link and rendering');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
