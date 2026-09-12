import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_PATH || 'playwright');
const api='http://127.0.0.1:8011/api/v1';
const projects=await fetch(`${api}/projects`).then(r=>r.json());
const project=projects.find(p=>p.cover);
assert(project,'A saved result is required for read-only reentry validation');
const workspace=await fetch(`${api}/projects/${project.id}/workspace`).then(r=>r.json());
const task=workspace.tasks.find(t=>t.result?.long_image);
const detail=await fetch(`${api}/tasks/${task.id}`).then(r=>r.json());
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage({viewport:{width:1440,height:960}});
 await page.route('**/api/v1/**',route=>route.request().method()==='GET' ? route.continue() : route.abort());
 for(const query of [`project=${project.id}&task=${task.id}`,`project=${project.id}&creation=${detail.creation_id}`,`project=${project.id}`]) {
  await page.goto(`http://127.0.0.1:3011/?${query}`);
  const result=page.getByAltText('完整五连图',{exact:true});
  await result.waitFor({state:'visible',timeout:15000});
  await result.evaluate(img=>img.decode());
  assert(await result.evaluate(img=>img.naturalWidth>0));
  await page.reload(); await result.waitFor({state:'visible'});
 }
 await page.getByRole('link',{name:'返回项目',exact:true}).click();
 await page.locator('.projectCard').first().waitFor();
 await page.locator('.projectCard').first().click();
 await page.getByAltText('完整五连图',{exact:true}).waitFor();

 let downloads=0; page.on('download',()=>downloads++);
 await page.getByRole('button',{name:'预览完整五连图',exact:true}).click();
 const preview=page.getByRole('dialog',{name:'作品预览'});
 await preview.waitFor({state:'visible'});
 await preview.getByAltText('完整五连图预览').evaluate(img=>img.decode());
 await preview.getByRole('button',{name:'下一张'}).click();
 assert(await preview.getByAltText('第 1 张切片预览').isVisible());
 await preview.getByRole('button',{name:'放大查看'}).click();
 assert(await preview.locator('.isZoomed').count()===1);
 await page.screenshot({path:'/tmp/tuanhui-result-preview.png'});
 await page.keyboard.press('Escape');
 await preview.waitFor({state:'hidden'});
 assert.equal(downloads,0,'Preview must not download');
 await page.setViewportSize({width:375,height:812});
 await page.getByRole('button',{name:'预览完整五连图',exact:true}).click();
 await page.screenshot({path:'/tmp/tuanhui-result-preview-mobile.png'});
 assert(await preview.evaluate(el=>el.getBoundingClientRect().right<=innerWidth));
 await preview.getByRole('button',{name:'关闭预览'}).click();
 await page.setViewportSize({width:1440,height:960});
 const downloading=page.waitForEvent('download');
 await page.getByRole('link',{name:'下载完整五连图',exact:true}).click();
 const download=await downloading; assert.equal(download.suggestedFilename(),'tuanhui-long.png');
 await page.screenshot({path:'/tmp/tuanhui-restored-result.png'});
 await page.goto('http://127.0.0.1:3011/projects');
 await page.locator('.projectMenu summary').first().click();
 for(const name of ['编辑','复制','隐藏','删除']) assert(await page.getByRole('button',{name,exact:true}).isVisible());
 await page.screenshot({path:'/tmp/tuanhui-project-menu.png'});
 console.log('PASS real saved result: task / creation / project / refresh / return-project / reopen; project menu');
} finally {await browser.close();}
