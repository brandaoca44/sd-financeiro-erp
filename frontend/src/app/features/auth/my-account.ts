import { BankSelector } from '../../core/bank-selector';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { ContextHelp } from '../../core/context-help';

interface Profile {
  name: string;
  email: string;
  revision: number;
  cpf_locked: boolean;
  [key: string]: string | number | boolean | null;
}

@Component({
  selector: 'sdf-my-account',
  imports: [ReactiveFormsModule, ContextHelp, BankSelector],
  styles: `
    form { width: 100%; min-width: 0; max-width: 68rem; display: grid; gap: 1rem; }
    .profile-section { min-width: 0; max-width: 100%; border: 1px solid #dbe5f0; border-radius: .75rem; padding: 1.2rem; background: linear-gradient(145deg, #fff, #f5f8fc); }
    .profile-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr)); gap: 1rem; align-items: start; }
    .profile-grid > * { min-width: 0; }
    .bank-field { grid-column: 1 / -1; display: grid; gap: .4rem; }
    label { display: grid; gap: .4rem; margin: 0; min-width: 0; }
    input, select { width: 100%; min-width: 0; }
    h2 { margin-bottom: 1rem; }
    .profile-title { display: flex; align-items: baseline; gap: .5rem; }
    .save-profile { display: flex; justify-content: flex-end; align-items: end; flex-wrap: wrap; gap: 1rem; }
    .save-profile label { flex: 1 1 15rem; max-width: 24rem; }
    .primary { background: linear-gradient(115deg, #173762, #27548d); }
    .readonly-field { background: #edf2f8; color: #425b76; }
  `,
  template: `
    <div class="page-heading"><div><span class="eyebrow">CONFIGURAÇÕES</span><h1>Minha conta</h1>
      <p class="muted">Dados pessoais e de pagamento do seu usuário.</p></div></div>
    @if (loading()) { <p role="status">Carregando perfil…</p> }
    @if (error()) { <p class="alert" role="alert">{{error()}}</p> }
    @if (saved()) { <p class="notice" role="status">Dados da conta atualizados.</p> }
    @if (!profile() && !loading()) { <button class="secondary" type="button" (click)="load()">Tentar novamente</button> }
    @if (profile(); as user) {
      <form [formGroup]="form" (ngSubmit)="save()">
        <fieldset class="profile-section" [disabled]="saving()">
          <h2>Identificação</h2>
          <div class="profile-grid">
            <label>Nome completo<input formControlName="name" maxlength="150" autocomplete="name" required></label>
            <label>E-mail de acesso<input [value]="user.email" class="readonly-field" readonly type="email"></label>
            @for (field of identityFields; track field.key) {
              <label>{{field.label}}<input [formControlName]="field.key" [type]="field.type" [maxLength]="field.max"
                [placeholder]="field.key === 'passport' ? 'Ex.: AB123456' : ''"
                [readOnly]="field.key === 'cpf' && user.cpf_locked"
                [class.readonly-field]="field.key === 'cpf' && user.cpf_locked"
                [attr.inputmode]="numericFields.has(field.key) ? 'numeric' : null"
                (input)="filterDigits(field.key, $event)" autocomplete="off">
                @if (field.key === 'passport') { <small class="field-help">Letras e números conforme o documento.</small> }
              </label>
            }
          </div>
          @if (user.cpf_locked) { <p class="field-help">O CPF registrado identifica o titular da conta.</p> }
        </fieldset>
        <fieldset class="profile-section" [disabled]="saving()">
          <h2>Endereço residencial</h2>
          <div class="profile-grid">
            <label>CEP<input formControlName="cep" maxlength="8" inputmode="numeric" (input)="filterDigits('cep', $event)" autocomplete="postal-code"></label>
            <label>Endereço completo<input formControlName="address" maxlength="250" placeholder="Rua, número, complemento, bairro, cidade e UF" autocomplete="street-address"></label>
          </div>
        </fieldset>
        <fieldset class="profile-section" [disabled]="saving()">
          <h2>Dados bancários</h2>
          <div class="profile-grid">
            <div class="bank-field"><label id="profile-bank-label">Banco</label><sdf-bank-selector formControlName="bank" aria-labelledby="profile-bank-label" /></div>
            <label>Agência<input formControlName="branch" maxlength="30" inputmode="numeric" (input)="filterDigits('branch', $event)" autocomplete="off"></label>
            <label>Conta com dígito<input formControlName="account" maxlength="30" inputmode="numeric" (input)="filterDigits('account', $event)" autocomplete="off"></label>
            <label>Tipo de conta<select formControlName="account_type">
              <option value="">Selecione</option>
              <option value="CORRENTE">Corrente</option><option value="POUPANCA">Poupança</option>
              <option value="SALARIO">Salário</option><option value="PAGAMENTO">Pagamento</option>
            </select></label>
          </div>
        </fieldset>
        <fieldset class="profile-section" [disabled]="saving()">
          <div class="profile-title"><h2>Chave Pix</h2>
            <sdf-help text="Selecione o tipo e informe a chave cadastrada no banco. Para telefone, use o formato +55 seguido do DDD e número. A chave fica armazenada no seu perfil." />
          </div>
          <div class="profile-grid">
            <label>Tipo de chave<select formControlName="pix_type">
              <option value="">Sem chave Pix</option>
              <option value="CPF">CPF</option><option value="CNPJ">CNPJ</option><option value="EMAIL">E-mail</option>
              <option value="PHONE">Telefone</option><option value="RANDOM">Chave aleatória</option>
            </select></label>
            <label>Chave Pix<input formControlName="pix_key" maxlength="254" autocomplete="off"></label>
          </div>
        </fieldset>
        <div class="save-profile">
          <label>Senha atual para confirmar<input type="password" formControlName="password" autocomplete="current-password" maxlength="128" required></label>
          <button class="primary" type="submit" [disabled]="saving() || form.invalid">
            {{saving() ? 'Salvando…' : 'Salvar alterações'}}
          </button>
        </div>
      </form>
    }
  `,
})
export class MyAccount {
  private readonly http = inject(HttpClient);
  private readonly endpoint = '/api/v1/auth/profile';
  readonly profile = signal<Profile | null>(null);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly saved = signal(false);
  readonly error = signal('');
  private destroyed = false;
  readonly numericFields = new Set(['cpf', 'rg', 'cnh', 'phone', 'cep', 'branch', 'account']);
  readonly identityFields = [
    {key: 'cpf', label: 'CPF', max: 11, type: 'text'},
    {key: 'rg', label: 'RG', max: 30, type: 'text'},
    {key: 'cnh', label: 'CNH', max: 11, type: 'text'},
    {key: 'passport', label: 'Passaporte (opcional)', max: 20, type: 'text'},
    {key: 'birth_date', label: 'Data de nascimento', max: 10, type: 'date'},
    {key: 'phone', label: 'Celular com DDD', max: 11, type: 'tel'},
  ];
  private readonly fb = inject(FormBuilder).nonNullable;
  readonly form = this.fb.record(Object.fromEntries([
    'name', 'cpf', 'rg', 'cnh', 'passport', 'birth_date', 'phone', 'cep', 'address',
    'bank', 'branch', 'account', 'account_type', 'pix_type', 'pix_key', 'password',
  ].map(key => [key, this.fb.control('', [
    ...(['name', 'password'].includes(key) ? [Validators.required] : []),
    ...(['cpf', 'cnh'].includes(key) ? [Validators.pattern(/^[0-9]{11}$/)] : []),
    ...(key === 'phone' ? [Validators.pattern(/^[0-9]{10,11}$/)] : []),
    ...(key === 'passport' ? [Validators.pattern(/^(?=.*[0-9])[A-Za-z0-9]{6,20}$/)] : []),
    ...(key === 'cep' ? [Validators.pattern(/^[0-9]{8}$/)] : []),
    ...(['rg', 'branch', 'account'].includes(key) ? [Validators.pattern(/^[0-9]+$/)] : []),
  ])])));

  constructor() {
    inject(DestroyRef).onDestroy(() => { this.destroyed = true; this.form.reset(); this.profile.set(null); });
    void this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const profile = await firstValueFrom(this.http.get<Profile>(this.endpoint).pipe(timeout(15000)));
      if (!this.destroyed) this.applyProfile(profile);
    } catch {
      if (!this.destroyed) this.error.set('Não foi possível carregar os dados da conta.');
    } finally {
      if (!this.destroyed) this.loading.set(false);
    }
  }

  private applyProfile(profile: Profile): void {
    this.profile.set(profile);
    this.form.reset(Object.fromEntries(Object.keys(this.form.controls).map(key =>
      [key, key === 'password' ? '' : String(profile[key] ?? '')])));
  }

  filterDigits(key: string, event: Event): void {
    const input = event.target as HTMLInputElement;
    if (key === 'passport') {
      const passport = input.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
      input.value = passport;
      this.form.controls[key].setValue(passport);
      return;
    }
    if (!this.numericFields.has(key)) return;
    const value = input.value.replace(/[^0-9]/g, '');
    input.value = value;
    this.form.controls[key].setValue(value);
  }

  async save(): Promise<void> {
    const profile = this.profile();
    if (!profile || this.form.invalid || this.saving()) return;
    const values = this.form.getRawValue();
    if (!!values['pix_type'] !== !!values['pix_key'].trim()) {
      this.error.set('Informe o tipo e a chave Pix, ou deixe ambos em branco.');
      return;
    }
    this.saving.set(true);
    this.saved.set(false);
    this.error.set('');
    const body = {...Object.fromEntries(Object.entries(values).map(([key, value]) =>
      [key, key === 'password' ? value : value.trim() || null])), expected_revision: profile.revision};
    try {
      const result = await firstValueFrom(this.http.put<Profile>(this.endpoint, body).pipe(timeout(15000)));
      if (!this.destroyed) {
        this.applyProfile(result);
        this.saved.set(true);
      }
    } catch (failure) {
      if (!this.destroyed) {
        const status = (failure as HttpErrorResponse).status;
        this.error.set(status === 409 ? 'O perfil foi alterado ou os dados de identificação precisam de revisão. Recarregue a página.'
          : status === 403 ? 'Confira a senha atual para confirmar a alteração.'
          : status === 422 ? 'Confira os documentos, os campos numéricos e a chave Pix.'
          : 'Não foi possível confirmar a alteração. Recarregue o perfil antes de tentar novamente.');
      }
    } finally {
      this.form.controls['password'].reset();
      if (!this.destroyed) this.saving.set(false);
    }
  }
}
