import { HttpClient } from '@angular/common/http';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { FinanceApi, dateLabel, money, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';

interface BillingRow {
  id: string;
  customer: string;
  service: string;
  competence: string;
  amount: string;
  due_date: string | null;
  invoice_reference: string | null;
}

interface Customer {id: string; name: string}
interface Receipt {id: string; amount: string; received_on: string; reversed: boolean}
interface Position {received: string; outstanding: string; receipts: Receipt[]}

@Component({
  selector: 'sdf-billing',
  imports: [ReactiveFormsModule],
  styles: `
    .billing-nav { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
    .billing-nav [aria-pressed="true"] { background: #e2edf9; color: #173762; }
    fieldset { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr)); gap: 1rem; }
    label { display: grid; gap: .4rem; margin: 0; min-width: 0; }
    input, select { width: 100%; min-width: 0; }
    .billing-actions { display: flex; justify-content: flex-end; margin-top: 1rem; }
    .billing-actions button { background: linear-gradient(115deg, #173762, #27548d); }
  `,
  template: `
    <div class="page-heading"><div><span class="eyebrow">FINANCEIRO</span><h1>Faturamento de serviços</h1>
      <p class="muted">Registre serviços faturados e acompanhe as cobranças da empresa selecionada.</p></div></div>
    @if (error()) { <p class="alert" role="alert">{{error()}}</p> }
    @if (message()) { <p class="notice" role="status">{{message()}}</p> }
    @if (loading()) { <p role="status">Consultando faturamento…</p> }
    @if (available()) {
      <nav class="billing-nav" aria-label="Seções de faturamento">
        <button class="secondary" [disabled]="receiptBusy() || !!receiptKey" [attr.aria-pressed]="view() === 'register'" (click)="selected.set(null); view.set('register')">Novo faturamento</button>
        <button class="secondary" [disabled]="receiptBusy() || !!receiptKey" [attr.aria-pressed]="view() === 'billing'" (click)="selected.set(null); view.set('billing')">Faturamento registrado</button>
        <button class="secondary" [disabled]="receiptBusy() || !!receiptKey" [attr.aria-pressed]="view() === 'receivables'" (click)="selected.set(null); view.set('receivables')">Contas a receber</button>
        <button class="secondary" [disabled]="receiptBusy() || !!receiptKey || !!pending || customerSaving()"
          [attr.aria-pressed]="view() === 'customers'" (click)="selected.set(null); view.set('customers')">Clientes</button>
      </nav>
      @if (selected(); as row) {
        <section class="panel detail-panel register-list">
          <div class="panel-heading">
            <div><h2>{{row.customer}}</h2><p class="muted">{{row.service}}</p></div>
            <button class="secondary" type="button" (click)="selected.set(null)" [disabled]="receiptBusy() || !!receiptKey">Voltar à lista</button>
          </div>
          @if (position(); as balance) {
            <div class="detail-summary">
              <div><span>Total da cobrança</span><strong>{{money(row.amount)}}</strong></div>
              <div><span>Recebido</span><strong>{{money(balance.received)}}</strong></div>
              <div><span>Saldo em aberto</span><strong>{{money(balance.outstanding)}}</strong></div>
            </div>
            @if (+balance.outstanding > 0 || receiptKey) {
              <h3>Registrar recebimento</h3>
              <form [formGroup]="receiptForm" (ngSubmit)="receive(row)">
                <fieldset [disabled]="receiptBusy() || !!receiptKey">
                  <label>Valor recebido (R$)<input formControlName="amount" inputmode="decimal" maxlength="19"></label>
                  <label>Data do recebimento<input type="date" formControlName="received_on"></label>
                </fieldset>
                <div class="billing-actions"><button class="primary" type="submit" [disabled]="receiptBusy() || receiptForm.invalid">
                  {{receiptKey ? 'Tentar novamente' : 'Confirmar recebimento'}}
                </button></div>
              </form>
            }
            <h3>Histórico de recebimentos</h3>
            @if (!balance.receipts.length) { <p class="muted">Nenhum recebimento registrado.</p> }
            @else {
              <div class="table-scroll"><table><thead><tr><th>Data</th><th>Valor</th><th>Situação</th><th>Ações</th></tr></thead>
                <tbody>@for (receipt of balance.receipts; track receipt.id) {
                  <tr><td>{{dateLabel(receipt.received_on)}}</td><td>{{money(receipt.amount)}}</td>
                    <td><span class="badge" [class.cancelled]="receipt.reversed">{{receipt.reversed ? 'Estornado' : 'Recebido'}}</span></td>
                    <td>@if (!receipt.reversed) {
                      <button class="secondary small danger-text" type="button" (click)="reverse(row, receipt)"
                        [disabled]="receiptBusy() || !!receiptKey">Estornar</button>
                    }</td></tr>
                }</tbody>
              </table></div>
            }
          } @else if (receiptBusy()) { <p role="status">Consultando cobrança…</p> }
        </section>
      } @else if (view() === 'customers') {
        <section class="panel detail-panel">
          <h2>Cadastrar cliente</h2>
          <form [formGroup]="customerForm" (ngSubmit)="saveCustomer()">
            <fieldset [disabled]="customerSaving() || !!customerPending">
              <label>Nome ou razão social<input formControlName="name" maxlength="150"></label>
            </fieldset>
            <div class="billing-actions"><button class="primary" type="submit"
              [disabled]="customerSaving() || customerForm.invalid">
              {{customerPending ? 'Tentar novamente' : 'Cadastrar cliente'}}
            </button></div>
          </form>
        </section>
        <section class="panel detail-panel register-list">
          <h2>Clientes cadastrados</h2>
          @if (!customers().length) { <p class="muted">Nenhum cliente cadastrado nesta empresa.</p> }
          @else {
            <div class="table-scroll"><table><thead><tr><th>Nome ou razão social</th></tr></thead>
              <tbody>@for (customer of customers(); track customer.id) { <tr><td>{{customer.name}}</td></tr> }</tbody>
            </table></div>
          }
        </section>
      } @else if (view() === 'register') {
        <section class="panel detail-panel"><h2>Novo faturamento</h2>
          <form [formGroup]="form" (ngSubmit)="save()">
            <fieldset [disabled]="saving() || !!pending">
              <label>Cliente<select formControlName="customer_id">
                <option value="">Selecione um cliente</option>
                @for (customer of customers(); track customer.id) {
                  <option [value]="customer.id">{{customer.name}}</option>
                }
              </select></label>
              <label>Serviço prestado<input formControlName="service" maxlength="250"></label>
              <label>Competência<input type="month" formControlName="competence"></label>
              <label>Emissão<input type="date" formControlName="issue_date"></label>
              <label>Valor bruto (R$)<input formControlName="amount" inputmode="decimal" maxlength="19"></label>
              <label>Vencimento (opcional)<input type="date" formControlName="due_date"></label>
              <label>Referência da nota fiscal (opcional)<input formControlName="invoice_reference" maxlength="80"></label>
            </fieldset>
            <p class="muted">Ao informar um vencimento, a cobrança aparece em Contas a receber.</p>
            <div class="billing-actions"><button class="primary" type="submit" [disabled]="saving() || (!pending && form.invalid)">
              {{pending ? 'Tentar novamente' : 'Registrar faturamento'}}
            </button></div>
          </form>
        </section>
      } @else {
        <section class="panel detail-panel register-list">
          <h2>{{view() === 'billing' ? 'Faturamento registrado' : 'Contas a receber'}}</h2>
          @if (!visibleRows().length) { <p class="muted">Nenhum registro para exibir.</p> }
          @else {
            <div class="table-scroll"><table><thead><tr>
              <th>Cliente</th><th>Serviço</th><th>Competência</th><th>Nota fiscal</th><th>Vencimento</th><th class="numeric">Valor</th>@if (view() === 'receivables') { <th>Ações</th> }
            </tr></thead><tbody>
              @for (row of visibleRows(); track row.id) {
                <tr><td>{{row.customer}}</td><td>{{row.service}}</td><td>{{row.competence.slice(0,7)}}</td>
                  <td>{{row.invoice_reference || '—'}}</td><td>{{row.due_date ? dateLabel(row.due_date) : '—'}}</td>
                  <td class="numeric">{{money(row.amount)}}</td>
                  @if (view() === 'receivables') {
                    <td><button class="secondary small" type="button" (click)="openReceipt(row)">Ver cobrança</button></td>
                  }</tr>
              }
            </tbody></table></div>
          }
        </section>
      }
    }
  `,
})
export class Billing {
  private readonly http = inject(HttpClient);
  private readonly workspaces = inject(Workspaces);
  private readonly api = inject(FinanceApi);
  readonly dateLabel = dateLabel;
  readonly money = money;
  readonly view = signal<'register' | 'billing' | 'receivables' | 'customers'>('billing');
  readonly available = signal(false);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly customers = signal<Customer[]>([]);
  readonly customerSaving = signal(false);
  customerPending: {url: string; key: string; name: string} | null = null;
  readonly customerForm = inject(FormBuilder).nonNullable.group({name: ['', Validators.required]});
  private readonly billings = signal<BillingRow[]>([]);
  private readonly receivables = signal<BillingRow[]>([]);
  readonly visibleRows = computed(() => this.view() === 'receivables' ? this.receivables() : this.billings());
  private readonly url = computed(() => {
    const company = this.workspaces.selected();
    return company ? this.api.base(company).replace(/payables$/, 'billing') : null;
  });
  private generation = 0;
  pending: {url: string; key: string; body: object} | null = null;

  readonly selected = signal<BillingRow | null>(null);
  readonly position = signal<Position | null>(null);
  readonly receiptBusy = signal(false);
  receiptKey: string | null = null;
  readonly receiptForm = inject(FormBuilder).nonNullable.group({
    amount: ['', [Validators.required, Validators.pattern(/^(?:0|[1-9]\d*)(?:[.,]\d{1,2})?$/)]],
    received_on: [today(), Validators.required],
  });

  readonly form = inject(FormBuilder).nonNullable.group({
    customer_id: ['', Validators.required], service: ['', Validators.required],
    competence: [today().slice(0, 7), Validators.required], issue_date: [today(), Validators.required],
    amount: ['', [Validators.required, Validators.pattern(/^(?:0|[1-9]\d*)(?:[.,]\d{1,2})?$/)]],
    due_date: [''], invoice_reference: [''],
  });

  constructor() {
    effect(() => {
      const url = this.url();
      const generation = ++this.generation;
      this.selected.set(null);
      this.position.set(null);
      this.receiptKey = null;
      this.customers.set([]);
      if (!this.customerPending) this.customerForm.reset();
      this.available.set(false);
      this.error.set('');
      this.message.set('');
      this.billings.set([]);
      this.receivables.set([]);
      if (!this.pending) this.resetForm();
      if (url) void this.load(url, generation);
    });
  }

  private resetForm(): void {
    this.form.reset({issue_date: today(), competence: today().slice(0, 7)});
  }

  private async load(url: string, generation: number): Promise<void> {
    this.loading.set(true);
    try {
      const [billings, receivables, customers] = await Promise.all([
        firstValueFrom(this.http.get<BillingRow[]>(url).pipe(timeout(15000))),
        firstValueFrom(this.http.get<BillingRow[]>(url, {params: {receivables: 'true'}}).pipe(timeout(15000))),
        firstValueFrom(this.http.get<Customer[]>(url.replace(/billing$/, 'customers')).pipe(timeout(15000))),
      ]);
      if (generation === this.generation) {
        this.customers.set(customers);
        this.billings.set(billings);
        this.receivables.set(receivables);
        this.available.set(true);
      }
    } catch {
      if (generation === this.generation) this.error.set('Não foi possível consultar o faturamento desta empresa.');
    } finally {
      if (generation === this.generation) this.loading.set(false);
    }
  }

  async openReceipt(row: BillingRow): Promise<void> {
    const url = this.url();
    if (!url || this.receiptBusy()) return;
    this.selected.set(row);
    this.position.set(null);
    this.receiptForm.reset({received_on: today()});
    await this.receiptOperation(row, url);
  }

  async receive(row: BillingRow): Promise<void> {
    const url = this.url();
    if (!url || this.receiptBusy() || this.receiptForm.invalid) return;
    const {amount, received_on} = this.receiptForm.getRawValue();
    const key = this.receiptKey ?? crypto.randomUUID();
    this.receiptKey = key;
    await this.receiptOperation(row, url, async path => {
      await firstValueFrom(this.http.post(path + '/receipts', {amount: amount.replace(',', '.'), received_on},
        {headers: {'Idempotency-Key': key}}).pipe(timeout(15000)));
      this.receiptKey = null;
      this.receiptForm.reset({received_on: today()});
    });
  }

  async reverse(row: BillingRow, receipt: Receipt): Promise<void> {
    const url = this.url();
    if (!url || this.receiptBusy() || !confirm('Estornar este recebimento? O valor voltará ao saldo em aberto.')) return;
    await this.receiptOperation(row, url, async path => {
      await firstValueFrom(this.http.post(path + '/receipts/' + receipt.id + '/reverse', {}).pipe(timeout(15000)));
    });
  }

  private async receiptOperation(row: BillingRow, url: string, write?: (path: string) => Promise<void>): Promise<void> {
    const generation = this.generation, path = url + '/' + row.id;
    this.receiptBusy.set(true);
    this.error.set('');
    this.message.set('');
    try {
      if (write) await write(path);
      if (generation !== this.generation) return;
      const balance = await firstValueFrom(this.http.get<Position>(path + '/position').pipe(timeout(15000)));
      if (generation === this.generation) {
        this.position.set(balance);
        if (write) this.message.set('Movimentação registrada.');
      }
    } catch (failure) {
      if (generation === this.generation) {
        const status = (failure as {status?: number})?.status;
        if (status && status >= 400 && status < 500) this.receiptKey = null;
        this.error.set(status === 409 ? 'O valor excede o saldo ou a cobrança foi alterada.'
          : this.receiptKey ? 'Envio sem confirmação. Tente novamente.'
          : 'Não foi possível concluir a consulta ou confirmar a movimentação.');
      }
    } finally {
      this.receiptBusy.set(false);
    }
  }

  async saveCustomer(): Promise<void> {
    const base = this.url(), generation = this.generation;
    const name = this.customerForm.getRawValue().name.trim();
    if (!base || !name || !this.available() || this.customerSaving()) return;
    const url = base.replace(/billing$/, 'customers');
    const attempt = this.customerPending ?? {url, key: crypto.randomUUID(), name};
    if (attempt.url !== url) {
      this.error.set('Volte à empresa original para confirmar o cadastro pendente.');
      return;
    }
    this.customerPending = attempt;
    this.customerSaving.set(true);
    this.error.set('');
    this.message.set('');
    try {
      await firstValueFrom(this.http.post<Customer>(url, {name: attempt.name}, {
        headers: {'Idempotency-Key': attempt.key},
      }).pipe(timeout(15000)));
      this.customerPending = null;
      this.customerForm.reset();
      if (generation === this.generation) {
        this.message.set('Cliente cadastrado.');
        await this.load(base, generation);
      }
    } catch (failure) {
      const status = (failure as {status?: number})?.status;
      if (status && status >= 400 && status < 500) this.customerPending = null;
      if (generation === this.generation) this.error.set(this.customerPending
        ? 'Envio sem confirmação. Tente novamente.' : 'Não foi possível cadastrar o cliente.');
    } finally {
      this.customerSaving.set(false);
    }
  }

  async save(): Promise<void> {
    const url = this.url(), generation = this.generation;
    if (!url || !this.available() || this.saving() || (!this.pending && this.form.invalid)) return;
    if (this.pending && this.pending.url !== url) {
      this.error.set('Volte à empresa original para confirmar o lançamento pendente.');
      return;
    }
    const value = this.form.getRawValue();
    const attempt = this.pending ?? {url, key: crypto.randomUUID(), body: {
      ...value, competence: value.competence + '-01', amount: value.amount.replace(',', '.'),
      due_date: value.due_date || null, invoice_reference: value.invoice_reference.trim() || null,
    }};
    this.pending = attempt;
    this.saving.set(true);
    this.error.set('');
    this.message.set('');
    try {
      const row = await firstValueFrom(this.http.post<BillingRow>(url, attempt.body, {
        headers: {'Idempotency-Key': attempt.key},
      }).pipe(timeout(15000)));
      this.pending = null;
      this.resetForm();
      if (generation === this.generation) {
        this.view.set(row.due_date ? 'receivables' : 'billing');
        this.message.set('Faturamento registrado.');
        await this.load(url, generation);
      }
    } catch (failure) {
      const status = (failure as {status?: number})?.status;
      if (status && status >= 400 && status < 500) this.pending = null;
      if (generation === this.generation) {
        this.error.set(this.pending ? 'Envio sem confirmação. Tente novamente.' : 'Confira os dados e tente registrar novamente.');
      }
    } finally {
      this.saving.set(false);
    }
  }
}
