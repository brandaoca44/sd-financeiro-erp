import { Component,effect,forwardRef,inject,signal,untracked } from '@angular/core';
import { NG_VALUE_ACCESSOR,ControlValueAccessor } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { timeout } from 'rxjs';
import { Workspaces } from './workspaces';
import { FinanceApi } from './finance';
@Component({selector:'sdf-account-picker',providers:[{provide:NG_VALUE_ACCESSOR,useExisting:forwardRef(()=>AccountPicker),multi:true}],styles:`:host{display:block}label{display:grid;gap:.35rem}select{width:100%}.picker-more{margin-top:.4rem}`,template:`
  <label>Conta financeira<select [value]="value()" (change)="choose($event)" (blur)="touch()" [disabled]="disabled() || loading() || !workspaces.can('accounts.read')">
    <option value="">Sem vínculo com conta</option>@for(row of rows();track row.id){<option [value]="row.id">{{row.name}}</option>}
  </select></label>
  @if(cursor()){<button class="secondary small picker-more" type="button" (click)="more()" [disabled]="loading() || disabled()">Carregar mais contas</button>}
  @if(error()){<p class="field-help" role="status">Não foi possível consultar as contas. Atualize a empresa.</p>}
  @if(!workspaces.can('accounts.read')){<p class="field-help">A consulta de contas financeiras exige permissão própria.</p>}
`})
export class AccountPicker implements ControlValueAccessor {
  readonly workspaces=inject(Workspaces);private api=inject(FinanceApi);private http=inject(HttpClient);private generation=0;private lastCompany:string|null=null;
  readonly rows=signal<{id:string;name:string}[]>([]);readonly cursor=signal<string|null>(null);readonly loading=signal(false);readonly error=signal(false);readonly value=signal('');readonly disabled=signal(false);
  private change:(value:string)=>void=()=>{};touch:()=>void=()=>{};
  constructor(){effect(onCleanup=>{const company=this.workspaces.selected(),allowed=this.workspaces.can('accounts.read');const scope=company?company.organization_id+'/'+company.company_id:null;if(this.lastCompany!==null&&scope!==this.lastCompany){this.value.set('');untracked(()=>this.change(''));}this.lastCompany=scope;this.generation++;this.rows.set([]);this.cursor.set(null);this.error.set(false);this.loading.set(false);
    if(!company||!allowed){this.value.set('');untracked(()=>this.change(''));return;}this.loading.set(true);
    const sub=this.http.get<{items:{id:string;name:string}[];next_cursor:string|null}>(this.api.base(company).replace(/payables$/,'financial-accounts'),{params:{status:'ACTIVE',limit:'100'}}).pipe(timeout(15000)).subscribe({next:page=>{this.rows.set(page.items);this.cursor.set(page.next_cursor);this.loading.set(false);},error:()=>{this.error.set(true);this.loading.set(false);}});onCleanup(()=>sub.unsubscribe());});}
  writeValue(value:string|null){this.value.set(value??'');}registerOnChange(fn:(value:string)=>void){this.change=fn;}registerOnTouched(fn:()=>void){this.touch=fn;}setDisabledState(value:boolean){this.disabled.set(value);}
  choose(event:Event){const value=(event.target as HTMLSelectElement).value;this.value.set(value);this.change(value);}
  more(){const company=this.workspaces.selected(),cursor=this.cursor(),generation=this.generation;if(!company||!cursor)return;this.loading.set(true);
    this.http.get<{items:{id:string;name:string}[];next_cursor:string|null}>(this.api.base(company).replace(/payables$/,'financial-accounts'),{params:{status:'ACTIVE',limit:'100',cursor}}).pipe(timeout(15000)).subscribe({next:page=>{if(generation===this.generation){this.rows.update(rows=>[...rows,...page.items]);this.cursor.set(page.next_cursor);this.loading.set(false);}},error:()=>{if(generation===this.generation){this.error.set(true);this.loading.set(false);}}});}
}
