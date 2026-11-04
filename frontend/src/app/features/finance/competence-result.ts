import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { timeout } from 'rxjs';
import { ContextHelp } from '../../core/context-help';
import { FinanceApi, money, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';

interface CompetenceResult {
  month: string;
  revenue: string;
  expenses: string;
  result: string;
  status: 'PROFIT' | 'LOSS' | 'BREAK_EVEN' | 'NO_ACTIVITY';
  revenue_count: number;
  expense_count: number;
  unassigned_expenses: number;
  unlinked_payables: number;
  partial: true;
}

@Component({
  selector: 'sdf-competence-result',
  imports: [ContextHelp],
  styles: `
    :host { display: block; margin-bottom: 1.5rem; }
    .result-heading { display: flex; justify-content: space-between; flex-wrap: wrap; align-items: center; gap: 1rem; margin-bottom: 1rem; }
    .result-title { display: flex; align-items: center; gap: .5rem; }
    .result-title h2 { margin: 0; }
    .result-filter { display: flex; flex-wrap: wrap; align-items: end; gap: .5rem; }
    .result-filter label { display: grid; gap: .35rem; margin: 0; }
    .result-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
    .result-card { border: 1px solid #dbe5f0; border-radius: .625rem; padding: 1.1rem; background: linear-gradient(145deg, #fff, #f2f6fc); }
    .result-card span, .result-card small { display: block; color: #50637d; }
    .result-card strong { display: block; margin-block: .65rem; font-size: clamp(1.25rem, 2.1vw, 1.8rem); color: #183754; overflow-wrap: anywhere; }
    .result-card.loss { border-top: 3px solid #c85f68; }
    .result-card.loss strong { color: #962832; }
    .result-card.profit { border-top: 3px solid #428875; }
    .result-card.profit strong { color: #246852; }
    .result-note { margin: 1rem 0 0; color: #50637d; }
    @media (max-width: 700px) { .result-cards { grid-template-columns: minmax(0, 1fr); } }
  `,
  template: `
    <section class="panel detail-panel" aria-labelledby="competence-title">
      <div class="result-heading">
        <div class="result-title">
          <h2 id="competence-title">Resultado por competência</h2>
          <sdf-help text="O faturamento segue o mês de prestação do serviço. As despesas seguem a competência informada no cadastro. Recebimentos e pagamentos são acompanhados nos respectivos históricos." />
        </div>
        <div class="result-filter">
          <label>Competência<input type="month" [value]="month()" (change)="changeMonth($event)"></label>
          <button class="secondary small" type="button" (click)="refresh.update(value => value + 1)" [disabled]="loading()">Atualizar</button>
        </div>
      </div>
      @if (loading()) { <p role="status">Calculando os registros da competência…</p> }
      @else if (restricted()) { <p class="muted">A consulta do resultado está disponível ao Master da organização.</p> }
      @else if (error()) { <p class="alert" role="alert">Não foi possível consultar o resultado. Tente atualizar.</p> }
      @else if (report(); as data) {
        <div class="result-cards">
          <article class="result-card"><span>Faturamento bruto</span><strong>{{money(data.revenue)}}</strong>
            <small>{{data.revenue_count}} serviços faturados</small></article>
          <article class="result-card"><span>Despesas registradas</span><strong>{{money(data.expenses)}}</strong>
            <small>{{data.expense_count}} despesas na competência</small></article>
          <article class="result-card" [class.loss]="data.status === 'LOSS'" [class.profit]="data.status === 'PROFIT'">
            <span>{{resultLabel(data.status)}}</span><strong>{{money(data.result)}}</strong>
            <small>Resultado gerencial parcial</small>
          </article>
        </div>
        @if (data.status === 'NO_ACTIVITY') { <p class="result-note">Nenhum faturamento ou despesa com competência informada neste mês.</p> }
        <p class="result-note">Apuração parcial dos registros disponíveis. Folha, tributos, deduções e custos ainda precisam ser integrados e conferidos para apurar o resultado completo.</p>
        @if (data.unassigned_expenses || data.unlinked_payables) {
          <p class="info-note" role="status">Pendências da empresa que ficaram fora do cálculo.
            {{data.unassigned_expenses}} despesas sem competência e {{data.unlinked_payables}} títulos ativos sem despesa vinculada.
          </p>
        }
      }
    </section>
  `,
})
export class CompetenceResultPanel {
  private readonly http = inject(HttpClient);
  private readonly workspaces = inject(Workspaces);
  private readonly api = inject(FinanceApi);
  readonly money = money;
  readonly month = signal(today().slice(0, 7));
  readonly refresh = signal(0);
  readonly report = signal<CompetenceResult | null>(null);
  readonly loading = signal(false);
  readonly restricted = signal(false);
  readonly error = signal(false);

  constructor() {
    effect(onCleanup => {
      const company = this.workspaces.selected(), month = this.month();
      this.refresh();
      this.api.revision();
      this.report.set(null);
      this.restricted.set(false);
      this.error.set(false);
      this.loading.set(false);
      if (!company || !this.workspaces.can('payables.read')) return;
      this.loading.set(true);
      const url = this.api.base(company).replace(/payables$/, 'results');
      const subscription = this.http.get<CompetenceResult>(url, {params: {month}}).pipe(timeout(15000)).subscribe({
        next: report => { this.report.set(report); this.loading.set(false); },
        error: (error: HttpErrorResponse) => {
          this.restricted.set(error.status === 403 || error.status === 404);
          this.error.set(!this.restricted());
          this.loading.set(false);
        },
      });
      onCleanup(() => subscription.unsubscribe());
    });
  }

  changeMonth(event: Event): void {
    const month = (event.target as HTMLInputElement).value;
    if (month) this.month.set(month);
  }

  resultLabel(status: CompetenceResult['status']): string {
    return {PROFIT: 'Lucro parcial', LOSS: 'Prejuízo parcial', BREAK_EVEN: 'Resultado equilibrado',
      NO_ACTIVITY: 'Sem movimento registrado'}[status];
  }
}
