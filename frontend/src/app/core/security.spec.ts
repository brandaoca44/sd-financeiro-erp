import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Session, sessionInterceptor, errorMessage } from './session';
import { Workspaces, Workspace } from './workspaces';
import { money } from './finance';

describe('Sessão e isolamento do cliente',()=>{
  let session:Session;let http:HttpClient;let control:HttpTestingController;
  beforeEach(()=>{TestBed.configureTestingModule({providers:[provideHttpClient(withInterceptors([sessionInterceptor])),provideHttpClientTesting(),provideRouter([])]});session=TestBed.inject(Session);http=TestBed.inject(HttpClient);control=TestBed.inject(HttpTestingController);});
  afterEach(()=>{control.verify();vi.restoreAllMocks();});
  it('mantém token somente na memória e não persiste a senha',async()=>{
    const local=vi.spyOn(localStorage,'setItem'),tab=vi.spyOn(sessionStorage,'setItem');
    const login=session.login('pessoa@example.invalid','senha-sintetica');
    const request=control.expectOne('/api/v1/auth/login');expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({access_token:'token-sintetico'});await login;expect(session.token()).toBe('token-sintetico');expect(local).not.toHaveBeenCalled();expect(tab).not.toHaveBeenCalled();session.clear();expect(session.token()).toBeNull();
  });
  it('envia Bearer apenas ao prefixo interno da API',()=>{
    session.token.set('token');http.get('/api/v1/auth/workspaces').subscribe();http.get('https://example.invalid/arquivo').subscribe();
    const own=control.expectOne('/api/v1/auth/workspaces'),external=control.expectOne('https://example.invalid/arquivo');
    expect(own.request.headers.get('Authorization')).toBe('Bearer token');expect(external.request.headers.has('Authorization')).toBe(false);own.flush({});external.flush({});
  });
  it('limpa sessão em 401 sem expor a resposta privada',()=>{
    session.token.set('token');http.get('/api/v1/auth/workspaces').subscribe({error:()=>undefined});control.expectOne('/api/v1/auth/workspaces').flush({detail:'privado'},{status:401,statusText:'Unauthorized'});expect(session.token()).toBeNull();expect(errorMessage(new HttpErrorResponse({status:500,error:{detail:'privado'}}))).not.toContain('privado');
  });
  it('não encerra uma sessão nova por resposta atrasada da anterior',()=>{
    session.token.set('old');http.get('/api/v1/auth/workspaces').subscribe({error:()=>undefined});session.token.set('new');control.expectOne('/api/v1/auth/workspaces').flush({},{status:401,statusText:'Unauthorized'});expect(session.token()).toBe('new');
  });
  it('não troca revogação confirmada por simples limpeza local em erro',async()=>{
    session.token.set('token');const logout=session.logout();const assertion=expect(logout).rejects.toBeInstanceOf(HttpErrorResponse);control.expectOne('/api/v1/auth/logout').flush({},{status:503,statusText:'Unavailable'});await assertion;expect(session.token()).toBe('token');
  });
  it('ignora respostas antigas após recarregar os contextos',async()=>{
    session.token.set('token');const workspaces=TestBed.inject(Workspaces);
    const first=workspaces.load(),second=workspaces.load();const requests=control.match(request=>request.url==='/api/v1/auth/workspaces');
    const item=(id:string):Workspace=>({organization_id:'org',company_id:id,company_name:null,permissions:['payables.read']});
    requests[1].flush({items:[item('new')],next_cursor:null});await second;requests[0].flush({items:[item('old')],next_cursor:null});await first;expect(workspaces.selected()?.company_id).toBe('new');
  });
  it('formata valores grandes e negativos sem perder centavos',()=>{
    expect(money('19999999999999999.98')).toBe('R$ 19.999.999.999.999.999,98');expect(money('-0.10')).toBe('− R$ 0,10');expect(money('NaN')).toBe('—');
  });
});
