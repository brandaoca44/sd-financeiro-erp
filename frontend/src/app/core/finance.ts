import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom, timeout } from 'rxjs';
import { Workspace } from './workspaces';

export interface Title {id:string; description:string; amount:string; issue_date:string; due_date:string; status:'OPEN'|'CANCELLED'; revision:number}
export interface Movement {id:string; payable_id:string; kind:'PAYMENT'|'REVERSAL'; amount:string; occurred_on:string; reverses_id:string|null; reversal_reason:string|null}
export interface Page<T>{items:T[];next_cursor:string|null}
export interface Day {day:string;outstanding_due_amount:string;payments_amount:string;reversals_amount:string;net_paid_amount:string}
export interface Summary {as_of:string;upcoming_days:number;current:{outstanding_amount:string;overdue_amount:string;due_today_amount:string;upcoming_amount:string;paid_amount:string;active_title_count:number};period:{payments_amount:string;reversals_amount:string;net_paid_amount:string};days:Day[]}
export interface Receipt {id:string;revision:number;status:string}
export interface Position {revision:number;paid_amount:string;outstanding_amount:string;settlement_status:string}
@Injectable({providedIn:'root'})
export class FinanceApi {
  private http=inject(HttpClient); readonly revision=signal(0);
  base(workspace:Workspace):string {return `/api/v1/organizations/${encodeURIComponent(workspace.organization_id)}/companies/${encodeURIComponent(workspace.company_id)}/payables`;}
  summary(workspace:Workspace,start:string,end:string):Promise<Summary> {return firstValueFrom(this.http.get<Summary>(this.base(workspace)+'/summary',{params:{period_start:start,period_end:end}}).pipe(timeout(15000)));}
  titles(workspace:Workspace,cursor:string|null,status:string):Promise<Page<Title>> {const params:Record<string,string>={limit:'20'};if(cursor)params['cursor']=cursor;if(status)params['status']=status;return firstValueFrom(this.http.get<Page<Title>>(this.base(workspace),{params}).pipe(timeout(15000)));}
  movements(workspace:Workspace,id:string,cursor:string|null=null):Promise<Page<Movement>> {const params:Record<string,string>={limit:'100'};if(cursor)params['cursor']=cursor;return firstValueFrom(this.http.get<Page<Movement>>(this.base(workspace)+`/${encodeURIComponent(id)}/movements`,{params}).pipe(timeout(15000)));}
  position(workspace:Workspace,id:string):Promise<Position>{return firstValueFrom(this.http.get<Position>(this.base(workspace)+`/${encodeURIComponent(id)}/position`).pipe(timeout(15000)));}
  title(workspace:Workspace,id:string):Promise<Title>{return firstValueFrom(this.http.get<Title>(this.base(workspace)+`/${encodeURIComponent(id)}`).pipe(timeout(15000)));}
  write(workspace:Workspace,path:string,body:unknown,method:'POST'|'PUT'='POST',key?:string):Promise<unknown> {
    const headers:Record<string,string>={};if(key)headers['Idempotency-Key']=key;
    return firstValueFrom(this.http.request(method,this.base(workspace)+path,{body,headers}).pipe(timeout(15000)));
  }
}
export function money(value:string):string {
  if(typeof value!=='string' || !/^-?\d+(\.\d{1,2})?$/.test(value))return '—';
  const negative=value.startsWith('-'), unsigned=negative?value.slice(1):value;
  const [integer,fraction='']=unsigned.split('.');
  return `${negative?'− ':''}R$ ${integer.replace(/\B(?=(\d{3})+(?!\d))/g,'.')},${fraction.padEnd(2,'0')}`;
}
export function dateLabel(value:string):string {return /^\d{4}-\d{2}-\d{2}$/.test(value)?`${value.slice(8,10)}/${value.slice(5,7)}/${value.slice(0,4)}`:'—';}
export function today():string {return new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
