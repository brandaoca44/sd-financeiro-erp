import { Component, OnDestroy, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Session } from '../../core/session';
import { accountError } from './account-pages';
import { AuthFrame } from './frame';

@Component({selector:'sdf-mfa-login',imports:[AuthFrame,ReactiveFormsModule,RouterLink],template:`
<sdf-auth-frame><span class="eyebrow">VERIFICAÇÃO DE IDENTIDADE</span><h2>Autenticação em duas etapas</h2><p class="muted">Informe o código do seu aplicativo autenticador ou um código de recuperação.</p>
@if(error()){<div class="alert" role="alert">{{error()}}</div>}
@if(session.challenge()){
<form [formGroup]="form" (ngSubmit)="submit()"><label for="factor-code">Código de verificação</label><input id="factor-code" class="otp-input" type="text" formControlName="code" autocomplete="one-time-code" maxlength="64" required autofocus><p class="field-help">O código do autenticador tem 6 dígitos. Cada código de recuperação pode ser usado uma única vez.</p><button type="submit" class="primary login-submit" [disabled]="busy() || form.invalid">{{busy()?'Verificando…':'Verificar e acessar'}}</button></form>
} @else {<p class="notice">Inicie uma nova autenticação para continuar.</p>}
<div class="auth-links"><a routerLink="/login" (click)="session.clear()">Voltar ao acesso</a></div></sdf-auth-frame>`})
export class MfaLogin implements OnDestroy {
  readonly session=inject(Session);private router=inject(Router);
  readonly form=inject(FormBuilder).nonNullable.group({code:['',[Validators.required,Validators.minLength(6),Validators.maxLength(64)]]});
  readonly busy=signal(false);readonly error=signal('');
  async submit(){if(this.busy() || this.form.invalid || !this.session.challenge())return;this.busy.set(true);this.error.set('');
    try{await this.session.completeMfa(this.form.getRawValue().code.trim());await this.router.navigateByUrl('/finance');}
    catch(error){this.error.set(accountError(error));}finally{this.form.reset();this.busy.set(false);}}
  ngOnDestroy(){this.form.reset();this.session.challenge.set(null);}
}
