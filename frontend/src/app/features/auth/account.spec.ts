import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { afterEach, describe, expect, it } from 'vitest';
import { Session } from '../../core/session';
import { AccountPage } from './account-pages';

function setup(mode='register'){
  TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting(),provideRouter([]),
    {provide:ActivatedRoute,useValue:{snapshot:{data:{mode},fragment:null}}}]});
  return TestBed.inject(HttpTestingController);
}

describe('Cadastro e segundo fator',()=>{
  afterEach(()=>TestBed.inject(HttpTestingController).verify());
  it('não emite sessão antes de completar o segundo fator',async()=>{
    const http=setup(),session=TestBed.inject(Session);
    const login=session.login('teste@example.invalid','senha-ficticia');
    http.expectOne('/api/v1/auth/login').flush({mfa_required:true,challenge_token:'desafio-ficticio'});await login;
    expect(session.token()).toBeNull();expect(session.challenge()).toBe('desafio-ficticio');
    const factor=session.completeMfa('123456');
    const request=http.expectOne('/api/v1/auth/mfa/login');expect(request.request.body.challenge_token).toBe('desafio-ficticio');
    request.flush({access_token:'sessao-validada'});await factor;
    expect(session.token()).toBe('sessao-validada');expect(session.challenge()).toBeNull();
  });
  it('descarta autenticação MFA concluída após o usuário cancelar o acesso',async()=>{
    const http=setup(),session=TestBed.inject(Session);
    session.challenge.set('desafio-ficticio');
    const pending=session.completeMfa('123456');const cancelled=expect(pending).rejects.toThrow();
    session.clear();http.expectOne('/api/v1/auth/mfa/login').flush({access_token:'sessao-atrasada'});
    await cancelled;expect(session.token()).toBeNull();
  });
  it('não fabrica envio nem cadastro quando o recurso está desabilitado',async()=>{
    const http=setup(),fixture=TestBed.createComponent(AccountPage),page=fixture.componentInstance;
    http.expectOne('/api/v1/auth/capabilities').flush({email_flows_available:false,mfa_enrollment_available:false});
    await fixture.whenStable();
    page.form.setValue({name:'Pessoa Teste',cpf:'00000000191',email:'teste@example.invalid',password:'senha-ficticia',confirmation:'senha-ficticia'});
    await page.submit();http.expectNone('/api/v1/auth/register');expect(page.done()).toBe('');
    fixture.detectChanges();expect(fixture.nativeElement.textContent).toContain('ainda não está habilitada');
  });
  it('exige CPF e nome completo e bloqueia confirmação de senha divergente',async()=>{
    const http=setup(),fixture=TestBed.createComponent(AccountPage),page=fixture.componentInstance;
    http.expectOne('/api/v1/auth/capabilities').flush({email_flows_available:true,mfa_enrollment_available:false});await fixture.whenStable();
    page.form.setValue({name:'Pessoa',cpf:'',email:'teste@example.invalid',password:'senha-ficticia',confirmation:'outra-senha'});
    expect(page.form.invalid).toBe(true);
    page.form.patchValue({name:'Pessoa Teste',cpf:'00000000191'});await page.submit();
    http.expectNone('/api/v1/auth/register');expect(page.error()).toContain('não coincidem');
  });
  it('não permite confirmar e-mail sem o token do link',async()=>{
    const http=setup('confirm'),fixture=TestBed.createComponent(AccountPage),page=fixture.componentInstance;
    http.expectOne('/api/v1/auth/capabilities').flush({email_flows_available:false,mfa_enrollment_available:false});await fixture.whenStable();
    await page.submit();http.expectNone('/api/v1/auth/email/confirm');expect(page.done()).toBe('');
  });
});
