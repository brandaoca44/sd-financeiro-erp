import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController,provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { afterEach,describe,expect,it } from 'vitest';
import { AccountStatementPanel } from './account-statement';
import { Workspaces } from '../../core/workspaces';
import { FinanceApi } from '../../core/finance';
const page={start:'2026-11-01',end:'2026-11-06',opening_balance:'1000.00',incoming:'200.00',outgoing:'100.00',closing_balance:'1100.00',items:[{id:'receipt',source:'RECEIPT',reference_id:'bill',day:'2026-11-05',kind:'RECEIVED',description:'Serviço',amount:'200.00',direction:'IN',balance:'1100.00'}],next_cursor:'cursor'};
function setup(permissions=['accounts.read','payables.read','billing.read']){
 const selected=signal({organization_id:'org',company_id:'a',permissions});TestBed.configureTestingModule({imports:[AccountStatementPanel],providers:[provideRouter([]),provideHttpClient(),provideHttpClientTesting(),{provide:Workspaces,useValue:{selected,can:(key:string)=>selected().permissions.includes(key)}},{provide:FinanceApi,useValue:{revision:signal(0),base:(company:{company_id:string})=>'/api/'+company.company_id+'/payables'}}]});
 const fixture=TestBed.createComponent(AccountStatementPanel);fixture.componentRef.setInput('accountId','account');fixture.componentRef.setInput('openingDate','2026-01-01');fixture.detectChanges();return {fixture,selected,http:TestBed.inject(HttpTestingController)};
}
afterEach(()=>TestBed.resetTestingModule());
describe('Extrato por conta',()=>{
 it('mantém totais e saldo acumulado ao carregar a próxima página',async()=>{
  const {fixture,http}=setup();http.expectOne(request=>request.url.endsWith('/account/statement')).flush(page);await fixture.whenStable();
  const pending=fixture.componentInstance.more();const next=http.expectOne(request=>request.params.get('cursor')==='cursor');next.flush({...page,items:[{...page.items[0],id:'second',balance:'1200.00'}],next_cursor:null});await pending;
  expect(fixture.componentInstance.report()?.items.length).toBe(2);expect(fixture.componentInstance.report()?.closing_balance).toBe('1100.00');http.verify();fixture.destroy();
 });
 it('descarta resposta de uma conta anterior',async()=>{
  const {fixture,http}=setup();const old=http.expectOne(request=>request.url.endsWith('/account/statement'));
  fixture.componentRef.setInput('accountId','other');fixture.detectChanges();http.expectOne(request=>request.url.endsWith('/other/statement')).flush({...page,items:[],next_cursor:null});
  old.flush(page);await fixture.whenStable();expect(fixture.componentInstance.report()?.items).toEqual([]);http.verify();fixture.destroy();
 });
 it('não consulta quando falta acesso a uma das áreas',()=>{const {fixture,http}=setup(['accounts.read','billing.read']);http.expectNone(()=>true);expect(fixture.componentInstance.report()).toBeNull();fixture.destroy();});
 it('rejeita intervalo anterior à abertura sem enviar consulta',async()=>{
  const {fixture,http}=setup();http.expectOne(request=>request.url.endsWith('/statement')).flush(page);await fixture.whenStable();
  fixture.componentInstance.form.setValue({start:'2025-01-01',end:'2025-01-02'});fixture.componentInstance.apply();expect(fixture.componentInstance.error()).toContain('data inicial');http.expectNone(()=>true);fixture.destroy();
 });
 it('mantém recebimentos com a mesma chave em cobranças distintas',async()=>{
  const {fixture,http}=setup();http.expectOne(request=>request.url.endsWith('/statement')).flush({...page,items:[page.items[0],{...page.items[0],reference_id:'other-bill',balance:'1300.00'}],next_cursor:null});
  await fixture.whenStable();fixture.detectChanges();const rows=fixture.nativeElement.querySelectorAll('tbody tr');
  expect(rows.length).toBe(2);expect(rows[0].textContent).toContain('bill');expect(rows[1].textContent).toContain('other-bill');http.verify();fixture.destroy();
 });

});
