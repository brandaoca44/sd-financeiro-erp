import { HttpClient } from '@angular/common/http';
import { Component,effect,inject,input,signal,untracked } from '@angular/core';
import { FormBuilder,ReactiveFormsModule,Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom,timeout } from 'rxjs';
import { Workspaces } from '../../core/workspaces';
import { FinanceApi,money,dateLabel,today } from '../../core/finance';
interface Entry {id:string;source:string;reference_id:string;day:string;kind:string;description:string;amount:string;direction:'IN'|'OUT';balance:string}
interface Statement {start:string;end:string;opening_balance:string;incoming:string;outgoing:string;closing_balance:string;items:Entry[];next_cursor:string|null}
@Component({selector:'sdf-account-statement',imports:[ReactiveFormsModule,RouterLink],styles:`
 :host{display:block;margin-top:1.25rem}.statement-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:1rem}
 .statement-filter{display:flex;gap:.75rem;align-items:end;flex-wrap:wrap}.statement-filter label{display:grid;gap:.35rem;margin:0}
 .statement-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr));gap:.75rem;margin-bottom:1rem}
 .statement-summary article{padding:1rem;border:1px solid #dce5f0;border-radius:.65rem;background:linear-gradient(145deg,#fff,#f3f7fc)}
 .statement-summary span{display:block;font-size:.8125rem;color:#52657e}.statement-summary strong{display:block;margin-top:.5rem;font-size:1.25rem;color:#173762;overflow-wrap:anywhere}
 .statement-more{display:flex;justify-content:center;margin-top:1rem}.statement-reference{display:block;font-size:.75rem;color:#64748b;overflow-wrap:anywhere}
`,template:`
 <section class="account-section" aria-labelledby="statement-title"><div class="statement-heading"><h2 id="statement-title">Extrato da conta</h2>
 <form class="statement-filter" [formGroup]="form" (ngSubmit)="apply()"><label>De<input type="date" formControlName="start" [min]="openingDate()" [max]="today"></label><label>Até<input type="date" formControlName="end" [max]="today"></label><button class="secondary" type="submit" [disabled]="loading() || form.invalid">Consultar extrato</button></form></div>
 @if(error()){<p class="alert" role="alert">{{error()}}</p>}
 @if(loading()){<p role="status">Consultando lançamentos…</p>}
 @if(report();as data){
 <div class="statement-summary"><article><span>Saldo de abertura</span><strong>{{money(data.opening_balance)}}</strong></article><article><span>Entradas no período</span><strong>{{money(data.incoming)}}</strong></article><article><span>Saídas no período</span><strong>{{money(data.outgoing)}}</strong></article><article><span>Saldo de fechamento</span><strong>{{money(data.closing_balance)}}</strong></article></div>
 <p class="muted">Período de {{date(data.start)}} a {{date(data.end)}}. Saldos e totais consideram todos os lançamentos do período, independentemente da página.</p>
 @if(!data.items.length){<p class="muted">Nenhum lançamento encontrado neste período.</p>}@else{
 <div class="table-scroll"><table><thead><tr><th>Data</th><th>Operação</th><th>Descrição e referência</th><th class="numeric">Entrada</th><th class="numeric">Saída</th><th class="numeric">Saldo após lançamento</th></tr></thead><tbody>
 @for(row of data.items;track row.source+row.id+row.reference_id){<tr><td>{{date(row.day)}}</td><td>{{label(row.kind)}}</td><td>{{row.description}}<small class="statement-reference">{{row.reference_id}}</small>
 @if(row.source==='PAYABLE'){<a routerLink="/finance/payables" [queryParams]="{title:row.reference_id}">Ver título</a>}</td><td class="numeric">{{row.direction==='IN'?money(row.amount):'—'}}</td><td class="numeric">{{row.direction==='OUT'?money(row.amount):'—'}}</td><td class="numeric">{{money(row.balance)}}</td></tr>}
 </tbody></table></div>}
 @if(data.next_cursor){<div class="statement-more"><button class="secondary small" type="button" (click)="more()" [disabled]="loading()">Carregar mais lançamentos</button></div>}
 }
 <p class="muted">Extrato gerencial dos movimentos vinculados ao ERP, ainda sem conciliação bancária. Estornos aparecem na data financeira registrada. Movimentos sem conta não são incluídos.</p>
 </section>
`})
export class AccountStatementPanel {
 readonly accountId=input.required<string>();readonly openingDate=input.required<string>();private http=inject(HttpClient);private workspaces=inject(Workspaces);private api=inject(FinanceApi);private generation=0;
 readonly form=inject(FormBuilder).nonNullable.group({start:['',Validators.required],end:[today(),Validators.required]});readonly today=today();readonly money=money;readonly date=dateLabel;
 readonly report=signal<Statement|null>(null);readonly loading=signal(false);readonly error=signal('');private range=signal({start:'',end:''});private refresh=signal(0);
 constructor(){effect(()=>{const id=this.accountId(),opening=this.openingDate();this.workspaces.selected();untracked(()=>{const start=opening>today().slice(0,7)+'-01'?opening:today().slice(0,7)+'-01';this.form.setValue({start,end:today()});this.range.set({start,end:today()});});});
 effect(()=>{this.accountId();this.workspaces.selected();this.range();this.refresh();this.api.revision();untracked(()=>{this.generation++;this.report.set(null);this.error.set('');this.loading.set(false);void this.load(false);});});}
 label(kind:string){return ({PAYMENT:'Pagamento',REVERSAL:'Estorno de pagamento',RECEIVED:'Recebimento',RECEIPT_REVERSAL:'Estorno de recebimento'} as Record<string,string>)[kind]??kind;}
 apply(){const value=this.form.getRawValue(),days=(Date.parse(value.end)-Date.parse(value.start))/86400000;
 if(this.form.invalid||!Number.isFinite(days)||days<0||days>92||value.start<this.openingDate()||value.end>today()){this.error.set('Selecione até 93 dias, a partir da data inicial e sem datas futuras.');return;}
 this.range.set(value);this.refresh.update(value=>value+1);}
 async more(){if(!this.loading()&&this.report()?.next_cursor)await this.load(true);}
 private async load(more:boolean){const company=this.workspaces.selected(),id=this.accountId(),generation=this.generation,range=this.range();
 if(!company||!range.start||!this.workspaces.can('accounts.read')||!this.workspaces.can('payables.read')||!this.workspaces.can('billing.read'))return;
 const params:Record<string,string>={...range,limit:'50'};if(more&&this.report()?.next_cursor)params['cursor']=this.report()!.next_cursor!;
 this.loading.set(true);try{const page=await firstValueFrom(this.http.get<Statement>(this.api.base(company).replace(/payables$/,'financial-accounts')+'/'+id+'/statement',{params}).pipe(timeout(15000)));
 if(generation===this.generation){this.report.set({...page,items:more?[...(this.report()?.items??[]),...page.items]:page.items});}}
 catch{if(generation===this.generation){this.report.set(null);this.error.set('Não foi possível consultar o extrato. Confira o período e suas permissões.');}}
 finally{if(generation===this.generation)this.loading.set(false);}}
}
