import { ReceivablesSummaryPanel } from './receivables-summary';
import { CompetenceResultPanel } from './competence-result';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { FinanceApi, Summary, money, dateLabel, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';
import { errorMessage } from '../../core/session';

@Component({selector:'sdf-overview',imports:[ReactiveFormsModule,RouterLink,CompetenceResultPanel,ReceivablesSummaryPanel],template:`
<div class="page-heading"><div><span class="eyebrow">ACOMPANHAMENTO FINANCEIRO</span><h1>Visão financeira</h1><p class="muted">Consulte pagamentos, recebimentos e vencimentos da empresa.</p></div>@if(workspaces.can('payables.read')){<a class="primary" routerLink="/finance/payables">Ver contas a pagar <span aria-hidden="true">↗</span></a>}</div>
@if(workspaces.can('payables.read') && workspaces.can('billing.read')){<p><a class="secondary small" routerLink="/finance/cashflow">Consultar fluxo de caixa consolidado</a></p>}
<sdf-receivables-summary />
@if(!workspaces.can('payables.read') && !workspaces.can('billing.read')){<div class="empty-state"><h2>Consulta financeira restrita</h2><p>Seu perfil não permite consultar os indicadores desta empresa. Peça ao Master para revisar seu acesso.</p></div>}@else if(workspaces.can('payables.read')){
<sdf-competence-result />
<section class="filter-panel"><div><strong>Atividade do período</strong><small>Os saldos exibidos nos cartões são atuais.</small></div><form class="date-filter" [formGroup]="form" (ngSubmit)="load()"><label>De<input type="date" formControlName="start" required></label><span class="filter-divider">—</span><label>Até<input type="date" formControlName="end" required></label><button class="secondary" type="submit" [disabled]="busy() || form.invalid">{{busy()?'Atualizando…':'Atualizar'}}</button></form></section>
@if(error()){<div class="alert" role="alert">{{error()}}</div>}
@if(busy()){<div class="loading-strip" role="status">Buscando indicadores da empresa selecionada…</div>}
@if(report();as data){<div class="section-caption"><span><i class="status-dot"></i> Posição atual em {{date(data.as_of)}}</span><span>Valores em reais · Contas a pagar</span></div>
<div class="metrics-grid"><article class="metric-card"><span class="metric-label">Saldo em aberto <span class="metric-icon">↗</span></span><strong>{{money(data.current.outstanding_amount)}}</strong><small>{{data.current.active_title_count}} títulos não cancelados</small></article>
<article class="metric-card warning due-today"><span class="metric-label">Vencem hoje <span class="metric-icon">▦</span></span><strong>{{money(data.current.due_today_amount)}}</strong><small>Para acompanhar de perto</small></article>
<article class="metric-card warning"><span class="metric-label">Vencidos <span class="metric-icon">◷</span></span><strong>{{money(data.current.overdue_amount)}}</strong><small>Saldo com vencimento anterior a hoje</small></article>
<article class="metric-card"><span class="metric-label">Próximos {{data.upcoming_days}} dias <span class="metric-icon">→</span></span><strong>{{money(data.current.upcoming_amount)}}</strong><small>A partir de amanhã</small></article></div>
<div class="insight-grid"><section class="panel chart-panel"><div class="panel-heading"><div><h2>Vencimentos e baixas</h2><p>Organize os compromissos. Acompanhe o que foi informado.</p></div><span class="pill">Por dia</span></div><div class="chart-legend"><span><i class="legend-bar"></i> Saldo atual por vencimento</span><span><i class="legend-line"></i> Baixas informadas no dia</span></div>
<div class="chart-wrap"><svg viewBox="0 0 900 230" role="img" aria-label="Saldo atual por vencimento e baixas informadas por dia. Valores exatos disponíveis na tabela abaixo."><line x1="20" y1="30" x2="880" y2="30" class="gridline"/><line x1="20" y1="90" x2="880" y2="90" class="gridline"/><line x1="20" y1="150" x2="880" y2="150" class="gridline"/><line x1="20" y1="200" x2="880" y2="200" class="gridline"/>
@for(bar of bars;track bar.index){<rect [attr.x]="bar.x" [attr.y]="200-bar.height" [attr.width]="bar.width" [attr.height]="bar.height" rx="3" class="chart-bar"/>}<path [attr.d]="line" class="chart-line"/><text x="20" y="225">{{date(data.days[0]?.day || '')}}</text><text x="880" y="225" text-anchor="end">{{date(data.days[data.days.length-1]?.day || '')}}</text></svg></div>
<details class="chart-details"><summary>Consultar valores diários</summary><div class="table-scroll"><table><thead><tr><th>Data</th><th class="numeric">Saldo por vencimento</th><th class="numeric">Baixas</th><th class="numeric">Estornos</th></tr></thead><tbody>@for(day of data.days;track day.day){<tr><td>{{date(day.day)}}</td><td class="numeric">{{money(day.outstanding_due_amount)}}</td><td class="numeric">{{money(day.payments_amount)}}</td><td class="numeric">{{money(day.reversals_amount)}}</td></tr>}</tbody></table></div></details></section>
<section class="panel period-panel"><span class="eyebrow">NO PERÍODO SELECIONADO</span><h2>Movimentação registrada</h2><p class="muted">Baixas e estornos pelas datas informadas.</p><div class="period-row"><span><i class="period-symbol blue">↘</i> Baixas manuais</span><strong>{{money(data.period.payments_amount)}}</strong></div><div class="period-row"><span><i class="period-symbol amber">↗</i> Estornos</span><strong>{{money(data.period.reversals_amount)}}</strong></div><div class="period-total"><span>Líquido do período</span><strong>{{money(data.period.net_paid_amount)}}</strong></div><div class="info-note">Este resumo acompanha contas a pagar. Os valores não representam saldo bancário ou lucro.</div></section></div>
<section class="guidance-strip"><div class="guidance-symbol">◇</div><div><strong>Informação que ajuda a decidir</strong><p>Revise os títulos vencidos e os próximos vencimentos para organizar seus pagamentos.</p></div><a routerLink="/finance/payables">Consultar títulos →</a></section>
} @else if(!busy() && !error()){<div class="empty-state"><h2>Pronto para acompanhar suas contas</h2><p>Atualize o período para consultar os indicadores.</p></div>}}
`})
export class Overview {
  readonly workspaces=inject(Workspaces);private api=inject(FinanceApi);private generation=0;
  readonly report=signal<Summary|null>(null);readonly busy=signal(false);readonly error=signal('');
  readonly money=money;readonly date=dateLabel;
  readonly form=inject(FormBuilder).nonNullable.group({start:[today().slice(0,7)+'-01',Validators.required],end:[today(),Validators.required]});
  constructor(){inject(DestroyRef).onDestroy(()=>this.generation++);effect(()=>{this.workspaces.selected();this.api.revision();untracked(()=>void this.load());});}
  async load():Promise<void>{const id=++this.generation,workspace=this.workspaces.selected();this.report.set(null);this.error.set('');this.busy.set(false);if(!workspace || !this.workspaces.can('payables.read'))return;
    const {start,end}=this.form.getRawValue();if(!start || !end || start>end){this.error.set('Confira o intervalo de datas.');return;}this.busy.set(true);
    try{const result=await this.api.summary(workspace,start,end);if(id===this.generation && this.workspaces.selected()?.company_id===workspace.company_id)this.report.set(result);}
    catch(error){if(id===this.generation)this.error.set(errorMessage(error));}finally{if(id===this.generation)this.busy.set(false);}}
  private points(){const days=this.report()?.days || [];const max=Math.max(1,...days.flatMap(day=>[Number(day.outstanding_due_amount),Number(day.payments_amount)]));return days.map((day,index)=>({index,x:20+(index+.5)*860/days.length,height:Math.max(0,Number(day.outstanding_due_amount)/max*170),payment:Math.max(0,Number(day.payments_amount)/max*170),width:Math.max(1,Math.min(25,600/days.length))}));}
  get bars(){return this.points().map(point=>({...point,x:point.x-point.width/2}));}
  get line():string{return this.points().map((point,index)=>`${index?'L':'M'}${point.x},${200-point.payment}`).join(' ');}
}
