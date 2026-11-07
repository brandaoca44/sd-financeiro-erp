import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReceivablesSummaryPanel } from './receivables-summary';
import { Overview } from './overview';
import { Workspaces } from '../../core/workspaces';
import { FinanceApi } from '../../core/finance';
const report={as_of:'2026-11-06',month:'2026-11-01',upcoming_days:7,outstanding_amount:'965.00',outstanding_count:5,
  overdue_amount:'140.00',overdue_count:2,due_today_amount:'150.00',due_today_count:1,upcoming_amount:'275.00',upcoming_count:1,received_amount:'615.00',received_count:4};
function setup(permissions:string[]=['billing.read'],overview=false){
  const selected=signal({organization_id:'org',company_id:'a',permissions});
  const api={revision:signal(0),base:(company:{company_id:string})=>'/api/'+company.company_id+'/payables',summary:vi.fn()};
  TestBed.configureTestingModule({imports:[overview?Overview:ReceivablesSummaryPanel],providers:[provideRouter([]),provideHttpClient(),provideHttpClientTesting(),
    {provide:Workspaces,useValue:{selected,can:(key:string)=>selected().permissions.includes(key)}},{provide:FinanceApi,useValue:api}]});
  return {selected,api,http:TestBed.inject(HttpTestingController)};
}
afterEach(()=>TestBed.resetTestingModule());
describe('Indicadores de contas a receber',()=>{
  it('não consulta sem billing.read',()=>{const {http}=setup(['payables.read']);const fixture=TestBed.createComponent(ReceivablesSummaryPanel);fixture.detectChanges();
    http.expectNone(()=>true);expect(fixture.componentInstance.report()).toBeNull();fixture.destroy();});
  it('cancela consultas da empresa anterior e limpa valores ao perder acesso',()=>{
    const {selected,http}=setup();const fixture=TestBed.createComponent(ReceivablesSummaryPanel);fixture.detectChanges();
    const first=http.expectOne(request=>request.url==='/api/a/receivables-summary');
    selected.set({...selected(),company_id:'b'});fixture.detectChanges();expect(first.cancelled).toBe(true);
    http.expectOne(request=>request.url==='/api/b/receivables-summary').flush(report);fixture.detectChanges();
    expect(fixture.componentInstance.report()?.outstanding_amount).toBe('965.00');
    selected.set({...selected(),permissions:[]});fixture.detectChanges();
    expect(fixture.componentInstance.report()).toBeNull();http.expectNone(()=>true);http.verify();fixture.destroy();
  });
  it('atualiza por mês e após uma movimentação financeira',()=>{
    const {http,api}=setup();const fixture=TestBed.createComponent(ReceivablesSummaryPanel);fixture.detectChanges();
    http.expectOne(request=>request.url.endsWith('/receivables-summary')).flush(report);
    fixture.componentInstance.month.set('2026-10');fixture.detectChanges();
    const october=http.expectOne(request=>request.params.get('month')==='2026-10');expect(fixture.componentInstance.report()).toBeNull();
    october.flush({...report,month:'2026-10-01',received_amount:'20.00'});
    api.revision.update(value=>value+1);fixture.detectChanges();
    http.expectOne(request=>request.params.get('month')==='2026-10').flush({...report,month:'2026-10-01'});
    http.verify();fixture.destroy();
  });
  it('abre a visão financeira para billing.read sem consultar pagamentos ou resultado',async()=>{
    const {http,api}=setup(['billing.read'],true);const fixture=TestBed.createComponent(Overview);fixture.detectChanges();
    http.expectOne(request=>request.url==='/api/a/receivables-summary').flush(report);await fixture.whenStable();fixture.detectChanges();
    expect(api.summary).not.toHaveBeenCalled();expect(fixture.nativeElement.textContent).toContain('Recebidos no mês');
    expect(fixture.nativeElement.textContent).not.toContain('Consulta financeira restrita');
    expect(fixture.nativeElement.textContent).not.toContain('Resultado por competência');
    http.verify();fixture.destroy();
  });
});
