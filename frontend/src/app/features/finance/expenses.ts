import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom, timeout } from 'rxjs';
import { FinanceApi, dateLabel, money, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';

const categories = [
  ['INTERNET', 'Internet'], ['ENERGIA', 'Luz'], ['AGUA', 'Água'], ['ESGOTO', 'Esgoto'],
  ['ALUGUEL', 'Aluguel'], ['PESSOAL', 'Pessoal'], ['OUTROS', 'Outras despesas'],
];

interface Expense {
  id: string;
  description: string;
  category: string;
  supplier: string;
  document_type: string | null;
  document_reference: string | null;
  amount: string;
  issue_date: string;
  due_date: string | null;
  payable_id: string | null;
}

@Component({
  selector: 'sdf-expenses',
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <div class="page-heading"><div><span class="eyebrow">FINANCEIRO</span><h1>Despesas</h1>
      <p class="muted">Classifique os gastos da empresa e vincule os documentos de origem.</p></div></div>
    @if (message()) { <p role="status">{{message()}}</p> }
    @if (error()) { <p role="alert">{{error()}}</p> }
    @if (workspaces.can('payables.manage')) {
      <section class="panel detail-panel">
        <h2>Nova despesa</h2>
        <form [formGroup]="form" (ngSubmit)="save()">
          <fieldset [disabled]="saving() || pending !== null">
            <label for="expense-description">Descrição</label>
            <input id="expense-description" formControlName="description" maxlength="300">
            <div class="form-grid">
              <label>Categoria<select formControlName="category">
                <option value="">Selecione</option>
                @for (category of categories; track category[0]) {
                  <option [value]="category[0]">{{category[1]}}</option>
                }
              </select></label>
              <label>Fornecedor<input formControlName="supplier" maxlength="150"></label>
              <label>Tipo de documento<select formControlName="document_type">
                <option value="">Sem documento</option><option value="BOLETO">Boleto</option>
                <option value="NOTA_FISCAL">Nota fiscal</option><option value="OUTRO">Outro documento</option>
              </select></label>
              <label>Referência do documento<input formControlName="document_reference" maxlength="100"></label>
              <label>Valor (R$)<input formControlName="amount" inputmode="decimal" maxlength="19"></label>
              <label>Emissão<input type="date" formControlName="issue_date"></label>
              <label>Vencimento (opcional)<input type="date" formControlName="due_date"></label>
            </div>
            <p class="muted">Preencha o vencimento para gerar uma obrigação em Contas a pagar.</p>
          </fieldset>
          <button class="primary" type="submit" [disabled]="saving() || (!pending && form.invalid)">
            {{saving() ? 'Salvando…' : pending ? 'Tentar novamente' : 'Salvar despesa'}}
          </button>
        </form>
      </section>
    }
    @if (workspaces.can('payables.read')) {
      <section class="panel detail-panel">
        <h2>Despesas registradas</h2>
        @if (loading()) { <p>Carregando despesas…</p> }
        @else if (expenses().length === 0) { <p class="muted">Nenhuma despesa para exibir.</p> }
        @else {
          <div class="table-wrap">
            <table>
              <thead><tr><th>Despesa</th><th>Categoria</th><th>Fornecedor e documento</th><th>Valor</th><th>Vencimento</th></tr></thead>
              <tbody>@for (expense of expenses(); track expense.id) {
                <tr><td>{{expense.description}}</td><td>{{label(expense.category)}}</td>
                  <td>{{expense.supplier}} @if (expense.document_type) {
                    <small>{{documentLabel(expense.document_type)}} {{expense.document_reference}}</small>
                  }</td>
                  <td>{{money(expense.amount)}}</td>
                  <td>@if (expense.payable_id && expense.due_date) {
                    {{dateLabel(expense.due_date)}} <a routerLink="../payables">Contas a pagar</a>
                  } @else { — }</td></tr>
              }</tbody>
            </table>
          </div>
        }
      </section>
    }
  `,
})
export class Expenses {
  readonly workspaces = inject(Workspaces);
  private readonly api = inject(FinanceApi);
  private readonly http = inject(HttpClient);
  readonly categories = categories;
  readonly money = money;
  readonly dateLabel = dateLabel;
  readonly expenses = signal<Expense[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly message = signal('');
  readonly error = signal('');
  private listRequest = 0;
  pending: {url: string; key: string; body: unknown} | null = null;

  readonly form = inject(FormBuilder).nonNullable.group({
    description: ['', Validators.required],
    category: ['', Validators.required],
    supplier: ['', Validators.required],
    document_type: [''],
    document_reference: [''],
    amount: ['', [Validators.required, Validators.pattern(/^(?:0|[1-9]\d*)(?:[.,]\d{1,2})?$/)]],
    issue_date: [today(), Validators.required],
    due_date: [''],
  });

  constructor() {
    effect(() => {
      const company = this.workspaces.selected();
      untracked(() => {
        this.form.reset({issue_date: today()});
        this.error.set('');
        this.message.set('');
        void this.load(company && this.workspaces.can('payables.read') ? this.url(company) : null);
      });
    });
  }

  private url(company: NonNullable<ReturnType<Workspaces['selected']>>): string {
    return this.api.base(company).replace(/\/payables$/, '/expenses');
  }

  label(category: string): string {
    return categories.find(([key]) => key === category)?.[1] ?? category;
  }

  documentLabel(type: string): string {
    return type === 'NOTA_FISCAL' ? 'Nota fiscal' : type === 'BOLETO' ? 'Boleto' : 'Outro documento';
  }

  private async load(url: string | null): Promise<void> {
    const request = ++this.listRequest;
    this.expenses.set([]);
    this.loading.set(url !== null);
    if (!url) return;
    try {
      const rows = await firstValueFrom(this.http.get<Expense[]>(url).pipe(timeout(15000)));
      if (request === this.listRequest) this.expenses.set(rows);
    } catch {
      if (request === this.listRequest) this.error.set('Não foi possível consultar as despesas.');
    } finally {
      if (request === this.listRequest) this.loading.set(false);
    }
  }

  async save(): Promise<void> {
    const company = this.workspaces.selected();
    if (!company || this.saving() || (!this.pending && this.form.invalid) || !this.workspaces.can('payables.manage')) return;
    const url = this.url(company);
    const value = this.form.getRawValue();
    const attempt = this.pending ?? {
      url, key: crypto.randomUUID(),
      body: {...value, amount: value.amount.replace(',', '.'), due_date: value.due_date || null,
        document_type: value.document_type || null, document_reference: value.document_reference.trim() || null},
    };
    if (attempt.url !== url) {
      this.error.set('Volte à empresa da despesa pendente para confirmar o envio.');
      return;
    }
    this.pending = attempt;
    this.saving.set(true);
    this.error.set('');
    this.message.set('');
    try {
      const expense = await firstValueFrom(this.http.post<Expense>(url, attempt.body, {
        headers: {'Idempotency-Key': attempt.key},
      }).pipe(timeout(15000)));
      this.pending = null;
      if (this.workspaces.selected()?.company_id === company.company_id) {
        this.form.reset({issue_date: today()});
        this.message.set(expense.payable_id ? 'Despesa salva e título gerado em Contas a pagar.' : 'Despesa salva.');
        if (this.workspaces.can('payables.read')) await this.load(url);
      }
    } catch (failure: unknown) {
      const status = (failure as {status?: number})?.status;
      if (status && status >= 400 && status < 500) this.pending = null;
      this.error.set(this.pending ? 'Envio sem confirmação. Tente novamente.' : 'Confira os dados e tente salvar novamente.');
    } finally {
      this.saving.set(false);
    }
  }
}
