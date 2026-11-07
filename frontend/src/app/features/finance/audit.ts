import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { Workspaces } from '../../core/workspaces';

interface EventRow {id:string;source:string;domain:string;resource_type:string;resource_id:string;
  actor_user_id:string;actor_name:string;action:string;created_at:string}
interface Page {items:EventRow[];next_cursor:string|null}
const utcDay=()=>new Date().toISOString().slice(0,10);
const defaultStart=()=>new Date(Date.now()-29*86400000).toISOString().slice(0,10);
@Component({selector:'sdf-audit',imports:[ReactiveFormsModule],styles:`
  .audit-filters {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,10rem),1fr));gap:1rem;align-items:end}
  .audit-filters label {display:grid;gap:.4rem;min-width:0;margin:0}
  .audit-filters input,.audit-filters select {width:100%;min-width:0}
  .audit-filters button {min-height:44px}
  .audit-list {margin-top:1rem}
  .audit-list td {vertical-align:top;line-height:1.5}
  .event-label {display:block;font-weight:600;color:#18385d}
  .event-id {display:block;color:#64748b;font-size:.75rem;overflow-wrap:anywhere;max-width:21rem}
  .audit-pagination {display:flex;justify-content:center;margin-top:1rem}
`,template:`
  <div class="page-heading"><div><span class="eyebrow">GOVERNANÇA</span><h1>Histórico de operações</h1>
    <p class="muted">Acompanhe quem realizou cada operação na empresa selecionada.</p></div></div>
  @if (!workspaces.selected()?.can_manage_access) {
    <p class="panel">A consulta de auditoria está disponível ao Master da organização.</p>
  } @else {
    <form class="panel audit-filters" [formGroup]="form" (ngSubmit)="refresh()">
      <label>De (UTC)<input type="date" formControlName="start"></label>
      <label>Até (UTC)<input type="date" formControlName="end"></label>
      <label>Área<select formControlName="domain"><option value="">Todas</option>
        @for (entry of domains;track entry.key){<option [value]="entry.key">{{entry.label}}</option>}
      </select></label>
      <label>Operação<select formControlName="action"><option value="">Todas</option>
        @for (entry of actions;track entry.key){<option [value]="entry.key">{{entry.label}}</option>}
      </select></label>
      <button class="primary" type="submit" [disabled]="loading() || form.invalid">Consultar histórico</button>
    </form>
    @if(error()){<p class="alert" role="alert">{{error()}}</p>}
    <section class="panel register-list audit-list">
      <div class="panel-heading"><h2>Operações registradas</h2><span class="muted">{{items().length}} registros carregados</span></div>
      <p class="muted">Somente metadados. Documentos, salários e dados bancários não aparecem aqui. As datas dos filtros usam UTC; os horários abaixo seguem seu navegador.</p>
      @if(loading()){<p role="status">Consultando histórico…</p>}
      @if(!loading() && !error() && !items().length){<p class="muted">Nenhuma operação encontrada neste período.</p>}
      @if(items().length){
        <div class="table-scroll"><table><thead><tr><th>Data e hora</th><th>Responsável</th><th>Área</th><th>Operação</th><th>Registro</th></tr></thead>
          <tbody>@for(row of items();track row.source+row.id){
            <tr><td>{{dateLabel(row.created_at)}}</td><td><span class="event-label">{{row.actor_name}}</span><small class="event-id">{{row.actor_user_id}}</small></td>
              <td>{{domainLabel(row.domain)}}</td><td>{{actionLabel(row.action)}}</td>
              <td><span class="event-label">{{resourceLabel(row.resource_type)}}</span><small class="event-id">{{row.resource_id}}</small></td></tr>
          }</tbody></table></div>
      }
      @if(cursor()){<div class="audit-pagination"><button class="secondary" type="button" (click)="loadMore()" [disabled]="loading()">Carregar mais</button></div>}
    </section>
    <p class="muted">Faturamento e Colaboradores passam a gerar histórico a partir desta atualização. Não são atribuídos autores ou datas a operações antigas sem registro.</p>
  }
`})
export class AuditPage {
  readonly workspaces=inject(Workspaces);private http=inject(HttpClient);private generation=0;
  readonly items=signal<EventRow[]>([]);readonly cursor=signal<string|null>(null);readonly loading=signal(false);readonly error=signal('');
  private applied:Record<string,string>={};
  readonly form=inject(FormBuilder).nonNullable.group({start:[defaultStart(),Validators.required],end:[utcDay(),Validators.required],domain:[''],action:['']});
  readonly domains=[{key:'EXPENSE',label:'Despesas'},{key:'PAYABLE',label:'Contas a pagar'},{key:'BILLING',label:'Faturamento'},{key:'PEOPLE',label:'Colaboradores'},{key:'ACCOUNTS',label:'Contas financeiras'}];
  readonly actions=[{key:'CREATED',label:'Cadastro'},{key:'UPDATED',label:'Alteração'},{key:'CANCELLED',label:'Cancelamento'},
    {key:'PAYMENT',label:'Pagamento'},{key:'RECEIVED',label:'Recebimento'},{key:'REVERSAL',label:'Estorno'},{key:'TERMINATED',label:'Desligamento'}];
  constructor(){effect(()=>{const company=this.workspaces.selected();untracked(()=>{
    this.generation++;this.items.set([]);this.cursor.set(null);this.error.set('');this.loading.set(false);
    if(company?.can_manage_access)void this.refresh();
  });});}
  dateLabel(value:string){return new Date(value).toLocaleString('pt-BR');}
  domainLabel(value:string){return this.domains.find(entry=>entry.key===value)?.label??value;}
  actionLabel(value:string){return this.actions.find(entry=>entry.key===value)?.label??value;}
  resourceLabel(value:string){return ({EXPENSE:'Despesa',PAYABLE:'Conta a pagar',BILLING:'Faturamento',CUSTOMER:'Cliente',RECEIPT:'Recebimento',COLLABORATOR:'Colaborador',ACCOUNT:'Conta financeira'} as Record<string,string>)[value]??value;}
  async refresh(){if(this.form.invalid)return;const values=this.form.getRawValue();
    const days=(Date.parse(values.end)-Date.parse(values.start))/86400000;
    this.generation++;this.items.set([]);this.cursor.set(null);this.error.set('');
    if(!Number.isFinite(days)||days<0||days>92){this.error.set('Selecione um período de até 93 dias.');return;}
    this.applied=Object.fromEntries(Object.entries(values).filter(([,value])=>!!value));await this.load(false);}
  async loadMore(){if(!this.loading()&&this.cursor())await this.load(true);}
  private async load(more:boolean){const company=this.workspaces.selected(),generation=this.generation;
    if(!company?.can_manage_access)return;this.loading.set(true);this.error.set('');
    const params:Record<string,string>={...this.applied,limit:'50'};if(more&&this.cursor())params['cursor']=this.cursor()!;
    try{const page=await firstValueFrom(this.http.get<Page>(`/api/v1/organizations/${company.organization_id}/companies/${company.company_id}/audit`,{params}).pipe(timeout(15000)));
      if(generation===this.generation){this.items.update(rows=>more?[...rows,...page.items]:page.items);this.cursor.set(page.next_cursor);}
    }catch{if(generation===this.generation){this.error.set('Não foi possível consultar o histórico. Verifique o período e sua autorização.');this.items.set([]);this.cursor.set(null);}}
    finally{if(generation===this.generation)this.loading.set(false);}}
}
