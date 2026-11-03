// Prévia visual opt-in: fixtures sintéticas, sem proxy ou conexão ao ERP.
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { dirname, extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../dist/sd-financeiro/browser');
const organization='00000000-0000-4000-8000-000000000001',company='00000000-0000-4000-8000-000000000002';
const titles=[{id:'00000000-0000-4000-8000-000000000003',description:'Serviços de infraestrutura · demonstração',amount:'1800.00',issue_date:'2026-11-01',due_date:'2026-11-10',status:'OPEN',revision:1},{id:'00000000-0000-4000-8000-000000000004',description:'Licenças de software · demonstração',amount:'420.00',issue_date:'2026-11-01',due_date:'2026-11-05',status:'OPEN',revision:1}];
const third='00000000-0000-4000-8000-000000000008';
titles.push({id:third,description:'Manutenção · demonstração',amount:'3300.00',issue_date:'2026-11-01',due_date:'2026-11-30',status:'OPEN',revision:4});
const demoMovements=[{id:'00000000-0000-4000-8000-000000000005',payable_id:third,kind:'PAYMENT',amount:'300.00',occurred_on:'2026-11-01',reverses_id:null,reversal_reason:null},{id:'00000000-0000-4000-8000-000000000006',payable_id:third,kind:'PAYMENT',amount:'700.00',occurred_on:'2026-11-01',reverses_id:null,reversal_reason:null},{id:'00000000-0000-4000-8000-000000000007',payable_id:third,kind:'REVERSAL',amount:'300.00',occurred_on:'2026-11-02',reverses_id:'00000000-0000-4000-8000-000000000005',reversal_reason:'Correção demonstrativa'}];
const json=(res,status,data)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(data===null?'':JSON.stringify(data));};
createServer(async(req,res)=>{try{
  const url=new URL(req.url,'http://127.0.0.1:4201');res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','no-referrer');
  if(url.pathname.startsWith('/api/v1/')){
    if(url.pathname.endsWith('/auth/login') && req.method==='POST'){
      let body='';for await(const part of req){body+=part;if(body.length>4096){json(res,413,{});return;}}
      const data=JSON.parse(body);json(res,data.email==='qa@example.invalid' && data.password==='somente-qa'?200:401,{access_token:'qa-token-sem-validade-no-erp'});return;
    }
    if(req.headers.authorization!=='Bearer qa-token-sem-validade-no-erp'){json(res,401,{});return;}
    if(url.pathname.endsWith('/auth/logout')){json(res,204,null);return;}
    if(req.method!=='GET'){json(res,503,{detail:'Prévia visual sem escrita.'});return;}
    if(url.pathname.endsWith('/auth/workspaces')){json(res,200,{items:[{organization_id:organization,company_id:company,company_name:'Empresa demonstrativa · dados fictícios',permissions:['payables.read','payables.manage','payables.settle','payables.reverse']}],next_cursor:null});return;}
    if(url.pathname.endsWith('/summary')){
      const start=url.searchParams.get('period_start'),end=url.searchParams.get('period_end'),days=[];
      for(let day=new Date(`${start}T12:00:00Z`),index=0;day<=new Date(`${end}T12:00:00Z`) && index<366;day.setUTCDate(day.getUTCDate()+1),index++){
        const key=day.toISOString().slice(0,10),due=titles.filter(title=>title.due_date===key),payments=key==='2026-11-01'?1000:0,reversals=key==='2026-11-02'?300:0;
        days.push({day:key,original_due_amount:due.reduce((sum,title)=>sum+Number(title.amount),0).toFixed(2),outstanding_due_amount:due.reduce((sum,title)=>sum+Number(title.amount)-(title.id===third?700:0),0).toFixed(2),payments_amount:payments.toFixed(2),reversals_amount:reversals.toFixed(2),net_paid_amount:(payments-reversals).toFixed(2)});
      }
      const total=name=>days.reduce((sum,day)=>sum+Number(day[name]),0).toFixed(2);
      json(res,200,{as_of:'2026-11-02',balance_basis:'CURRENT',currency:'BRL',upcoming_days:7,current:{outstanding_amount:'4820.00',original_amount:'5520.00',overdue_amount:'0.00',due_today_amount:'0.00',upcoming_amount:'420.00',later_amount:'4400.00',paid_amount:'700.00',active_title_count:3,cancelled_title_count:0,unpaid_title_count:2,partial_title_count:1,paid_title_count:0},period:{original_due_amount:total('original_due_amount'),outstanding_due_amount:total('outstanding_due_amount'),overdue_due_amount:'0.00',payments_amount:total('payments_amount'),reversals_amount:total('reversals_amount'),net_paid_amount:total('net_paid_amount')},days});return;
    }
    if(url.pathname.endsWith('/movements')){json(res,200,{items:url.pathname.includes(third)?demoMovements:[],next_cursor:null});return;}
    if(url.pathname.endsWith('/position')){const title=titles.find(item=>url.pathname.includes(item.id));json(res,200,{revision:title.revision,paid_amount:title.id===third?'700.00':'0.00',outstanding_amount:(Number(title.amount)-(title.id===third?700:0)).toFixed(2),settlement_status:title.id===third?'PARTIALLY_PAID':'OPEN'});return;}
    const item=titles.find(title=>url.pathname.endsWith('/'+title.id));json(res,200,item || {items:titles,next_cursor:null});return;
  }
  const file=resolve(root,'.'+decodeURIComponent(url.pathname));if(!file.startsWith(root+sep) && file!==root){res.writeHead(403);res.end();return;}
  let target=file;try{if(!(await stat(target)).isFile())target=resolve(root,'index.html');}catch{target=resolve(root,'index.html');}
  const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'};res.setHeader('Content-Type',types[extname(target)] || 'application/octet-stream');res.end(await readFile(target));
}catch{json(res,500,{detail:'Prévia visual indisponível.'});}}).listen(4201,'127.0.0.1',()=>process.stdout.write('QA local com dados fictícios: http://127.0.0.1:4201 · use somente qa@example.invalid / somente-qa\n'));
