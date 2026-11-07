import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { timeout } from 'rxjs';
import { ContextHelp } from '../../core/context-help';
import { FinanceApi, dateLabel, money, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';

interface ReceivableSummary {
  as_of:string;month:string;upcoming_days:number;
  outstanding_amount:string;outstanding_count:number;overdue_amount:string;overdue_count:number;
  due_today_amount:string;due_today_count:number;upcoming_amount:string;upcoming_count:number;
  received_amount:string;received_count:number;
}
@Component({selector:'sdf-receivables-summary',imports:[RouterLink,ContextHelp],styles:`
  :host {display:block;margin-bottom:1.5rem}
  .receivable-heading {display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;margin-bottom:1rem}
  .receivable-title {display:flex;align-items:center;gap:.5rem}
  .receivable-title h2 {margin:0}
  .receivable-filter {display:flex;align-items:end;gap:.65rem;flex-wrap:wrap}
  .receivable-filter label {display:grid;gap:.35rem;margin:0;font-size:.8125rem}
  .receivable-cards {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr));gap:1rem}
  .receivable-card {border:1px solid #dce5f0;border-radius:.7rem;padding:1.1rem;background:linear-gradient(145deg,#fff,#f4f8fd);min-width:0}
  .receivable-card span,.receivable-card small {display:block;color:#52657e}
  .receivable-card span {font-size:.875rem;font-weight:550}
  .receivable-card strong {display:block;margin:.7rem 0;font-size:clamp(1.2rem,1.7vw,1.8rem);color:#173762;overflow-wrap:anywhere}
  .receivable-card small {font-size:.75rem;line-height:1.5}
  .receivable-card.received {border-top:3px solid #438974}
  .receivable-card.received strong {color:#246852}
  .receivable-card.today {border-top:3px solid #b97821}
  .receivable-card.today strong {color:#875410}
  .receivable-card.overdue {border-top:3px solid #bd4854}
  .receivable-card.overdue strong {color:#a12d3c}
  .receivable-footer {display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;margin-top:1rem}
  .receivable-footer p {margin:0;max-width:55rem;font-size:.8125rem}
`,template:`
  @if(workspaces.can('billing.read')){
    <section class="panel detail-panel" aria-labelledby="receivables-title">
      <div class="receivable-heading"><div class="receivable-title"><h2 id="receivables-title">Contas a receber</h2>
        <sdf-help text="Em aberto, vencimentos e atrasos mostram os saldos atuais das cobranças, descontando recebimentos parciais válidos. Recebidos no mês considera a data informada e exclui recebimentos estornados. Faturamento por competência, lucro e saldo bancário são indicadores distintos." />
      </div><div class="receivable-filter"><label>Recebimentos do mês<input type="month" [value]="month()" (change)="changeMonth($event)"></label>
        <button class="secondary small" type="button" (click)="refresh.update(value=>value+1)" [disabled]="loading()">Atualizar</button>
      </div></div>
      @if(loading()){<p role="status">Consultando cobranças e recebimentos…</p>}
      @else if(error()){<p class="alert" role="alert">{{error()}}</p>}
      @else if(report();as data){
        <div class="section-caption"><span>Posição atual em {{date(data.as_of)}}</span><span>Valores em reais</span></div>
        <div class="receivable-cards">
          <article class="receivable-card received"><span>Recebidos no mês</span><strong>{{money(data.received_amount)}}</strong><small>{{data.received_count}} recebimentos válidos em {{monthLabel(data.month)}}</small></article>
          <article class="receivable-card"><span>Saldo a receber</span><strong>{{money(data.outstanding_amount)}}</strong><small>{{data.outstanding_count}} cobranças com saldo em aberto</small></article>
          <article class="receivable-card today"><span>Vencem hoje</span><strong>{{money(data.due_today_amount)}}</strong><small>{{data.due_today_count}} cobranças para acompanhar</small></article>
          <article class="receivable-card overdue"><span>Em atraso</span><strong>{{money(data.overdue_amount)}}</strong><small>{{data.overdue_count}} cobranças vencidas</small></article>
          <article class="receivable-card"><span>Próximos {{data.upcoming_days}} dias</span><strong>{{money(data.upcoming_amount)}}</strong><small>{{data.upcoming_count}} cobranças a partir de amanhã</small></article>
        </div>
      }
      <div class="receivable-footer"><p class="muted">A seleção do mês altera apenas os recebimentos. Os demais cartões mostram a posição atual. Estornos retiram o recebimento do mês em que ele foi registrado.</p>
        <a class="secondary small" routerLink="/finance/billing" [queryParams]="{view:'receivables'}">Ver contas a receber</a></div>
    </section>
  }
`})
export class ReceivablesSummaryPanel {
  readonly workspaces=inject(Workspaces);private http=inject(HttpClient);private api=inject(FinanceApi);
  readonly report=signal<ReceivableSummary|null>(null);readonly loading=signal(false);readonly error=signal('');
  readonly month=signal(today().slice(0,7));readonly refresh=signal(0);readonly money=money;readonly date=dateLabel;
  constructor(){effect(onCleanup=>{const company=this.workspaces.selected(),allowed=this.workspaces.can('billing.read'),month=this.month();this.api.revision();this.refresh();
    this.report.set(null);this.error.set('');this.loading.set(false);if(!company||!allowed)return;
    if(!/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(month)){this.error.set('Selecione um mês válido.');return;}
    this.loading.set(true);const url=this.api.base(company).replace(/payables$/,'receivables-summary');
    const subscription=this.http.get<ReceivableSummary>(url,{params:{month}}).pipe(timeout(15000)).subscribe({
      next:report=>{this.report.set(report);this.loading.set(false);},error:()=>{this.report.set(null);this.error.set('Não foi possível consultar os recebimentos desta empresa. Tente atualizar.');this.loading.set(false);}});
    onCleanup(()=>subscription.unsubscribe());
  });}
  changeMonth(event:Event){this.month.set((event.target as HTMLInputElement).value);}
  monthLabel(value:string){return value.slice(5,7)+'/'+value.slice(0,4);}
}
