import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { afterEach,describe,expect,it } from 'vitest';
import { FinancialAccountsPage } from './financial-accounts';
import { Workspaces } from '../../core/workspaces';
import { FinanceApi } from '../../core/finance';
const account={id:'account',name:'Operacional',kind:'BANK' as const,currency:'BRL',opening_balance:'100.00',opening_date:'2026-01-01',status:'ACTIVE',revision:1};
function setup(permissions=['accounts.read','accounts.manage']){const selected=signal({organization_id:'org',company_id:'a',permissions});
  TestBed.configureTestingModule({imports:[FinancialAccountsPage],providers:[provideHttpClient(),provideHttpClientTesting(),
    {provide:Workspaces,useValue:{selected,can:(key:string)=>selected().permissions.includes(key)}},
    {provide:FinanceApi,useValue:{revision:signal(0),base:(company:{company_id:string})=>'/api/'+company.company_id+'/payables'}}]});
  const fixture=TestBed.createComponent(FinancialAccountsPage),http=TestBed.inject(HttpTestingController);fixture.detectChanges();return {fixture,http,selected};}
afterEach(()=>TestBed.resetTestingModule());
describe('Contas financeiras da empresa',()=>{
  it('edita dados básicos sem consultar ou enviar informações bancárias',async()=>{
    const {fixture,http}=setup();http.expectOne(request=>request.url==='/api/a/financial-accounts').flush({items:[account],next_cursor:null});await fixture.whenStable();
    const component=fixture.componentInstance;component.open(account);component.form.controls.name.setValue('Novo nome');
    http.expectNone(request=>request.url.endsWith('/bank-details'));const save=component.save();const request=http.expectOne('/api/a/financial-accounts/account');
    expect(request.request.body).toEqual({name:'Novo nome',status:'ACTIVE',expected_revision:1});
    request.flush({id:'account',revision:2});await Promise.resolve();http.expectOne(request=>request.url==='/api/a/financial-accounts').flush({items:[{...account,revision:2}],next_cursor:null});await save;http.verify();fixture.destroy();
  });
  it('confirma o mesmo cadastro após perda de conexão',async()=>{
    const {fixture,http}=setup(['accounts.manage']);const component=fixture.componentInstance;
    component.start();component.form.controls.name.setValue('Caixa');component.form.controls.opening_date.setValue('2026-01-01');
    const first=component.save();const request=http.expectOne('/api/a/financial-accounts');const key=request.request.headers.get('Idempotency-Key');const body=request.request.body;
    expect(body.bank_details).toBeUndefined();request.error(new ProgressEvent('error'));await first;
    component.form.controls.name.setValue('Outro');const retry=component.save();const repeat=http.expectOne('/api/a/financial-accounts');
    expect(repeat.request.headers.get('Idempotency-Key')).toBe(key);expect(repeat.request.body).toEqual(body);repeat.flush({id:'account',revision:1});await retry;http.verify();fixture.destroy();
  });
  it('descarta informações da empresa anterior',async()=>{
    const {fixture,http,selected}=setup();const old=http.expectOne(request=>request.url==='/api/a/financial-accounts');
    selected.set({...selected(),company_id:'b'});fixture.detectChanges();http.expectOne(request=>request.url==='/api/b/financial-accounts').flush({items:[],next_cursor:null});
    old.flush({items:[account],next_cursor:null});await fixture.whenStable();expect(fixture.componentInstance.rows()).toEqual([]);expect(fixture.componentInstance.selected()).toBeNull();http.verify();fixture.destroy();
  });
  it('não consulta contas com permissão de outros motores',()=>{const {fixture,http}=setup(['payables.read','people.bank']);http.expectNone(()=>true);expect(fixture.nativeElement.textContent).toContain('não permite acessar');fixture.destroy();});
  it('exibe o saldo calculado e descarta uma consulta encerrada',async()=>{
    const {fixture,http}=setup(['accounts.read','accounts.manage','payables.read','billing.read']);
    http.expectOne(request=>request.url==='/api/a/financial-accounts').flush({items:[account],next_cursor:null});await fixture.whenStable();
    const component=fixture.componentInstance;component.open(account);fixture.detectChanges();const first=http.expectOne('/api/a/financial-accounts/account/position');
    const statement={start:'2026-11-01',end:'2026-11-06',opening_balance:'100.00',incoming:'0.00',outgoing:'0.00',closing_balance:'100.00',items:[],next_cursor:null};
    http.expectOne(request=>request.url.endsWith('/statement')).flush(statement);
    component.close();fixture.detectChanges();component.open(account);fixture.detectChanges();const second=http.expectOne('/api/a/financial-accounts/account/position');
    http.expectOne(request=>request.url.endsWith('/statement')).flush(statement);
    second.flush({as_of:'2026-11-06',current_balance:'150.00',receipts_amount:'50.00',payments_amount:'0.00',receipt_reversals_amount:'0.00',payment_reversals_amount:'0.00',unassigned_payments:1,unassigned_receipts:2});await Promise.resolve();
    first.flush({current_balance:'999.00'});await fixture.whenStable();fixture.detectChanges();
    expect(component.position()?.current_balance).toBe('150.00');expect(fixture.nativeElement.textContent).toContain('Saldo calculado pelo ERP');http.verify();fixture.destroy();
  });

});
