import { ContextHelp } from '../../core/context-help';
import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom, timeout } from 'rxjs';
import { FinanceApi, dateLabel, money, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';

const categories = [
  ['INTERNET', 'Internet'], ['ENERGIA', 'Luz'], ['AGUA', 'Água'], ['ESGOTO', 'Esgoto'],
  ['ALUGUEL', 'Aluguel'], ['ASSINATURA', 'Assinaturas'], ['OUTROS', 'Outras despesas'],
];

interface ExpenseRule {
  supplier_id: string;
  cancelled: boolean;
  id: string;
  description: string;
  category: string;
  due_day: number;
  fixed_amount: string | null;
}

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
  imports: [ReactiveFormsModule, RouterLink, ContextHelp],
  styles: `
    .panel-heading { justify-content: flex-start; align-items: center; flex-wrap: wrap; gap: .75rem 1.25rem; }
    .panel-heading p { margin: .35rem 0 0; }
    fieldset { border: 0; padding: 0; margin: 1.5rem 0 0; min-inline-size: 0; }
    legend { padding: 0; margin-bottom: .75rem; font-weight: 650; }
    .expense-grid, .supplier-editor { display: grid; gap: .85rem 1rem; }
    .expense-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .financial-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .full { grid-column: 1 / -1; }
    label { display: grid; align-content: start; gap: .4rem; min-width: 0; margin: 0; }
    input, select { width: 100%; min-width: 0; min-height: 2.75rem; box-sizing: border-box; }
    select {
      appearance: none;
      padding-inline-end: 2.5rem;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='m4 6 4 4 4-4' fill='none' stroke='%23465870' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right .875rem center;
      background-size: 1rem;
    }
    @media (forced-colors: active) {
      select { appearance: auto; background-image: none; }
    }
    .supplier-editor {
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: end;
      max-inline-size: 32rem;
      padding: 1rem;
      background: #f6f8fb;
      border: 1px solid #e1e7ef;
      border-radius: .5rem;
    }
    :host {
      display: block;
      background: linear-gradient(145deg, #edf3fa, #f7f9fc 65%, #eef3f8);
      padding: clamp(.75rem, 2vw, 1.5rem);
      border-radius: .75rem;
    }
    .expense-tabs { display: flex; flex-wrap: wrap; gap: .35rem; margin-bottom: 1rem; }
    .expense-tabs button { padding: .65rem .9rem; border-radius: .5rem; background: transparent; color: #294665; }
    .expense-tabs button[aria-pressed="true"] { background: #dce8f6; color: #173762; font-weight: 650; }
    .expense-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 1rem;
      align-items: start;
    }
    .expense-preview { background: linear-gradient(145deg, #fff, #f0f5fb); }
    .expense-preview p { margin-bottom: .5rem; }
    @media (min-width: 1100px) {
      .expense-layout { grid-template-columns: minmax(0, 1fr) minmax(13rem, 19rem); }
    }
    .expense-entry button { border-radius: .5rem; }
    .expense-entry .primary {
      background: linear-gradient(115deg, #173762, #27548d);
      border: 1px solid #244a7b;
      box-shadow: 0 2px 4px #1737621a;
    }
    .expense-entry .primary:hover:not(:disabled) {
      background: linear-gradient(115deg, #122e53, #204878);
    }
    .expense-entry .primary:disabled {
      background: #e8edf4;
      border-color: #d9e2ee;
      color: #546680;
      box-shadow: none;
      opacity: 1;
    }
    .expense-entry .secondary, .expense-entry .icon-button {
      background: linear-gradient(180deg, #fff, #f4f7fb);
      border-color: #d6e0ed;
      color: #294665;
    }
    .expense-entry .secondary:hover, .expense-entry .icon-button:hover {
      background: #eaf0f8;
      border-color: #b9cbe1;
    }
    fieldset + fieldset { padding-top: .25rem; }
    fieldset > p { margin: .75rem 0 0; }
    .supplier-editor .primary { min-height: 2.75rem; }
    .panel-heading button[hidden] { display: none; }
    .supplier-heading { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center; }
    .supplier-heading h3 { margin: 0; }
    .expense-actions {
      display: flex;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: .625rem;
      border-top: 1px solid #e1e7ef;
      margin-top: 1rem;
      padding-top: 1rem;
    }
    .expense-actions .secondary { background: transparent; border-color: #d6e0ed; }
    .expense-actions .secondary:hover { background: #edf3fa; }
    .expense-actions .primary { padding-inline: 1.25rem; }
    .document-field { position: relative; min-width: 0; }
    .field-caption { display: flex; align-items: center; gap: .4rem; margin-bottom: .4rem; }
    .linked-expense td { background: #eaf1fa; }
    td small { display: block; margin-top: .25rem; }
    @media (max-width: 640px) {
      .expense-grid, .financial-fields, .supplier-editor { grid-template-columns: minmax(0, 1fr); }
      .expense-actions button { flex: 1 1 9rem; }
    }
  `,
  template: `
    <div class="page-heading"><div><span class="eyebrow">FINANCEIRO</span><h1>Despesas</h1>
      <p class="muted">Classifique os gastos da empresa e vincule os documentos de origem.</p></div></div>


    @if (!editingRule()) {
    <nav class="expense-tabs" aria-label="Seções de despesas">
      @if (workspaces.can('payables.manage')) {
        <button type="button" [attr.aria-pressed]="activeSection() === 'create'" (click)="editingRule() ? leaveRuleEdit() : null; section.set('create')">Nova despesa</button>
      }
      @if (workspaces.can('payables.read')) {
        <button type="button" [attr.aria-pressed]="activeSection() === 'expenses'" (click)="section.set('expenses')">Despesas registradas</button>
        <button type="button" [attr.aria-pressed]="activeSection() === 'rules'" (click)="section.set('rules')">Recorrências</button>
      }
    </nav>
    }
    @if (workspaces.can('payables.manage') && activeSection() === 'create') {
      <div class="expense-layout">
      <section class="panel detail-panel expense-entry">
        <div class="panel-heading">
          <div><h2>{{editingRule() ? 'Editar recorrência' : 'Nova despesa'}}</h2><p class="muted">Informe a origem e os dados financeiros do lançamento.</p></div>
          <button [hidden]="showSupplier()" class="secondary" type="button" (click)="showSupplier.set(true)"
            [attr.aria-expanded]="showSupplier()" aria-controls="supplier-editor">
            Cadastrar fornecedor
          </button>
        </div>
        <div id="supplier-editor" [hidden]="!showSupplier()">
          <form class="supplier-editor" [formGroup]="supplierForm" (ngSubmit)="createSupplier()">
            <div class="supplier-heading"><h3>Novo fornecedor</h3><button class="icon-button" type="button" (click)="showSupplier.set(false)" aria-label="Fechar cadastro de fornecedor">×</button></div>
            <label>Nome do fornecedor<input formControlName="name" maxlength="150"></label>
            <button class="primary" type="submit" [disabled]="supplierForm.invalid || savingSupplier()">
              Salvar fornecedor
            </button>
          </form>
        </div>
        <form [formGroup]="form" (ngSubmit)="save()">
          <fieldset [disabled]="saving() || pending !== null">
            <legend>Identificação</legend>
            <div class="expense-grid">
              <label class="full">Descrição<input formControlName="description" maxlength="300" placeholder="Ex.: Licença do software contábil — novembro"></label>
              <label>Categoria<select formControlName="category">
                <option value="">Selecione</option>
                @for (category of categories; track category[0]) {
                  <option [value]="category[0]">{{category[1]}}</option>
                }
              </select></label>
              <label>Fornecedor<select formControlName="supplier_id">
                <option value="">Selecione um fornecedor</option>
                @for (supplier of suppliers(); track supplier.id) {
                  <option [value]="supplier.id">{{supplier.name}}</option>
                }
              </select></label>
            </div>
          </fieldset>
          <fieldset [disabled]="saving() || pending !== null">
            <legend>Frequência</legend>
            <label>Tipo de lançamento<select formControlName="frequency">
              @if (!editingRule()) { <option value="once">Despesa avulsa</option> }
              <option value="fixed">Mensal com valor fixo</option>
              <option value="variable">Mensal com valor variável</option>
            </select></label>
          </fieldset>
          @if (!recurring()) {
          <fieldset [disabled]="saving() || pending !== null">
            <legend>Comprovante (opcional)</legend>
            <div class="expense-grid">
              <label>Tipo de documento<select formControlName="document_type">
                <option value="">Sem documento</option><option value="BOLETO">Boleto</option>
                <option value="NOTA_FISCAL">Nota fiscal</option><option value="OUTRO">Outro documento</option>
              </select></label>
              <div class="document-field">
                <div class="field-caption">
                  <label for="document-reference">Referência do documento</label>
                  <sdf-help label="Ajuda sobre referência do documento"
                    text="Informe o número da nota fiscal, do boleto, da fatura ou do recibo. Se não houver documento, deixe em branco." />
                </div>
                <input id="document-reference" formControlName="document_reference" maxlength="100" placeholder="Ex.: número da nota ou fatura">
              </div>
            </div>
          </fieldset>
          }
          @if (recurring()) {
          <fieldset [disabled]="saving() || pending !== null">
            <legend>Condições mensais</legend>
            <div class="expense-grid">
              <label>Dia do vencimento<select formControlName="due_day">
                @for (day of ['05', '10', '15', '20', '25', '30']; track day) {
                  <option [value]="day">Todo dia {{day}}</option>
                }
              </select></label>
              @if (form.controls.frequency.value === 'fixed') {
                <label>Valor mensal (R$)<input formControlName="amount" inputmode="decimal" maxlength="19"></label>
              }
            </div>
            <p class="muted">O cadastro salva a recorrência. A geração mensal ainda não está ativa.</p>
          </fieldset>
          } @else {
          <fieldset [disabled]="saving() || pending !== null">
            <legend>Valores e datas</legend>
            <div class="expense-grid financial-fields">
              <label>Valor (R$)<input formControlName="amount" inputmode="decimal" maxlength="19" placeholder="0,00"></label>
              <label>Emissão<input type="date" formControlName="issue_date"></label>
              <label>Vencimento (opcional)<input type="date" formControlName="due_date"></label>
            </div>
            <p class="muted">Preencha o vencimento para gerar uma obrigação em Contas a pagar.</p>
          </fieldset>
          }
          @if (message()) { <p class="notice" role="status">{{message()}}</p> }
          @if (error()) { <p class="alert" role="alert">{{error()}}</p> }
          <div class="expense-actions">
            @if (editingRule()) { <button class="secondary" type="button" (click)="leaveRuleEdit()" [disabled]="saving()">Voltar</button> }
            <button class="primary" type="submit" [disabled]="saving() || (!pending && !canSave())">
            {{saving() ? 'Salvando…' : pending ? 'Tentar novamente' : editingRule() ? 'Salvar alterações' : 'Registrar operação'}}
          </button></div>
        </form>
      </section>
      <aside class="panel detail-panel expense-preview" aria-labelledby="expense-preview-title">
        <h2 id="expense-preview-title">Resumo do lançamento</h2>
        <p><strong>Categoria</strong><br>{{form.controls.category.value ? label(form.controls.category.value) : 'A selecionar'}}</p>
        <p><strong>Vencimento</strong><br>{{form.controls.due_date.value ? dateLabel(form.controls.due_date.value) : 'Sem vencimento'}}</p>
        <p class="muted">{{form.controls.due_date.value
          ? 'Ao salvar, será gerado um título em Contas a pagar.'
          : 'Sem vencimento, será registrada somente a despesa.'}}</p>
      </aside>
      </div>
    }
    @if (workspaces.can('payables.read') && activeSection() === 'rules') {
      <section class="panel detail-panel register-list">
        <h2>Recorrências cadastradas</h2>
        @if (message()) { <p role="status">{{message()}}</p> }
        @if (ruleActionError()) { <p role="alert">{{ruleActionError()}}</p> }
        @if (rulesError()) { <p role="alert">{{rulesError()}}</p> }
        @else if (loading()) { <p role="status">Carregando recorrências…</p> }
        @else if (!rules().length) { <p class="muted">Nenhuma recorrência cadastrada nesta empresa.</p> }
        @else {
          <div class="table-scroll"><table>
            <thead><tr><th>Descrição</th><th>Categoria</th><th>Vencimento mensal</th><th class="numeric">Valor</th><th>Situação</th><th>Ações</th></tr></thead>
            <tbody>@for (rule of rules(); track rule.id) {
              <tr><td>{{rule.description}}</td><td>{{label(rule.category)}}</td>
                <td>Dia {{rule.due_day}}</td>
                <td class="numeric">{{rule.fixed_amount === null ? 'Variável' : money(rule.fixed_amount)}}</td>
                <td>{{rule.cancelled ? 'Cancelada' : 'Ativa'}}</td>
                <td>@if (!rule.cancelled && workspaces.can('payables.manage')) {
                  <button class="text-button" type="button" (click)="editRule(rule)" [disabled]="saving() || !!pending">Editar</button>
                  <button class="text-button danger-text" type="button" (click)="cancelRule(rule)" [disabled]="saving()">Cancelar</button>
                }</td></tr>
            }</tbody>
          </table></div>
        }
      </section>
    }
    @if (workspaces.can('payables.read') && activeSection() === 'expenses') {
      <section class="panel detail-panel register-list">
        <h2>{{selectedExpense ? 'Despesa vinculada' : 'Despesas registradas'}}</h2>
        @if (selectedExpense) { <p><a class="secondary small" routerLink="." [queryParams]="{view:'registered'}">Ver todas as despesas</a></p> }
        @if (error()) { <p role="alert">{{error()}}</p> }
        @if (loading()) { <p>Carregando despesas…</p> }
        @else if (expenses().length === 0) { <p class="muted">Nenhuma despesa para exibir.</p> }
        @else {
          <div class="table-scroll">
            <table>
              <thead><tr><th>Despesa</th><th>Categoria</th><th>Fornecedor e documento</th><th class="numeric">Valor</th><th>Vencimento</th></tr></thead>
              <tbody>@for (expense of expenses(); track expense.id) {
                <tr [class.linked-expense]="expense.id === selectedExpense"><td>{{expense.description}}</td><td>{{label(expense.category)}}</td>
                  <td>{{expense.supplier}} @if (expense.document_type) {
                    <small>{{documentLabel(expense.document_type)}} {{expense.document_reference}}</small>
                  }</td>
                  <td class="numeric">{{money(expense.amount)}}</td>
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
  private readonly route = inject(ActivatedRoute);
  selectedExpense = this.route.snapshot.queryParamMap.get('expense');
  readonly section = signal<'create' | 'expenses' | 'rules'>(
    this.route.snapshot.queryParamMap.get('view') === 'registered' ? 'expenses' : 'create',
  );

  activeSection(): 'create' | 'expenses' | 'rules' {
    return this.section() === 'create' && !this.workspaces.can('payables.manage') ? 'expenses' : this.section();
  }

  readonly editingRule = signal<ExpenseRule | null>(null);
  readonly ruleActionError = signal('');
  readonly rules = signal<ExpenseRule[]>([]);
  readonly rulesError = signal('');
  readonly expenses = signal<Expense[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly message = signal('');
  readonly error = signal('');
  private listRequest = 0;
  pending: {url: string; key: string; body: unknown} | null = null;

  readonly showSupplier = signal(false);
  readonly suppliers = signal<{id: string; name: string}[]>([]);
  readonly savingSupplier = signal(false);
  readonly supplierForm = inject(FormBuilder).nonNullable.group({name: ['', Validators.required]});
  private supplierRequest = 0;

  readonly form = inject(FormBuilder).nonNullable.group({
    description: ['', Validators.required],
    category: ['', Validators.required],
    supplier_id: ['', Validators.required],
    document_type: [''],
    document_reference: [''],
    frequency: ['once'],
    due_day: ['05'],
    amount: ['', [Validators.pattern(/^(?:0|[1-9]\d*)(?:[.,]\d{1,2})?$/)]],
    issue_date: [today(), Validators.required],
    due_date: [''],
  });

  constructor() {
    this.route.queryParamMap.subscribe(params => {
      const next = params.get('expense');
      if (next === this.selectedExpense) return;
      this.selectedExpense = next;
      const company = this.workspaces.selected();
      if (company && this.workspaces.can('payables.read')) void this.load(this.url(company));
    });
    effect(() => {
      const company = this.workspaces.selected();
      untracked(() => {
        this.form.reset({issue_date: today()});
        this.editingRule.set(null);
        this.ruleActionError.set('');
        this.supplierForm.reset();
        this.showSupplier.set(false);
        this.suppliers.set([]);
        void this.loadSuppliers(company && this.workspaces.can('payables.manage') ? this.supplierUrl(company) : null);
        this.error.set('');
        this.message.set('');
        void this.load(company && this.workspaces.can('payables.read') ? this.url(company) : null);
      });
    });
  }

  private url(company: NonNullable<ReturnType<Workspaces['selected']>>): string {
    return this.api.base(company).replace(/\/payables$/, '/expenses');
  }

  private supplierUrl(company: NonNullable<ReturnType<Workspaces['selected']>>): string {
    return this.api.base(company).replace(/\/payables$/, '/suppliers');
  }

  private async loadSuppliers(url: string | null): Promise<void> {
    const request = ++this.supplierRequest;
    if (!url) return;
    try {
      const suppliers = await firstValueFrom(this.http.get<{id: string; name: string}[]>(url).pipe(timeout(15000)));
      if (request === this.supplierRequest) this.suppliers.set(suppliers);
    } catch {
      if (request === this.supplierRequest) this.error.set('Não foi possível consultar os fornecedores.');
    }
  }

  async createSupplier(): Promise<void> {
    const company = this.workspaces.selected();
    const name = this.supplierForm.getRawValue().name.trim();
    if (!company || !name || this.savingSupplier() || !this.workspaces.can('payables.manage')) return;
    const url = this.supplierUrl(company);
    this.savingSupplier.set(true);
    this.error.set('');
    try {
      const supplier = await firstValueFrom(this.http.post<{id: string; name: string}>(url, {name}).pipe(timeout(15000)));
      if (this.workspaces.selected()?.company_id === company.company_id) {
        this.supplierForm.reset();
        this.showSupplier.set(false);
        this.form.controls.supplier_id.setValue(supplier.id);
        await this.loadSuppliers(url);
      }
    } catch {
      if (this.workspaces.selected()?.company_id === company.company_id) {
        this.error.set('Não foi possível cadastrar o fornecedor.');
      }
    } finally {
      this.savingSupplier.set(false);
    }
  }

  label(category: string): string {
    if (category === 'PESSOAL') return 'Pessoal (histórico)';
    return categories.find(([key]) => key === category)?.[1] ?? category;
  }

  documentLabel(type: string): string {
    return type === 'NOTA_FISCAL' ? 'Nota fiscal' : type === 'BOLETO' ? 'Boleto' : 'Outro documento';
  }

  private async load(url: string | null): Promise<void> {
    const request = ++this.listRequest;
    this.expenses.set([]);
    this.rules.set([]);
    this.rulesError.set('');
    this.loading.set(url !== null);
    if (!url) return;
    try {
      await Promise.all([
        firstValueFrom(this.http.get<Expense[]>(url, this.selectedExpense ? {params: {expense_id: this.selectedExpense}} : {}).pipe(timeout(15000))).then(rows => {
          if (request === this.listRequest) this.expenses.set(rows);
        }).catch(() => {
          if (request === this.listRequest) this.error.set('Não foi possível consultar as despesas.');
        }),
        firstValueFrom(this.http.get<ExpenseRule[]>(url + '/rules').pipe(timeout(15000))).then(rows => {
          if (request === this.listRequest) this.rules.set(rows);
        }).catch(() => {
          if (request === this.listRequest) this.rulesError.set('Não foi possível consultar as recorrências.');
        }),
      ]);
    } finally {
      if (request === this.listRequest) this.loading.set(false);
    }
  }

  editRule(rule: ExpenseRule): void {
    this.editingRule.set(rule);
    this.error.set('');
    this.message.set('');
    this.form.reset({
      description: rule.description, category: rule.category, supplier_id: rule.supplier_id,
      frequency: rule.fixed_amount === null ? 'variable' : 'fixed',
      due_day: String(rule.due_day).padStart(2, '0'), amount: rule.fixed_amount ?? '',
    });
    this.section.set('create');
  }

  leaveRuleEdit(): void {
    this.editingRule.set(null);
    this.pending = null;
    this.form.reset({issue_date: today()});
    this.section.set('rules');
  }

  async cancelRule(rule: ExpenseRule): Promise<void> {
    const company = this.workspaces.selected();
    if (!company || this.saving() || !this.workspaces.can('payables.manage')
      || !confirm('Cancelar esta recorrência? O registro ficará no histórico.')) return;
    const base = this.url(company);
    this.saving.set(true);
    this.ruleActionError.set('');
    this.message.set('');
    try {
      await firstValueFrom(this.http.post(base + '/rules/' + rule.id + '/cancel', {}).pipe(timeout(15000)));
      if (this.workspaces.selected() === company) {
        this.message.set('Recorrência cancelada.');
        await this.load(base);
      }
    } catch {
      if (this.workspaces.selected() === company) this.ruleActionError.set('Não foi possível confirmar o cancelamento.');
    } finally {
      this.saving.set(false);
    }
  }

  recurring(): boolean {
    return this.form.controls.frequency.value !== 'once';
  }

  canSave(): boolean {
    const {description, category, supplier_id, frequency, amount, issue_date} = this.form.getRawValue();
    return !!(description.trim() && category && category !== 'PESSOAL' && supplier_id
      && (frequency === 'variable' || (amount && this.form.controls.amount.valid))
      && (frequency !== 'once' || issue_date));
  }

  async save(): Promise<void> {
    const company = this.workspaces.selected();
    if (!company || this.saving() || (!this.pending && !this.canSave()) || !this.workspaces.can('payables.manage')) return;
    const base = this.url(company);
    const {frequency, due_day, ...value} = this.form.getRawValue();
    const amount = value.amount.replace(',', '.');
    const editing = this.editingRule();
    if (editing) {
      this.saving.set(true);
      this.error.set('');
      try {
        await firstValueFrom(this.http.put(base + '/rules/' + editing.id, {
          description: value.description, category: value.category, supplier_id: value.supplier_id,
          due_day: Number(due_day), fixed_amount: frequency === 'fixed' ? amount : null,
        }).pipe(timeout(15000)));
        if (this.workspaces.selected() === company) {
          this.leaveRuleEdit();
          this.message.set('Recorrência atualizada.');
          await this.load(base);
        }
      } catch {
        if (this.workspaces.selected() === company) this.error.set('Não foi possível confirmar a alteração.');
      } finally {
        this.saving.set(false);
      }
      return;
    }
    const attempt = this.pending ?? {
      url: frequency === 'once' ? base : base + '/rules', key: crypto.randomUUID(),
      body: frequency === 'once' ? {...value, amount, due_date: value.due_date || null,
        document_type: value.document_type || null, document_reference: value.document_reference.trim() || null}
        : {description: value.description, category: value.category, supplier_id: value.supplier_id,
          due_day: Number(due_day), fixed_amount: frequency === 'fixed' ? amount : null},
    };
    if (attempt.url !== base && attempt.url !== base + '/rules') {
      this.error.set('Volte à empresa da despesa pendente para confirmar o envio.');
      return;
    }
    this.pending = attempt;
    this.saving.set(true);
    this.error.set('');
    this.message.set('');
    try {
      const expense = await firstValueFrom(this.http.post<Expense>(attempt.url, attempt.body, {
        headers: {'Idempotency-Key': attempt.key},
      }).pipe(timeout(15000)));
      this.pending = null;
      if (this.workspaces.selected()?.company_id === company.company_id) {
        this.form.reset({issue_date: today()});
        this.message.set(attempt.url !== base ? 'Recorrência salva.' : expense.payable_id ? 'Despesa salva e título gerado em Contas a pagar.' : 'Despesa salva.');
        if (this.workspaces.can('payables.read')) await this.load(base);
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
