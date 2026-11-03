import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthFrame } from './frame';
import { Session, errorMessage } from '../../core/session';

@Component({selector:'sdf-login',imports:[ReactiveFormsModule,RouterLink,AuthFrame],template:`
<sdf-auth-frame><span class="eyebrow">ACESSO CORPORATIVO</span><h2>Acessar o sistema</h2><p class="muted">Informe suas credenciais de acesso.</p>
@if(session.notice()){<div class="notice" role="status">{{session.notice()}}</div>}
@if(error()){<div class="alert" role="alert">{{error()}}</div>}
<form [formGroup]="form" (ngSubmit)="submit()"><label for="email">E-mail</label><div class="login-input"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/></svg><input id="email" type="email" formControlName="email" autocomplete="username" placeholder="voce@empresa.com.br" required></div>
<label for="password">Senha</label><div class="login-input"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/></svg><input id="password" [type]="passwordVisible()?'text':'password'" formControlName="password" autocomplete="current-password" placeholder="Sua senha" required><button class="password-toggle" type="button" [attr.aria-label]="passwordVisible()?'Ocultar senha':'Mostrar senha'" [attr.aria-pressed]="passwordVisible()" (click)="passwordVisible.set(!passwordVisible())"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>@if(!passwordVisible()){<path d="m3 3 18 18"/>}</svg></button></div>
<button class="primary login-submit" [disabled]="busy() || form.invalid" type="submit">{{busy()?'Entrando…':'Entrar'}} <span aria-hidden="true">→</span></button></form>
<div class="auth-links login-secondary-links"><a routerLink="/register">Criar conta</a><a routerLink="/forgot-password">Esqueci minha senha</a></div><p class="login-help">Já possui cadastro pendente? <a routerLink="/resend-confirmation">Confirmar e-mail</a></p>
<div class="login-plan-link"><a routerLink="/plans">Conhecer os planos <span aria-hidden="true">↗</span></a></div><div class="login-security"><span aria-hidden="true">◇</span> Acesso individual. Informações protegidas por permissão.</div></sdf-auth-frame>`})
export class Login {
  readonly session=inject(Session);private router=inject(Router);
  readonly passwordVisible=signal(false);readonly busy=signal(false);readonly error=signal('');
  readonly form=inject(FormBuilder).nonNullable.group({email:['',[Validators.required,Validators.email]],password:['',Validators.required]});
  async submit():Promise<void>{if(this.busy() || this.form.invalid)return;this.busy.set(true);this.error.set('');const value=this.form.getRawValue();
    try{await this.session.login(value.email.trim(),value.password);this.form.controls.password.reset();this.passwordVisible.set(false);await this.router.navigateByUrl(this.session.challenge()?'/mfa':'/finance');}
    catch(error){this.form.controls.password.reset();this.passwordVisible.set(false);this.error.set(errorMessage(error));}finally{this.busy.set(false);}}
}
