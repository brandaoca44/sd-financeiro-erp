import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Alerts, AlertKind } from '../../core/alerts';
import { Workspaces } from '../../core/workspaces';
import { money, dateLabel } from '../../core/finance';

@Component({
  selector: 'sdf-alerts-page',
  imports: [RouterLink],
  styles: `
    .alert-filters { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
    .alert-filters button[aria-pressed="true"] { background: #e3edf9; color: #173762; border-color: #9eb9d9; }
    .alert-type { display: inline-block; border-radius: .4rem; padding: .3rem .5rem; font-size: .8125rem; background: #eaf1fa; color: #24486c; }
    .alert-type.overdue { background: #fff0f1; color: #962832; }
    .alert-type.today { background: #fff2e9; color: #97451f; }
    .alert-type.review { background: #f0edfb; color: #53467d; }
  `,
  template: `
    <div class="page-heading"><div><span class="eyebrow">FINANCEIRO</span><h1>Central de alertas</h1>
      <p class="muted">Pendências atuais da empresa selecionada.</p></div>
      <button class="secondary" type="button" (click)="alerts.refresh()" [disabled]="alerts.loading()">Atualizar</button>
    </div>
    @if (!workspaces.can('payables.read')) {
      <p class="notice">Seu perfil precisa da permissão de consulta financeira para acessar os alertas desta empresa.</p>
    } @else if (alerts.failed()) {
      <p class="alert" role="alert">Não foi possível consultar os alertas. Tente atualizar.</p>
    } @else if (alerts.loading()) { <p role="status">Consultando pendências…</p> }
    @else if (alerts.report(); as report) {
      <nav class="alert-filters" aria-label="Tipos de alerta">
        @for (option of filters; track option.key) {
          <button class="secondary small" type="button" [attr.aria-pressed]="filter() === option.key"
            (click)="filter.set(option.key)">{{option.label}} ({{count(option.key)}})</button>
        }
      </nav>
      <section class="panel detail-panel register-list">
        <h2>{{report.total}} pendências atuais</h2>
        <p class="muted">Posição em {{dateLabel(report.as_of)}}. Próximos vencimentos incluem amanhã até os próximos sete dias.</p>
        @if (!items().length) {
          <p class="muted">{{report.total ? 'Nenhum alerta deste tipo entre os registros exibidos.' : 'Nenhuma pendência identificada nesta empresa.'}}</p>
        } @else {
          <div class="table-scroll"><table><thead><tr>
            <th>Alerta</th><th>Cobrança</th><th>Vencimento</th><th class="numeric">Saldo em aberto</th><th>Ação</th>
          </tr></thead><tbody>
            @for (alert of items(); track alert.kind + alert.id) {
              <tr><td><span class="alert-type" [class.overdue]="alert.kind === 'OVERDUE'" [class.today]="alert.kind === 'TODAY'"
                [class.review]="alert.kind === 'REVIEW'">{{label(alert.kind)}}</span></td>
                <td>{{alert.description}}</td><td>{{dateLabel(alert.due_date)}}</td>
                <td class="numeric">{{alert.amount === null ? 'A confirmar' : money(alert.amount)}}</td>
                <td>@if (alert.kind === 'REVIEW') {
                  <a class="secondary small" routerLink="../expenses" [queryParams]="{view:'rules', occurrence:alert.id}">Ver cobrança</a>
                } @else {
                  <a class="secondary small" routerLink="../payables" [queryParams]="{title:alert.id}">Ver título</a>
                }</td>
              </tr>
            }
          </tbody></table></div>
        }
        @if (report.total > report.items.length) {
          <p class="field-help">Exibindo {{report.items.length}} pendências por prioridade, de {{report.total}} no total. Os contadores incluem todas as pendências.</p>
        }
      </section>
    }
  `,
})
export class AlertsPage {
  readonly alerts = inject(Alerts);
  readonly workspaces = inject(Workspaces);
  readonly money = money;
  readonly dateLabel = dateLabel;
  readonly filter = signal<AlertKind | 'ALL'>('ALL');
  readonly filters: {key: AlertKind | 'ALL'; label: string}[] = [
    {key: 'ALL', label: 'Todas'}, {key: 'OVERDUE', label: 'Vencidas'}, {key: 'TODAY', label: 'Vencem hoje'},
    {key: 'REVIEW', label: 'Aguardando revisão'}, {key: 'UPCOMING', label: 'Próximos 7 dias'},
  ];
  readonly items = computed(() => (this.alerts.report()?.items ?? []).filter(item =>
    this.filter() === 'ALL' || item.kind === this.filter()));

  count(kind: AlertKind | 'ALL'): number {
    const report = this.alerts.report();
    if (!report) return 0;
    return {ALL: report.total, OVERDUE: report.overdue, TODAY: report.today, UPCOMING: report.upcoming, REVIEW: report.review}[kind];
  }

  label(kind: AlertKind): string {
    return {OVERDUE: 'Vencida', TODAY: 'Vence hoje', UPCOMING: 'Próximo vencimento', REVIEW: 'Aguardando revisão'}[kind];
  }
}
