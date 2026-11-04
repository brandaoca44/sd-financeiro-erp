import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FinanceApi, dateLabel, money, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';

interface Payment {
  id: string;
  expense_id: string | null;
  description: string;
  supplier: string | null;
  category: string | null;
  document_type: string | null;
  document_reference: string | null;
  occurred_on: string;
  amount: string;
  status: 'PARCIAL' | 'INTEGRAL' | 'ESTORNO' | 'ESTORNADO';
}

interface Report {items: Payment[]; count: number; paid: string; reversed: string; net: string}

@Component({
  selector: 'sdf-monthly-payments',
  imports: [RouterLink],
  template: `
    <section class="panel detail-panel register-list">
      <div class="panel-heading">
        <div><h2>Pagamentos do mês</h2><p class="muted">Baixas e estornos pela data registrada de cada movimento.</p></div>
        <label>Mês do pagamento <input type="month" [value]="month()" (change)="changeMonth($event)"></label>
      </div>
      @if (error()) { <p class="alert" role="alert">Não foi possível consultar os pagamentos.</p> }
      @else if (loading()) { <p role="status">Consultando pagamentos…</p> }
      @else if (report(); as data) {
        <div class="detail-summary">
          <div><span>Baixas registradas</span><strong>{{money(data.paid)}}</strong></div>
          <div><span>Estornos no mês</span><strong>{{money(data.reversed)}}</strong></div>
          <div><span>Total líquido</span><strong>{{money(data.net)}}</strong></div>
        </div>
        @if (!data.items.length) { <p class="muted">Nenhum pagamento ou estorno no mês selecionado.</p> }
        @else {
          <div class="table-scroll"><table>
            <thead><tr><th>Cobrança</th><th>Categoria e comprovante</th><th>Data</th>
              <th class="numeric">Valor</th><th>Situação</th><th>Origem</th></tr></thead>
            <tbody>@for (row of data.items; track row.id) {
              <tr><td>{{row.description}} @if (row.supplier) { <small>{{row.supplier}}</small> }</td>
                <td>{{label(row.category)}}<small>{{label(row.document_type)}} {{row.document_reference}}</small></td>
                <td>{{dateLabel(row.occurred_on)}}</td>
                <td class="numeric">{{money(row.status === 'ESTORNO' ? '-' + row.amount : row.amount)}}</td>
                <td><span class="badge" [class.cancelled]="row.status === 'ESTORNO' || row.status === 'ESTORNADO'">{{label(row.status)}}</span></td>
                <td>@if (row.expense_id) {
                  <a class="secondary small" routerLink="../expenses" [queryParams]="{view:'registered', expense:row.expense_id}">Ver despesa</a>
                } @else { — }</td>
              </tr>
            }</tbody>
          </table></div>
          @if (data.count > data.items.length) {
            <p class="muted">Exibindo os {{data.items.length}} movimentos mais recentes de {{data.count}}. Os totais incluem todo o mês.</p>
          }
        }
      }
    </section>
  `,
})
export class MonthlyPayments {
  private readonly http = inject(HttpClient);
  private readonly workspaces = inject(Workspaces);
  private readonly api = inject(FinanceApi);
  readonly month = signal(today().slice(0, 7));
  readonly report = signal<Report | null>(null);
  readonly error = signal(false);
  readonly loading = signal(false);
  readonly money = money;
  readonly dateLabel = dateLabel;

  constructor() {
    effect(onCleanup => {
      const company = this.workspaces.selected(), month = this.month();
      this.api.revision();
      this.report.set(null);
      this.error.set(false);
      this.loading.set(!!company);
      if (!company) return;
      const url = this.api.base(company).replace(/payables$/, 'expenses/monthly-payments');
      const subscription = this.http.get<Report>(url, {params: {month}}).subscribe({
        next: report => { this.report.set(report); this.loading.set(false); },
        error: () => { this.error.set(true); this.loading.set(false); },
      });
      onCleanup(() => subscription.unsubscribe());
    });
  }

  changeMonth(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    if (value) this.month.set(value);
  }

  label(value: string | null): string {
    const labels: Record<string, string> = {
      INTERNET: 'Internet', ENERGIA: 'Luz', AGUA: 'Água', ESGOTO: 'Esgoto', ALUGUEL: 'Aluguel',
      PESSOAL: 'Pessoal', ASSINATURA: 'Assinaturas', OUTROS: 'Outras despesas',
      BOLETO: 'Boleto', NOTA_FISCAL: 'Nota fiscal', OUTRO: 'Outro documento',
      PARCIAL: 'Pagamento parcial', INTEGRAL: 'Pagamento integral', ESTORNO: 'Estorno', ESTORNADO: 'Estornado',
    };
    return value ? labels[value] ?? value : '—';
  }
}
