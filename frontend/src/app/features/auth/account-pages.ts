import { Component, OnDestroy, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AccountApi } from '../../core/account';
import { AuthFrame } from './frame';
import { errorMessage } from '../../core/session';

export function accountError(error:unknown):string {
  if(error instanceof HttpErrorResponse){
    if(error.status===400)return 'Código ou link inválido, expirado ou já utilizado. Confira os dados ou solicite novas instruções.';
    if(error.status===422)return 'Confira os campos. A senha deve ter de 8 a 128 caracteres e não pode ser uma sequência comum.';
    if(error.status===503)return 'Este recurso está indisponível no momento. Tente novamente mais tarde.';
  }
  return errorMessage(error);
}

@Component({selector:'sdf-account-page',imports:[AuthFrame,ReactiveFormsModule,RouterLink],template:`
<sdf-auth-frame [class.auth-registration]="mode==='register'" class="account-access-page"><span class="eyebrow">IDENTIDADE E ACESSO</span><h2>{{title}}</h2><p class="muted">{{description}}</p>
@if(loading()){<p class="notice" role="status">Verificando disponibilidade…</p>}
@if(!loading() && !api.capabilities().email_flows_available && !isTokenAction){<div class="notice" role="status">A confirmação por e-mail ainda não está habilitada. O cadastro e a recuperação estão indisponíveis no momento.</div>}
@if(error()){<div class="alert" role="alert">{{error()}}</div>}
@if(done()){<div class="notice success" role="status">{{done()}}</div><a class="primary login-submit" routerLink="/login">Voltar ao acesso</a>}
@else{
<form [formGroup]="form" (ngSubmit)="submit()">
@if(mode==='register'){
<div class="registration-fields">
<div class="field field-full"><label for="name">Nome completo conforme o documento</label><input id="name" formControlName="name" autocomplete="name" maxlength="150" required></div>
<div class="field"><label for="cpf">CPF do titular</label><input id="cpf" type="text" formControlName="cpf" inputmode="numeric" autocomplete="off" maxlength="14" placeholder="000.000.000-00" required></div>
<div class="field"><label for="account-email">E-mail profissional</label><input id="account-email" type="email" formControlName="email" autocomplete="email" maxlength="254" placeholder="nome@empresa.com.br" required></div>
<div class="field"><label for="new-password">Senha</label><input id="new-password" type="password" formControlName="password" autocomplete="new-password" minlength="8" maxlength="128" aria-describedby="password-policy" required></div>
<div class="field"><label for="confirm-password">Confirmar senha</label><input id="confirm-password" type="password" formControlName="confirmation" autocomplete="new-password" maxlength="128" required></div>
</div><small class="field-help" id="password-policy">Senha de 8 a 128 caracteres. Caracteres especiais são permitidos.</small>
}@else{
@if(!isTokenAction){<label for="account-email">E-mail profissional</label><input id="account-email" type="email" formControlName="email" autocomplete="email" maxlength="254" required>}
@if(mode==='reset'){
<label for="new-password">Nova senha</label><input id="new-password" type="password" formControlName="password" autocomplete="new-password" minlength="8" maxlength="128" aria-describedby="password-policy" required>
<small class="field-help" id="password-policy">De 8 a 128 caracteres. Caracteres especiais são permitidos.</small>
<label for="confirm-password">Confirmar senha</label><input id="confirm-password" type="password" formControlName="confirmation" autocomplete="new-password" maxlength="128" required>}
}
@if(isTokenAction && !token){<div class="notice">Abra o link recebido por e-mail para continuar.</div>}
<button class="primary login-submit" type="submit" [disabled]="busy() || loading() || form.invalid || (isTokenAction ? !token : !api.capabilities().email_flows_available)">{{busy()?'Processando…':button}}</button></form>
<div class="auth-links"><a routerLink="/login">Voltar ao acesso</a>@if(mode==='confirm'){<a routerLink="/resend-confirmation">Solicitar novo link</a>}@if(mode==='reset'){<a routerLink="/forgot-password">Solicitar novo link</a>}</div>}
<p class="login-help">O acesso aos dados da empresa depende do vínculo e das permissões da organização.</p></sdf-auth-frame>`})
export class AccountPage implements OnDestroy {
  readonly api=inject(AccountApi);private router=inject(Router);private route=inject(ActivatedRoute);
  readonly mode=this.route.snapshot.data['mode'] as 'register'|'forgot'|'resend'|'confirm'|'reset';
  readonly isTokenAction=this.mode==='confirm' || this.mode==='reset';
  readonly title={register:'Criar conta',forgot:'Recuperar acesso',resend:'Confirmar e-mail',confirm:'Confirmar e-mail',reset:'Redefinir senha'}[this.mode];
  readonly description={register:'Cadastre sua identidade de acesso ao sistema.',forgot:'Informe seu e-mail para solicitar a redefinição da senha.',resend:'Solicite um novo link de confirmação para seu e-mail.',confirm:'Confirme o endereço de e-mail associado ao cadastro.',reset:'Defina uma nova senha para sua conta.'}[this.mode];
  readonly button={register:'Criar conta',forgot:'Solicitar instruções',resend:'Solicitar confirmação',confirm:'Confirmar e-mail',reset:'Redefinir senha'}[this.mode];
  readonly busy=signal(false);readonly loading=signal(true);readonly error=signal('');readonly done=signal('');
  token='';
  readonly form=inject(FormBuilder).nonNullable.group({name:[''],cpf:[''],email:[''],password:[''],confirmation:['']});
  constructor(){
    if(!this.isTokenAction)this.form.controls.email.setValidators([Validators.required,Validators.email,Validators.maxLength(254)]);
    if(this.mode==='register'){this.form.controls.name.setValidators([Validators.required,Validators.pattern(/^\s*\S+\s+\S+.*$/),Validators.maxLength(150)]);this.form.controls.cpf.setValidators([Validators.required,Validators.pattern(/^(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})$/)]);}
    if(this.mode==='register' || this.mode==='reset'){
      this.form.controls.password.setValidators([Validators.required,Validators.minLength(8),Validators.maxLength(128)]);
      this.form.controls.confirmation.setValidators([Validators.required]);
    }
    for(const control of Object.values(this.form.controls))control.updateValueAndValidity();
    const fragment=this.route.snapshot.fragment || '';
    if(this.isTokenAction && /^[A-Za-z0-9_-]{43}$/.test(fragment))this.token=fragment;
    if(fragment)void this.router.navigate([], {relativeTo:this.route,fragment:undefined,replaceUrl:true});
    void this.load();
  }
  async load(){try{await this.api.load();}catch{this.error.set('Não foi possível verificar a disponibilidade do serviço. Recarregue a página.');}finally{this.loading.set(false);}}
  async submit():Promise<void>{
    if(this.busy() || this.loading() || this.form.invalid || (this.isTokenAction ? !this.token : !this.api.capabilities().email_flows_available))return;
    const value=this.form.getRawValue();
    if((this.mode==='register' || this.mode==='reset') && value.password!==value.confirmation){this.error.set('As senhas informadas não coincidem.');return;}
    this.busy.set(true);this.error.set('');
    try{
      const paths={register:'register',forgot:'password/forgot',resend:'email/resend',confirm:'email/confirm',reset:'password/reset'};
      const body=this.mode==='register'?{name:value.name.trim(),cpf:value.cpf,email:value.email.trim(),password:value.password}:this.mode==='reset'?{token:this.token,password:value.password}:this.mode==='confirm'?{token:this.token}:{email:value.email.trim()};
      await this.api.post(paths[this.mode],body);
      this.done.set(this.isTokenAction?(this.mode==='reset'?'Senha redefinida. Acesse novamente com sua nova senha.':'E-mail confirmado. Sua identidade de acesso foi validada.'):'Se os dados forem elegíveis, você receberá as instruções por e-mail. Verifique também a pasta de spam.');
      this.token='';this.form.reset();
    }catch(error){this.error.set(accountError(error));this.form.controls.password.reset();this.form.controls.confirmation.reset();this.form.controls.cpf.reset();}finally{this.busy.set(false);}
  }
  ngOnDestroy(){this.token='';this.form.reset();}
}
