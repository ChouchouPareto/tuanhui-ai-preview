import test from 'node:test';
import assert from 'node:assert/strict';
import {adminConfigured,validAdmin,adminUpstream,sameOriginMutation} from '../lib/admin-access.ts';
const env={TUANHUI_ADMIN_ENABLED:'1',ADMIN_API_TOKEN:'test-only-admin-token-with-32-characters'};
const basic=value=>'Basic '+Buffer.from(value).toString('base64');
test('admin disabled unless explicitly enabled with a strong token',()=>{
 assert.equal(adminConfigured({}),false);
 assert.equal(adminConfigured({...env,TUANHUI_ADMIN_ENABLED:'0'}),false);
 assert.equal(adminConfigured({...env,ADMIN_API_TOKEN:'short'}),false);
 assert.equal(validAdmin(basic(`admin:${env.ADMIN_API_TOKEN}`),env),true);
 for(const input of [null,'Bearer anything','Basic ???',basic('admin:wrong'),basic(`merchant:${env.ADMIN_API_TOKEN}`)])assert.equal(validAdmin(input,env),false);
});
test('management gateway cannot proxy arbitrary or paid endpoints',()=>{
 assert.equal(adminUpstream('contracts','GET'),'/agent/contracts');
 assert.equal(adminUpstream('templates','GET'),'/templates/reviews');
 assert.equal(adminUpstream('templates/L01/review','POST'),'/templates/L01/review');
 for(const path of ['../projects','projects/x/agent-runs','templates/L01/review/../../projects','https://example.com','templates/L01/review?x=1'])assert.equal(adminUpstream(path,'POST'),null);
 assert.equal(adminUpstream('contracts','POST'),null);
 assert.equal(adminUpstream('templates/L01/review','DELETE'),null);
});
test('mutations require exact same origin, not a sibling or absent origin',()=>{
 const req=origin=>new Request('http://localhost:3021/api/internal/templates/L01/review',{headers:origin?{Origin:origin}:{}});
 assert.equal(sameOriginMutation(req('http://localhost:3021')),true);
 assert.equal(sameOriginMutation(req('http://localhost:3011')),false);
 assert.equal(sameOriginMutation(req('https://evil.example')),false);
 assert.equal(sameOriginMutation(req(null)),false);
});
