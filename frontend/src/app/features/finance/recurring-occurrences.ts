import { toSignal } from '@angular/core/rxjs-interop';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom, timeout } from 'rxjs';
import { FinanceApi, money, dateLabel } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';

interface Occurrence {
  id: string;
  rule_id: string;
  competence: string;
  description: string;
  supplier: string;
  amount: string | null;
  due_date: string;
  expense_id: string | null;
  status: 'PENDING' | 'GENERATED' | 'CANCELLED';
}

@Component({
  selector: 'sdf-recurring-occurrences',
  imports: [ReactiveFormsModule, RouterLink],
  styles: `
    :host { display: block; margin-top: 1rem; }
    .review-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr)); gap: 1rem; }
    label { display: grid; gap: .4rem; margin: 0; }
    input, select { width: 100%; min-width: 0; }
    .review-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: .625rem; margin-top: 1rem; }
    .primary { background: linear-gradient(115deg, #173762, #27548d); }
  `,
  template: `
    <section class="panel detail-panel register-list">
      @if (selectedId()) {
        <p><a class="secondary small" routerLink="../expenses" [queryParams]="{view:'rules'}">Ver todas as cobranças</a></p>
      }
      <div class="panel-heading">
        <div><h2>Cobranças mensais</h2><p class="muted">Confira os lançamentos gerados e revise as cobranças de valor variável.</p></div>
        <button class="secondary small" type="button" (click)="refresh.update(value => value + 1)" [disabled]="busy() || !!attempt">Atualizar</button>
      </div>
      @if (error()) { <p class="alert" role="alert">{{error()}}</p> }
      @if (message()) { <p class="notice" role="status">{{message()}}</p> }
      @if (reviewing(); as occurrence) {
        <h3>{{occurrence.description}}</h3>
        <p>{{occurrence.supplier}} · Competência {{occurrence.competence.slice(0, 7)}}</p>
        <form [formGroup]="form" (ngSubmit)="confirm()">
          <fieldset class="review-fields" [disabled]="busy() || !!attempt">
            <label>Valor da cobrança (R$)<input formControlName="amount" inputmode="decimal" maxlength="19"></label>
            <label>Vencimento<input type="date" formControlName="due_date" [min]="occurrence.competence"></label>
            <label>Tipo de comprovante<select formControlName="document_type">
              <option value="">Sem comprovante</option><option value="BOLETO">Boleto</option>
              <option value="NOTA_FISCAL">Nota fiscal</option><option value="OUTRO">Outro documento</option>
            </select></label>
            <label>Referência (opcional)<input formControlName="document_reference" maxlength="100"></label>
          </fieldset>
          <p class="muted">A confirmação registra a despesa e gera a conta a pagar.</p>
          <div class="review-actions">
            <button class="secondary" type="button" (click)="reviewing.set(null)" [disabled]="busy() || !!attempt">Voltar</button>
            <button class="primary" type="submit" [disabled]="busy() || (!attempt && form.invalid)">
              {{busy() ? 'Confirmando…' : attempt ? 'Tentar novamente' : 'Confirmar cobrança'}}
            </button>
          </div>
        </form>
      } @else if (loading()) { <p role="status">Consultando cobranças…</p> }
      @else if (!rows().length) {
        <p class="muted">Nenhuma cobrança mensal gerada. A geração ocorre em até um minuto após a ativação da recorrência.</p>
      } @else {
        <div class="table-scroll"><table><thead><tr>
          <th>Competência</th><th>Despesa</th><th>Vencimento</th><th class="numeric">Valor</th><th>Situação</th><th>Ação</th>
        </tr></thead><tbody>@for (row of rows(); track row.id) {
          <tr><td>{{row.competence.slice(0, 7)}}</td><td>{{row.description}}<small>{{row.supplier}}</small></td>
            <td>{{dateLabel(row.due_date)}}</td><td class="numeric">{{row.amount === null ? 'A confirmar' : money(row.amount)}}</td>
            <td><span class="badge" [class.cancelled]="row.status === 'CANCELLED'">
              {{row.status === 'PENDING' ? 'Aguardando revisão' : row.status === 'GENERATED' ? 'Gerada' : 'Cancelada'}}
            </span></td>
            <td>@if (row.status === 'PENDING' && workspaces.can('payables.manage')) {
              <button class="secondary small" type="button" (click)="open(row)">Revisar cobrança</button>
            } @else if (row.expense_id) {
              <a class="secondary small" routerLink="../expenses" [queryParams]="{view:'registered', expense:row.expense_id}">Ver despesa</a>
            }</td></tr>
        }</tbody></table></div>
        <p class="field-help">Exibindo até 200 cobranças recentes.</p>
      }
    </section>
  `,
})
export class RecurringOccurrences {
  private readonly params = toSignal(inject(ActivatedRoute).queryParamMap);
  selectedId():string|null { return this.params()?.get('occurrence') ?? null; }
  private readonly http = inject(HttpClient);
  readonly workspaces = inject(Workspaces);
  private readonly api = inject(FinanceApi);
  readonly money = money;
  readonly dateLabel = dateLabel;
  readonly rows = signal<Occurrence[]>([]);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly reviewing = signal<Occurrence | null>(null);
  readonly refresh = signal(0);
  private generation = 0;
  private companyKey = '';
  attempt: {path: string; body: object} | null = null;
  readonly form = inject(FormBuilder).nonNullable.group({
    amount: ['', [Validators.required, Validators.pattern(/^(?:0|[1-9]\d*)(?:[.,]\d{1,2})?$/)]],
    due_date: ['', Validators.required], document_type: [''], document_reference: [''],
  });

  constructor() {
    effect(onCleanup => {
      const company = this.workspaces.selected(), selectedId = this.selectedId();
      this.api.revision();
      this.refresh();
      const generation = ++this.generation;
      const path = company ? this.api.base(company).replace(/payables$/, 'expense-occurrences') : '';
      const key = path + '|' + (selectedId ?? '');
      if (key !== this.companyKey) {
        this.companyKey = key;
        this.reviewing.set(null);
        this.form.reset();
      }
      this.rows.set([]);
      this.error.set('');
      this.loading.set(!!path);
      if (!company || !this.workspaces.can('payables.read')) { this.loading.set(false); return; }
      const subscription = this.http.get<Occurrence[]>(path, selectedId ? {params: {occurrence_id:selectedId}} : {}).pipe(timeout(15000)).subscribe({
        next: rows => { if (generation === this.generation) { this.rows.set(rows); this.loading.set(false); if (selectedId && rows[0]?.status === 'PENDING' && this.workspaces.can('payables.manage')) this.open(rows[0]); } },
        error: () => { if (generation === this.generation) { this.error.set('Não foi possível consultar as cobranças.'); this.loading.set(false); } },
      });
      onCleanup(() => subscription.unsubscribe());
    });
  }

  open(row: Occurrence): void {
    this.error.set('');
    this.message.set('');
    this.form.reset({due_date: row.due_date});
    this.reviewing.set(row);
  }

  async confirm(): Promise<void> {
    const row = this.reviewing(), company = this.workspaces.selected();
    if (!row || !company || this.busy() || (!this.attempt && this.form.invalid)) return;
    const path = this.api.base(company).replace(/payables$/, 'expense-occurrences/') + row.id + '/confirm';
    const values = this.form.getRawValue();
    const attempt = this.attempt ?? {path, body: {...values, amount: values.amount.replace(',', '.'),
      document_type: values.document_type || null, document_reference: values.document_reference.trim() || null}};
    if (attempt.path !== path) {
      this.error.set('Volte à empresa da cobrança pendente para confirmar o envio.');
      return;
    }
    this.attempt = attempt;
    const generation = this.generation;
    this.busy.set(true);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(attempt.path, attempt.body).pipe(timeout(15000)));
      this.attempt = null;
      if (generation === this.generation) {
        this.reviewing.set(null);
        this.message.set('Cobrança confirmada. Despesa e conta a pagar registradas.');
        this.api.revision.update(value => value + 1);
      }
    } catch (failure) {
      if (generation === this.generation) {
        const status = (failure as HttpErrorResponse).status;
        if (status >= 400 && status < 500) this.attempt = null;
        this.error.set(status === 409 ? 'A recorrência foi cancelada ou a cobrança já foi confirmada com outros dados.'
          : this.attempt ? 'Envio sem confirmação. Tente novamente.' : 'Confira o valor, o vencimento e o comprovante.');
      }
    } finally {
      this.busy.set(false);
    }
  }
}
