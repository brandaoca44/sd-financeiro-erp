import { Component, OnDestroy, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { AccountApi } from '../../core/account';
import { accountError } from './account-pages';

@Component({selector:'sdf-account-security',imports:[ReactiveFormsModule],template:`
<div class="page-heading"><div><span class="eyebrow">IDENTIDADE E ACESSO</span><h1>Segurança da conta</h1><p class="muted">As configurações desta página se aplicam ao seu usuário em todas as organizações.</p></div></div>
@if(error()){<div class="alert" role="alert">{{error()}}</div>}
@if(notice()){<div class="notice success" role="status">{{notice()}}</div>}
<section class="panel security-panel"><span class="eyebrow">AUTENTICAÇÃO MULTIFATOR</span><h2>Verificação em duas etapas</h2><p class="muted">Além da senha, use um aplicativo autenticador compatível com TOTP. O segundo fator será solicitado nos próximos acessos.</p>
@if(loading()){<p role="status">Carregando configuração…</p>}@else{
<div class="security-status"><span class="badge" [class.cancelled]="!enabled()">{{enabled()?'Ativada':'Desativada'}}</span></div>
@if(!available() && !enabled()){<p class="notice">A ativação depende de configuração de segurança pela administração do sistema.</p>}
@if(codes().length){<div class="recovery-panel"><h3>Códigos de recuperação</h3><p>Guarde estes códigos em um local seguro. Eles são exibidos apenas nesta etapa. Cada código permite um acesso e é invalidado após o uso.</p><div class="recovery-codes">@for(code of codes();track code){<code>{{code}}</code>}</div><button class="secondary" type="button" (click)="codes.set([])">Guardei os códigos</button></div>}
@else if(secret()){
<div class="notice">No aplicativo autenticador, adicione uma conta por chave manual. Selecione o modo baseado em tempo, com 6 dígitos e intervalo de 30 segundos.</div><dl class="factor-details"><dt>Nome da conta</dt><dd>Sistema Digital Financeiro</dd><dt>Chave de configuração</dt><dd><code class="setup-secret">{{secret()}}</code></dd></dl><p class="field-help">A chave é confidencial. Não a compartilhe. A configuração expira em 10 minutos.</p>
<form [formGroup]="factorForm" (ngSubmit)="enable()"><label for="enable-code">Código do aplicativo</label><input id="enable-code" formControlName="code" autocomplete="one-time-code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required><div class="security-actions"><button class="primary" type="submit" [disabled]="busy() || factorForm.invalid">Confirmar ativação</button><button class="secondary" type="button" [disabled]="busy()" (click)="secret.set('')">Cancelar</button></div></form>
}@else{
<form [formGroup]="passwordForm" (ngSubmit)="enabled()?disable():setup()"><label for="security-password">Senha atual</label><input id="security-password" type="password" formControlName="password" autocomplete="current-password" maxlength="128" required>
@if(enabled()){<label for="disable-code">Código do autenticador ou de recuperação</label><input id="disable-code" formControlName="code" autocomplete="one-time-code" maxlength="64"><p class="field-help">A desativação exige sua senha e um segundo fator válido. As outras sessões serão encerradas.</p>}
<div class="security-actions"><button class="primary" type="submit" [disabled]="busy() || passwordForm.controls.password.invalid || (!enabled() && !available()) || (enabled() && !passwordForm.controls.code.value)">{{busy()?'Processando…':enabled()?'Desativar verificação':'Configurar autenticador'}}</button></div></form>
}}
</section>`})
export class AccountSecurityPage implements OnDestroy {
  private api=inject(AccountApi);private http=inject(HttpClient);
  readonly enabled=signal(false);readonly available=signal(false);readonly loading=signal(true);readonly busy=signal(false);
  readonly secret=signal('');readonly codes=signal<string[]>([]);readonly error=signal('');readonly notice=signal('');
  private fb=inject(FormBuilder);
  readonly passwordForm=this.fb.nonNullable.group({password:['',Validators.required],code:['']});
  readonly factorForm=this.fb.nonNullable.group({code:['',[Validators.required,Validators.pattern(/^[0-9]{6}$/)]]});
  constructor(){void this.load();}
  async load(){try{const status=await firstValueFrom(this.http.get<{enabled:boolean;enrollment_available:boolean}>('/api/v1/auth/mfa/status').pipe(timeout(15000)));this.enabled.set(status.enabled);this.available.set(status.enrollment_available);}catch(error){this.error.set(accountError(error));}finally{this.loading.set(false);}}
  async setup(){if(this.busy() || this.passwordForm.controls.password.invalid || !this.available())return;this.busy.set(true);this.error.set('');this.notice.set('');
    try{const result=await this.api.post<{secret:string}>('mfa/setup',{password:this.passwordForm.getRawValue().password});this.secret.set(result.secret);}catch(error){this.error.set(accountError(error));}finally{this.passwordForm.reset();this.busy.set(false);}}
  async enable(){if(this.busy() || this.factorForm.invalid || !this.secret())return;this.busy.set(true);this.error.set('');
    try{const result=await this.api.post<{recovery_codes:string[]}>('mfa/enable',this.factorForm.getRawValue());this.codes.set(result.recovery_codes);this.secret.set('');this.enabled.set(true);this.notice.set('Verificação em duas etapas ativada. As outras sessões foram encerradas.');}catch(error){this.error.set(accountError(error));}finally{this.factorForm.reset();this.busy.set(false);}}
  async disable(){if(this.busy() || this.passwordForm.controls.password.invalid || !this.passwordForm.controls.code.value)return;this.busy.set(true);this.error.set('');this.notice.set('');
    try{await this.api.post('mfa/disable',this.passwordForm.getRawValue());this.enabled.set(false);this.notice.set('Verificação em duas etapas desativada. As outras sessões foram encerradas.');}catch(error){this.error.set(accountError(error));}finally{this.passwordForm.reset();this.busy.set(false);}}
  ngOnDestroy(){this.secret.set('');this.codes.set([]);this.passwordForm.reset();this.factorForm.reset();}
}
