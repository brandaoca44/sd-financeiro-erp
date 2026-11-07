import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { timeout } from 'rxjs';
import { FinanceApi, dateLabel, money, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';
import { ContextHelp } from '../../core/context-help';
interface Amounts {realized_in:string;realized_out:string;pending_in:string;pending_out:string;realized_net:string;projected_net:string}
interface Day extends Amounts {day:string;cumulative_realized:string;cumulative_projected:string}
interface Cashflow {as_of:string;start:string;end:string;totals:Amounts;days:Day[]}
const monthEnd=()=>{const day=today();return day.slice(0,8)+new Date(Date.UTC(+day.slice(0,4),+day.slice(5,7),0)).getUTCDate();};
@Component({selector:'sdf-cashflow',imports:[ReactiveFormsModule,ContextHelp],styles:`
  .flow-filters {display:flex;align-items:end;gap:1rem;flex-wrap:wrap;margin-bottom:1.25rem}
  .flow-filters label {display:grid;gap:.35rem;margin:0}
  .flow-cards {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,13rem),1fr));gap:1rem;margin-bottom:1.25rem}
  .flow-card {padding:1.1rem;border:1px solid #dce5f0;border-radius:.7rem;background:linear-gradient(145deg,#fff,#f3f7fc);min-width:0}
  .flow-card span,.flow-card small {display:block;color:#52657e}
  .flow-card strong {display:block;margin:.7rem 0;color:#173762;font-size:clamp(1.25rem,2vw,1.9rem);overflow-wrap:anywhere}
  .flow-card.negative {border-top:3px solid #bd4854}.flow-card.negative strong {color:#a12d3c}
  .flow-card.positive {border-top:3px solid #438974}
  .flow-note {font-size:.8125rem;line-height:1.6;margin-top:1rem}
  .flow-title {display:flex;align-items:center;gap:.5rem}.flow-title h2 {margin:0}
  .flow-table th {white-space:normal;min-width:8rem}.flow-table td {white-space:nowrap}
`,template:`
  <div class="page-heading"><div><span class="eyebrow">FINANCEIRO</span><h1>Fluxo de caixa</h1><p class="muted">Entradas, saídas e pendências por dia na empresa selecionada.</p></div></div>
  @if(!allowed()){
    <div class="empty-state"><h2>Consulta consolidada restrita</h2><p>Este painel exige consulta de Contas a pagar e de Faturamento na mesma empresa.</p></div>
  }@else{
    <form class="panel flow-filters" [formGroup]="form" (ngSubmit)="apply()">
      <label>De<input type="date" formControlName="start"></label><label>Até<input type="date" formControlName="end"></label>
      <button class="primary" type="submit" [disabled]="loading() || form.invalid">Consultar fluxo</button>
    </form>
    @if(error()){<p class="alert" role="alert">{{error()}}</p>}
    @if(loading()){<p role="status">Consolidando os registros financeiros…</p>}
    @if(report();as data){
      <div class="section-caption"><span>Posição atual em {{date(data.as_of)}}</span><span>Período de {{date(data.start)}} a {{date(data.end)}}</span></div>
      <div class="flow-cards">
        <article class="flow-card"><span>Entradas registradas</span><strong>{{money(data.totals.realized_in)}}</strong><small>Recebimentos válidos no período</small></article>
        <article class="flow-card"><span>Saídas registradas</span><strong>{{money(data.totals.realized_out)}}</strong><small>Pagamentos líquidos de estornos</small></article>
        <article class="flow-card" [class.negative]="negative(data.totals.realized_net)" [class.positive]="!negative(data.totals.realized_net)"><span>Variação realizada</span><strong>{{money(data.totals.realized_net)}}</strong><small>Entradas menos saídas registradas</small></article>
        <article class="flow-card"><span>Entradas pendentes</span><strong>{{money(data.totals.pending_in)}}</strong><small>Saldo a receber por vencimento</small></article>
        <article class="flow-card"><span>Saídas pendentes</span><strong>{{money(data.totals.pending_out)}}</strong><small>Saldo a pagar por vencimento</small></article>
        <article class="flow-card" [class.negative]="negative(data.totals.projected_net)" [class.positive]="!negative(data.totals.projected_net)"><span>Variação projetada</span><strong>{{money(data.totals.projected_net)}}</strong><small>Realizado mais pendências do período</small></article>
      </div>
      <section class="panel register-list">
        <div class="flow-title"><h2>Movimentação diária</h2><sdf-help text="Os valores pendentes seguem o vencimento original e descontam pagamentos ou recebimentos já registrados. Valores acumulados partem de zero no início do período. Um estorno de pagamento pode tornar a saída líquida do dia negativa. A projeção usa os títulos cadastrados e não estima receitas futuras ainda não registradas." /></div>
        <p class="muted">Os acumulados representam variações do período, sem saldo bancário inicial.</p>
        <div class="table-scroll"><table class="flow-table"><thead><tr><th>Data</th><th class="numeric">Entradas registradas</th><th class="numeric">Saídas registradas</th><th class="numeric">A receber</th><th class="numeric">A pagar</th><th class="numeric">Variação do dia</th><th class="numeric">Realizado acumulado</th><th class="numeric">Projetado acumulado</th></tr></thead>
          <tbody>@for(day of data.days;track day.day){<tr><td>{{date(day.day)}}</td><td class="numeric">{{money(day.realized_in)}}</td><td class="numeric">{{money(day.realized_out)}}</td><td class="numeric">{{money(day.pending_in)}}</td><td class="numeric">{{money(day.pending_out)}}</td><td class="numeric">{{money(day.realized_net)}}</td><td class="numeric">{{money(day.cumulative_realized)}}</td><td class="numeric">{{money(day.cumulative_projected)}}</td></tr>}</tbody>
        </table></div>
        <p class="muted flow-note">As pendências incluem atrasos pelo vencimento original que esteja neste intervalo. Recebimentos estornados deixam de compor o dia em que foram informados. Esta posição usa os registros atuais do ERP; não representa extrato bancário ou fechamento histórico.</p>
      </section>
    }
  }
`})
export class CashflowPage {
  readonly workspaces=inject(Workspaces);private http=inject(HttpClient);private api=inject(FinanceApi);
  readonly form=inject(FormBuilder).nonNullable.group({start:[today().slice(0,7)+'-01',Validators.required],end:[monthEnd(),Validators.required]});
  private range=signal(this.form.getRawValue());private refresh=signal(0);
  readonly report=signal<Cashflow|null>(null);readonly loading=signal(false);readonly error=signal('');readonly date=dateLabel;readonly money=money;
  allowed(){return this.workspaces.can('billing.read')&&this.workspaces.can('payables.read');}
  negative(value:string){return value.startsWith('-')&& /[1-9]/.test(value);}
  constructor(){effect(onCleanup=>{const company=this.workspaces.selected(),allowed=this.allowed(),range=this.range();this.api.revision();this.refresh();
    this.report.set(null);this.error.set('');this.loading.set(false);if(!company||!allowed)return;
    this.loading.set(true);const subscription=this.http.get<Cashflow>(this.api.base(company).replace(/payables$/,'cashflow'),{params:range}).pipe(timeout(15000)).subscribe({
      next:report=>{this.report.set(report);this.loading.set(false);},error:()=>{this.error.set('Não foi possível consultar o fluxo. Verifique o período, as permissões e os registros financeiros.');this.loading.set(false);}});
    onCleanup(()=>subscription.unsubscribe());
  });}
  apply(){const range=this.form.getRawValue(),days=(Date.parse(range.end)-Date.parse(range.start))/86400000;
    if(this.form.invalid||!Number.isFinite(days)||days<0||days>92){this.error.set('Selecione um período de até 93 dias.');return;}
    this.range.set(range);this.refresh.update(value=>value+1);
  }
}
