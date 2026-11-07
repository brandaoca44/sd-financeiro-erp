import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { afterEach,describe,expect,it } from 'vitest';
import { CashflowPage } from './cashflow';
import { Workspaces } from '../../core/workspaces';
import { FinanceApi } from '../../core/finance';
const report={as_of:'2026-11-10',start:'2026-11-01',end:'2026-11-10',totals:{realized_in:'50.00',realized_out:'25.00',pending_in:'150.00',pending_out:'75.00',realized_net:'25.00',projected_net:'100.00'},days:[]};
function setup(permissions=['billing.read','payables.read']){const selected=signal({organization_id:'org',company_id:'a',permissions});const revision=signal(0);
  TestBed.configureTestingModule({imports:[CashflowPage],providers:[provideHttpClient(),provideHttpClientTesting(),{provide:Workspaces,useValue:{selected,can:(key:string)=>selected().permissions.includes(key)}},
    {provide:FinanceApi,useValue:{revision,base:(company:{company_id:string})=>'/api/'+company.company_id+'/payables'}}]});
  const fixture=TestBed.createComponent(CashflowPage),http=TestBed.inject(HttpTestingController);fixture.detectChanges();return {fixture,http,selected,revision};}
afterEach(()=>TestBed.resetTestingModule());
describe('Fluxo de caixa consolidado',()=>{
  it('não consulta com acesso a apenas uma das áreas',()=>{const {fixture,http}=setup(['billing.read']);expect(fixture.nativeElement.textContent).toContain('Consulta consolidada restrita');http.expectNone(()=>true);fixture.destroy();});
  it('cancela consulta antiga e elimina dados ao trocar empresa ou perder acesso',()=>{
    const {fixture,http,selected}=setup();const old=http.expectOne(request=>request.url==='/api/a/cashflow');
    selected.set({...selected(),company_id:'b'});fixture.detectChanges();expect(old.cancelled).toBe(true);
    http.expectOne(request=>request.url==='/api/b/cashflow').flush(report);fixture.detectChanges();expect(fixture.componentInstance.report()?.totals.projected_net).toBe('100.00');
    selected.set({...selected(),permissions:['payables.read']});fixture.detectChanges();expect(fixture.componentInstance.report()).toBeNull();http.expectNone(()=>true);fixture.destroy();});
  it('aplica período válido e atualiza após movimentação',()=>{const {fixture,http,revision}=setup();http.expectOne(request=>request.url.endsWith('/cashflow')).flush(report);
    const component=fixture.componentInstance;component.form.setValue({start:'2026-11-05',end:'2026-11-10'});component.apply();fixture.detectChanges();
    const next=http.expectOne(request=>request.params.get('start')==='2026-11-05');expect(component.report()).toBeNull();next.flush(report);
    revision.update(value=>value+1);fixture.detectChanges();http.expectOne(request=>request.params.get('end')==='2026-11-10').flush(report);http.verify();fixture.destroy();});
  it('rejeita período longo sem enviar consulta',()=>{const {fixture,http}=setup();http.expectOne(request=>request.url.endsWith('/cashflow')).flush(report);
    const component=fixture.componentInstance;component.form.setValue({start:'2026-01-01',end:'2026-12-31'});component.apply();fixture.detectChanges();
    expect(component.error()).toContain('93 dias');http.expectNone(()=>true);fixture.destroy();});
});
