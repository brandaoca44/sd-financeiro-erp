import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController,provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { afterEach,describe,expect,it } from 'vitest';
import { AccountPicker } from './account-picker';
import { LegacyAccountLink } from './legacy-account-link';
import { Workspaces } from './workspaces';
import { FinanceApi } from './finance';
function setup(permissions=['accounts.read','accounts.manage','billing.receive','billing.reverse']){
  const selected=signal({organization_id:'org',company_id:'a',permissions});
  TestBed.configureTestingModule({imports:[AccountPicker,LegacyAccountLink],providers:[provideHttpClient(),provideHttpClientTesting(),
    {provide:Workspaces,useValue:{selected,can:(key:string)=>selected().permissions.includes(key)}},
    {provide:FinanceApi,useValue:{revision:signal(0),base:(company:{company_id:string})=>'/api/'+company.company_id+'/payables'}}]});return {selected,http:TestBed.inject(HttpTestingController)};
}
afterEach(()=>TestBed.resetTestingModule());
describe('Seleção e atribuição de contas',()=>{
  it('cancela a lista anterior ao trocar empresa e consulta apenas contas ativas',()=>{
    const {selected,http}=setup();const fixture=TestBed.createComponent(AccountPicker);fixture.detectChanges();
    const first=http.expectOne(request=>request.url==='/api/a/financial-accounts');expect(first.request.params.get('status')).toBe('ACTIVE');
    selected.set({...selected(),company_id:'b'});fixture.detectChanges();expect(first.cancelled).toBe(true);
    http.expectOne(request=>request.url==='/api/b/financial-accounts').flush({items:[{id:'bank',name:'Caixa'}],next_cursor:null});
    selected.set({...selected(),permissions:[]});fixture.detectChanges();expect(fixture.componentInstance.rows()).toEqual([]);http.verify();fixture.destroy();
  });
  it('não oferece vinculação sem as permissões de gerenciamento e da operação',()=>{
    const {http}=setup(['accounts.read']);const fixture=TestBed.createComponent(LegacyAccountLink);fixture.componentRef.setInput('path','/api/receipt');fixture.componentRef.setInput('kind','receipt');fixture.detectChanges();
    expect(fixture.componentInstance.allowed()).toBe(false);http.expectNone(()=>true);fixture.destroy();
  });
  it('exige a data efetiva e envia o vínculo de um recebimento antigo estornado',async()=>{
    const {http}=setup();const fixture=TestBed.createComponent(LegacyAccountLink);fixture.componentRef.setInput('path','/api/receipt');fixture.componentRef.setInput('kind','receipt');fixture.componentRef.setInput('reversed',true);fixture.detectChanges();
    const component=fixture.componentInstance;component.form.controls.account.setValue('bank');await component.save();expect(component.error()).toContain('data efetiva');http.expectNone(()=>true);
    component.form.controls.reversed_on.setValue('2026-11-06');const save=component.save();const request=http.expectOne('/api/receipt/account');
    expect(request.request.body).toEqual({financial_account_id:'bank',expected_reversed:true,reversed_on:'2026-11-06'});request.flush({linked:true});await save;http.verify();fixture.destroy();
  });
});
