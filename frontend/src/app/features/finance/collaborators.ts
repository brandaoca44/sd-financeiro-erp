import { BankSelector } from '../../core/bank-selector';
import { dateLabel, money } from '../../core/finance';
import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { Workspaces } from '../../core/workspaces';

interface Collaborator {
  id: string;
  name: string;
  job_title: string;
  employment_type: string | null;
  work_model: string | null;
  admission_date: string | null;
  termination_date: string | null;
  termination_reason: string | null;
}

@Component({
  selector: 'sdf-collaborators',
  imports: [ReactiveFormsModule, BankSelector],
  styles: `
    form { display: grid; gap: 1rem; max-inline-size: 66rem; }
    .profile-block {
      display: grid; gap: .85rem; padding: clamp(.85rem, 2vw, 1.25rem);
      border: 1px solid #dbe5f0; border-radius: .75rem;
      background: linear-gradient(145deg, #fff, #f7faff);
      min-inline-size: 0;
    }
    .profile-block h3 { margin: 0; color: #173762; }
    .details-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr)); gap: .85rem 1rem; }
    label { display: grid; align-content: start; gap: .35rem; margin: 0; min-inline-size: 0; }
    input, select { width: 100%; min-inline-size: 0; }
    summary { cursor: pointer; color: #173762; font-weight: 650; }
    details[open] > summary { margin-bottom: 1rem; }
    .private-section + .private-section { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #dbe5f0; }
    .address-grid { display: grid; grid-template-columns: minmax(0, 9rem) minmax(0, 1fr); gap: .85rem 1rem; }
    @media (max-width: 560px) { .address-grid { grid-template-columns: minmax(0, 1fr); } }
    .details-grid > * { min-width: 0; }
    .bank-field { grid-column: 1 / -1; display: grid; gap: .4rem; }
    .private-section h3 { margin-bottom: .75rem; }
    .form-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .625rem; }
    .form-actions .primary { background: linear-gradient(115deg, #173762, #27548d); }
    .form-actions .primary:hover:not(:disabled) { background: linear-gradient(115deg, #122e53, #204878); }
    .history-tabs { display: flex; flex-wrap: wrap; gap: .5rem; margin-block: .75rem 1rem; }
    .history-tabs button[aria-pressed="true"] { background: #e3edf9; color: #173762; }
    .row-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
    .termination-action { background: #fff4f4; border-color: #e5a6aa; color: #962832; }
    .termination-action:hover:not(:disabled) { background: #ffe7e8; border-color: #c85f68; }
    .termination-form { margin-block: 1rem; }
    .detail-panel + .detail-panel { margin-top: 1rem; }
  `,
  template: `
    <div class="page-heading"><div><span class="eyebrow">PESSOAS</span><h1>Colaboradores</h1>
      <p class="muted">Cadastro profissional da empresa selecionada.</p></div></div>
    @if (error()) { <p class="alert" role="alert">{{error()}}</p> }
    @if (loading()) { <p role="status">Consultando cadastro…</p> }
    @if (available()) {
      @if (creating() || editing()) {
      <section class="panel detail-panel">
        <h2>{{editing() ? 'Editar colaborador' : 'Novo colaborador'}}</h2>
        <form [formGroup]="form" (ngSubmit)="save()">
          <section class="profile-block" aria-label="Identificação profissional">
            <h3>Identificação profissional</h3>
            <div class="details-grid">
          <label>Nome completo<input formControlName="name" maxlength="150" [readOnly]="saving() || !!pending"></label>
          <label>Cargo ou profissão
            <select formControlName="job_title" [attr.inert]="saving() || pending ? '' : null">
              <option value="">Selecione um cargo</option>
              @for (group of jobGroups; track group.area) {
                <optgroup [label]="group.area">
                  @for (job of group.jobs; track job) { <option [value]="job">{{job}}</option> }
                </optgroup>
              }
              <option value="Outro cargo">Outro cargo</option>
            </select>
          </label>
            </div>
          </section>
          <section class="profile-block" aria-label="Vínculo profissional">
            <h3>Vínculo profissional</h3>
          <div class="details-grid">
            <label>Vínculo<select formControlName="employment_type">
              <option value="">Selecione</option>
              @for (type of ['CLT', 'PJ', 'ESTAGIO', 'TEMPORARIO', 'OUTRO']; track type) {
                <option [value]="type">{{type}}</option>
              }
            </select></label>
            <label>Modelo de trabalho<select formControlName="work_model">
              <option value="">Selecione</option>
              <option value="PRESENCIAL">Presencial</option><option value="HIBRIDO">Híbrido</option><option value="REMOTO">Remoto</option>
            </select></label>
            <label>Data de admissão<input type="date" formControlName="admission_date" [readOnly]="!!closedLink()"></label>
          </div>
          </section>
          <details class="profile-block" open>
            <summary>Dados pessoais, remuneração e pagamento</summary>
            <div formGroupName="details">
              <section class="private-section">
                <h3>Documentos e contato</h3>
                <div class="details-grid">
              @for (field of privateFields.slice(0, 7); track field.key) {
                <label>{{field.label}}{{requiredPrivate.has(field.key) ? ' (obrigatório)' : ''}}<input [required]="requiredPrivate.has(field.key)" [type]="field.type" [formControlName]="field.key" [maxLength]="field.max" [attr.inputmode]="numericFields.has(field.key) ? 'numeric' : null"
                  (input)="filterDigits(field.key, $event)" autocomplete="off"></label>
              }
                </div>
              </section>
              <section class="private-section">
                <h3>Endereço residencial</h3>
                <div class="address-grid">
                  <label>CEP<input formControlName="cep" maxlength="8" inputmode="numeric"
                    placeholder="8 dígitos" (input)="filterDigits('cep', $event)" autocomplete="off"></label>
                  <label>Endereço residencial completo<input formControlName="address" maxlength="250"
                    placeholder="Rua, número, complemento, bairro, cidade e UF" autocomplete="off"></label>
                </div>
              </section>
              <section class="private-section">
                <h3>Remuneração e dados bancários</h3>
                <div class="details-grid">
              @for (field of privateFields.slice(7); track field.key) {
                @if (field.key === 'bank') {
                  <div class="bank-field"><label id="collaborator-bank-label">Banco (obrigatório)</label>
                    <sdf-bank-selector formControlName="bank" aria-labelledby="collaborator-bank-label" />
                  </div>
                } @else {
                <label>{{field.label}}{{requiredPrivate.has(field.key) ? ' (obrigatório)' : ''}}<input [required]="requiredPrivate.has(field.key)" [type]="field.type" [formControlName]="field.key" [maxLength]="field.max" [attr.inputmode]="numericFields.has(field.key) ? 'numeric' : null"
                  (input)="filterDigits(field.key, $event)" autocomplete="off"></label>
                }
              }
              <label>Tipo de conta (obrigatório)<select formControlName="account_type" required>
                <option value="">Selecione</option>
                @for (type of ['CORRENTE', 'POUPANCA', 'SALARIO', 'PAGAMENTO']; track type) {
                  <option [value]="type">{{type}}</option>
                }
              </select></label>
                </div>
              </section>
              <section class="private-section">
                <h3>Chave Pix (opcional)</h3>
                <div class="details-grid">
                  <label>Tipo de chave<select formControlName="pix_type">
                    <option value="">Sem chave Pix</option>
                    <option value="CPF">CPF</option><option value="CNPJ">CNPJ</option>
                    <option value="EMAIL">E-mail</option><option value="PHONE">Telefone</option>
                    <option value="RANDOM">Chave aleatória</option>
                  </select></label>
                  <label>Chave Pix<input formControlName="pix_key" maxlength="254" autocomplete="off"></label>
                </div>
                <p class="field-help">Para telefone, informe +55, DDD e número. A chave fica vinculada a este cadastro.</p>
              </section>
            </div>
          </details>
          @if (editing() && form.controls.employment_type.value === 'CLT') {
            <div>
              <button class="secondary" type="button" (click)="previewPayroll()" [disabled]="saving()">Simular folha 2026</button>
              <p class="muted">Prévia de desenvolvimento com a remuneração salva, sem dependentes ou outras verbas.</p>
              @if (payroll(); as result) {
                <p role="status">Bruto {{money(result.gross)}} · INSS {{money(result.inss)}} ·
                  IRRF {{money(result.irrf)}} · Líquido estimado {{money(result.net)}}</p>
              }
            </div>
          }
          <div class="form-actions">
          <button class="secondary" type="button" (click)="reset()" [disabled]="saving() || !!pending">Voltar à lista</button>
          <button class="primary" type="submit" [disabled]="saving() || form.invalid">
            {{saving() ? 'Registrando…' : pending ? 'Tentar novamente' : editing() ? 'Salvar alterações' : 'Cadastrar colaborador'}}
          </button>
          </div>
        </form>
      </section>
      } @else if (terminating()) {
        @let person = terminating()!;
        <section class="panel detail-panel">
          <form class="profile-block termination-form" [formGroup]="terminationForm" (ngSubmit)="terminate(person)">
            <h3>Registrar desligamento de {{person.name}}</h3>
            <div class="details-grid">
              <label>Data do desligamento<input type="date" formControlName="date" [attr.min]="person.admission_date"></label>
              <label>Motivo<select formControlName="reason">
                <option value="">Selecione</option>
                @for (reason of reasons; track reason.key) { <option [value]="reason.key">{{reason.label}}</option> }
              </select></label>
            </div>
            <div class="form-actions">
              <button class="secondary" type="button" (click)="terminating.set(null)" [disabled]="saving()">Voltar</button>
              <button class="primary" type="submit" [disabled]="saving() || terminationForm.invalid">Confirmar desligamento</button>
            </div>
          </form>
        </section>
        }
      @else {
      <section class="panel detail-panel register-list" aria-labelledby="collaborator-list-title">
        <div class="panel-heading">
          <h2 id="collaborator-list-title">Colaboradores cadastrados</h2>
          <button class="primary" type="button" (click)="reset(); creating.set(true)">Novo colaborador</button>
        </div>
        @if (saved()) { <p class="notice" role="status">Dados do colaborador salvos.</p> }
        <nav class="history-tabs" aria-label="Situação dos colaboradores">
          <button class="secondary small" type="button" [attr.aria-pressed]="!history()" (click)="history.set(false)">Ativos</button>
          <button class="secondary small" type="button" [attr.aria-pressed]="history()" (click)="history.set(true)">Desligados</button>
        </nav>
        @if (!visibleRows().length) { <p class="muted">{{history() ? 'Nenhum desligamento registrado.' : 'Nenhum colaborador ativo.'}}</p> }
        @else {
          <div class="table-scroll"><table><thead><tr><th>Nome</th><th>Cargo</th><th>Admissão</th>
            @if (history()) { <th>Desligamento</th><th>Motivo</th><th>Tempo de vínculo</th> }
            <th>Ações</th></tr></thead>
            <tbody>@for (row of visibleRows(); track row.id) {
              <tr><td>{{row.name}}</td><td>{{row.job_title}}</td>
                <td>{{row.admission_date ? dateLabel(row.admission_date) : 'Não informada'}}</td>
                @if (row.termination_date) {
                  <td>{{dateLabel(row.termination_date)}}</td><td>{{reasonLabel(row.termination_reason)}}</td>
                  <td>{{duration(row)}}</td>
                }
                <td><div class="row-actions"><button class="secondary small" type="button" (click)="edit(row)" [disabled]="saving() || !!pending">Editar</button>
                  @if (!row.termination_date) {
                    <button class="secondary small termination-action" type="button" (click)="startTermination(row)" [disabled]="saving() || !!pending">Desligar</button>
                  }
                </div></td>
              </tr>
            }</tbody>
          </table></div>
        }
      </section>
      }
    }
  `,
})
export class Collaborators {
  private readonly http = inject(HttpClient);
  private readonly workspaces = inject(Workspaces);
  readonly jobGroups = [
    {area: 'Administração e gestão', jobs: ['Auxiliar administrativo', 'Assistente administrativo', 'Analista administrativo', 'Coordenador administrativo', 'Gerente de operações', 'Diretor executivo']},
    {area: 'Financeiro e contabilidade', jobs: ['Assistente financeiro', 'Analista financeiro', 'Analista fiscal', 'Contador', 'Controlador financeiro', 'Gerente financeiro']},
    {area: 'Comercial e atendimento', jobs: ['Assistente comercial', 'Consultor comercial', 'Analista de atendimento', 'Analista de sucesso do cliente', 'Gerente comercial']},
    {area: 'Jurídico', jobs: ['Advogado interno']},
    {area: 'Pessoas', jobs: ['Assistente de recursos humanos', 'Analista de recursos humanos', 'Analista de departamento pessoal', 'Gerente de recursos humanos']},
    {area: 'Operações e serviços', jobs: ['Assistente de operações', 'Analista de operações', 'Consultor de serviços', 'Supervisor de operações', 'Gerente de projetos']},
    {area: 'Tecnologia e marketing', jobs: ['Analista de suporte', 'Analista de sistemas', 'Desenvolvedor de software', 'Analista de dados', 'Analista de marketing']},
  ];

  readonly dateLabel = dateLabel;
  readonly history = signal(false);
  readonly closedLink = signal(false);
  readonly terminating = signal<Collaborator | null>(null);
  readonly reasons = [
    {key: 'JUSTA_CAUSA', label: 'Dispensa por justa causa (JC)'},
    {key: 'SEM_JUSTA_CAUSA', label: 'Dispensa sem justa causa (SJC)'},
    {key: 'PEDIDO_DEMISSAO', label: 'Pedido de demissão'},
    {key: 'FIM_CONTRATO', label: 'Término de contrato'},
    {key: 'ACORDO', label: 'Acordo entre as partes'},
    {key: 'OUTRO', label: 'Outro motivo'},
  ];
  readonly terminationForm = inject(FormBuilder).nonNullable.group({
    date: ['', Validators.required], reason: ['', Validators.required],
  });
  readonly rows = signal<Collaborator[]>([]);
  readonly error = signal('');
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly saved = signal(false);
  readonly available = signal(false);
  readonly money = money;
  readonly payroll = signal<{gross: string; inss: string; irrf: string; net: string} | null>(null);
  readonly creating = signal(false);
  readonly editing = signal<string | null>(null);
  readonly numericFields = new Set(['cpf', 'phone', 'branch', 'account', 'rg', 'cnh', 'cep']);
  readonly requiredPrivate = new Set(['cpf', 'phone', 'bank', 'branch', 'account', 'account_type']);
  readonly privateFields = [
    {key: 'cpf', label: 'CPF (11 dígitos)', max: 11, type: 'text'},
    {key: 'rg', label: 'RG', max: 80, type: 'text'},
    {key: 'cnh', label: 'CNH (11 dígitos)', max: 11, type: 'text'},
    {key: 'passport', label: 'Passaporte (opcional)', max: 20, type: 'text'},
    {key: 'birth_date', label: 'Data de nascimento', max: 10, type: 'date'},
    {key: 'birthplace', label: 'Cidade e UF ou país de nascimento', max: 250, type: 'text'},
    {key: 'phone', label: 'Celular com DDD (somente números)', max: 11, type: 'tel'},
    {key: 'monthly_compensation', label: 'Remuneração mensal bruta (R$)', max: 19, type: 'text'},
    {key: 'bank', label: 'Banco', max: 80, type: 'text'},
    {key: 'branch', label: 'Agência', max: 80, type: 'text'},
    {key: 'account', label: 'Conta com dígito', max: 80, type: 'text'},
  ];
  private readonly builder = inject(FormBuilder).nonNullable;
  readonly form = this.builder.group({
    name: ['', Validators.required], job_title: ['', Validators.required],
    employment_type: [''], work_model: [''], admission_date: [''],
    details: this.builder.record(Object.fromEntries([...this.privateFields.map(field => field.key), 'account_type', 'cep', 'address', 'pix_type', 'pix_key'].map(key => [key, this.builder.control('', [
      ...(this.requiredPrivate.has(key) ? [Validators.required] : []),
      ...(key === 'cpf' || key === 'cnh' ? [Validators.pattern(/^[0-9]{11}$/)] : []),
      ...(key === 'passport' ? [Validators.pattern(/^(?=.*[0-9])[A-Za-z0-9]{6,20}$/)] : []),
      ...(key === 'cep' ? [Validators.pattern(/^[0-9]{8}$/)] : []),
      ...(key === 'phone' ? [Validators.pattern(/^[0-9]{10,11}$/)] : []),
      ...(key === 'branch' || key === 'account' || key === 'rg' ? [Validators.pattern(/^[0-9]+$/)] : []),
    ])]))),

  });
  pending: string | null = null;
  private generation = 0;

  constructor() {
    effect(() => {
      const company = this.workspaces.selected();
      untracked(() => {
        const generation = ++this.generation;
        this.reset();
        this.pending = null;
        this.terminating.set(null);
        this.history.set(false);
        this.saved.set(false);
        this.available.set(false);
        this.rows.set([]);
        this.error.set('');
        this.loading.set(!!company);
        if (company) void this.load(this.url(company.organization_id, company.company_id), generation);
      });
    });
  }

  private url(organization: string, company: string): string {
    return `/api/v1/organizations/${encodeURIComponent(organization)}/companies/${encodeURIComponent(company)}/collaborators`;
  }

  private async load(url: string, generation: number): Promise<void> {
    try {
      const rows = await firstValueFrom(this.http.get<Collaborator[]>(url).pipe(timeout(15000)));
      if (generation === this.generation) {
        this.rows.set(rows);
        this.available.set(true);
      }
    } catch {
      if (generation === this.generation) this.error.set('Não foi possível consultar o cadastro desta empresa.');
    } finally {
      if (generation === this.generation) this.loading.set(false);
    }
  }

  filterDigits(key: string, event: Event): void {
    if (key === 'passport') {
      const input = event.target as HTMLInputElement;
      const passport = input.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
      input.value = passport;
      this.form.controls.details.controls[key].setValue(passport);
      return;
    }
    if (!this.numericFields.has(key)) return;
    const input = event.target as HTMLInputElement;
    const digits = input.value.replace(/[^0-9]/g, '');
    if (digits !== input.value) {
      input.value = digits;
      this.form.controls.details.controls[key].setValue(digits);
    }
  }

  reset(): void {
    this.form.reset();
    this.creating.set(false);
    this.editing.set(null);
    this.closedLink.set(false);
    this.payroll.set(null);
  }

  async edit(row: Collaborator): Promise<void> {
    const company = this.workspaces.selected();
    if (!company || this.saving()) return;
    const generation = this.generation;
    this.saving.set(true);
    this.saved.set(false);
    this.error.set('');
    try {
      const details = await firstValueFrom(this.http.get<Record<string, string | null>>(
        this.url(company.organization_id, company.company_id) + '/' + row.id + '/details',
      ).pipe(timeout(15000)));
      if (generation !== this.generation) return;
      this.form.reset({
        name: row.name, job_title: row.job_title,
        employment_type: row.employment_type ?? '', work_model: row.work_model ?? '',
        admission_date: row.admission_date ?? '',
        details: Object.fromEntries(Object.entries(details).map(([key, value]) => [key, value ?? ''])),
      });
      this.payroll.set(null);
      this.editing.set(row.id);
      this.closedLink.set(!!row.termination_date);
    } catch {
      if (generation === this.generation) this.error.set('Não foi possível abrir os dados do colaborador.');
    } finally {
      this.saving.set(false);
    }
  }

  visibleRows(): Collaborator[] {
    return this.rows().filter(row => !!row.termination_date === this.history());
  }

  reasonLabel(reason: string | null): string {
    return this.reasons.find(item => item.key === reason)?.label ?? '—';
  }

  duration(row: Collaborator): string {
    if (!row.admission_date || !row.termination_date) return 'Admissão não informada';
    const days = (Date.parse(row.termination_date) - Date.parse(row.admission_date)) / 86400000;
    return `${days} ${days === 1 ? 'dia' : 'dias'}`;
  }

  startTermination(row: Collaborator): void {
    this.error.set('');
    this.terminationForm.reset();
    this.terminating.set(row);
  }

  async terminate(row: Collaborator): Promise<void> {
    const company = this.workspaces.selected();
    if (!company || this.saving() || this.terminationForm.invalid) return;
    const generation = this.generation;
    const url = this.url(company.organization_id, company.company_id);
    this.saving.set(true);
    this.error.set('');
    try {
      await firstValueFrom(this.http.post(url + '/' + row.id + '/termination',
        this.terminationForm.getRawValue()).pipe(timeout(15000)));
      if (generation === this.generation) {
        if (this.editing() === row.id) this.reset();
        this.terminating.set(null);
        this.history.set(true);
        await this.load(url, generation);
      }
    } catch (failure) {
      if (generation === this.generation) {
        this.error.set((failure as {status?: number})?.status === 422
          ? 'Confira se a data de desligamento é igual ou posterior à admissão.'
          : 'Não foi possível confirmar o desligamento.');
      }
    } finally {
      this.saving.set(false);
    }
  }

  async previewPayroll(): Promise<void> {
    const company = this.workspaces.selected(), id = this.editing();
    if (!company || !id || this.saving()) return;
    const generation = this.generation;
    this.error.set('');
    try {
      const result = await firstValueFrom(this.http.get<{gross: string; inss: string; irrf: string; net: string}>(
        this.url(company.organization_id, company.company_id) + '/' + id + '/payroll-preview-2026',
      ).pipe(timeout(15000)));
      if (generation === this.generation && this.editing() === id) this.payroll.set(result);
    } catch {
      if (generation === this.generation && this.editing() === id) {
        this.payroll.set(null);
        this.error.set('Prévia indisponível. Confira se o vínculo CLT e a remuneração foram salvos.');
      }
    }
  }

  async save(): Promise<void> {
    const company = this.workspaces.selected();
    const {name, job_title, employment_type, work_model, admission_date, details} = this.form.getRawValue();
    if (this.form.invalid || !company || !this.available() || this.saving() || !name.trim() || !job_title.trim()) return;
    const generation = this.generation;
    const url = this.url(company.organization_id, company.company_id);
    const key = this.pending ?? crypto.randomUUID();
    const editing = this.editing();
    this.pending = editing ? null : key;
    this.saving.set(true);
    this.saved.set(false);
    this.error.set('');
    try {
      const body = {
        name, job_title, employment_type: employment_type || null, work_model: work_model || null,
        admission_date: admission_date || null,
        details: Object.fromEntries(Object.entries(details).map(([key, value]) => {
          const text = String(value ?? '').trim();
          return [key, (key === 'monthly_compensation' ? text.replace(',', '.') : text) || null];
        })),
      };
      await firstValueFrom((editing
        ? this.http.put(url + '/' + editing, body)
        : this.http.post(url, body, {headers: {'Idempotency-Key': key}})).pipe(timeout(15000)));
      if (generation === this.generation) {
        this.pending = null;
        this.reset();
        this.saved.set(true);
        await this.load(url, generation);
      }
    } catch (failure) {
      if (generation === this.generation) {
        const status = (failure as {status?: number})?.status;
        if (status && status >= 400 && status < 500) this.pending = null;
        this.error.set(this.pending ? 'Envio sem confirmação. Tente novamente.' : 'Não foi possível cadastrar o colaborador.');
      }
    } finally {
      this.saving.set(false);
    }
  }
}
