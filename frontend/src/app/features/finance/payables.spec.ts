import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Payables } from './payables';
import { Session } from '../../core/session';
import { Workspaces, Workspace } from '../../core/workspaces';
import { FinanceApi, Title } from '../../core/finance';

describe('Operações financeiras no cliente',()=>{
  const workspace:Workspace={organization_id:'00000000-0000-0000-0000-000000000001',company_id:'00000000-0000-0000-0000-000000000002',company_name:'Empresa sintética',permissions:['payables.read','payables.manage','payables.settle','payables.reverse']};
  const title:Title={id:'00000000-0000-0000-0000-000000000003',description:'Despesa sintética',amount:'100.00',issue_date:'2026-11-01',due_date:'2026-11-10',revision:1,status:'OPEN'};
  let api:{revision:ReturnType<typeof signal<number>>;titles:ReturnType<typeof vi.fn>;write:ReturnType<typeof vi.fn>};
  beforeEach(()=>{api={revision:signal(0),titles:vi.fn().mockResolvedValue({items:[],next_cursor:null}),write:vi.fn()};TestBed.configureTestingModule({imports:[Payables],providers:[provideRouter([]),provideHttpClient(),provideHttpClientTesting(),{provide:FinanceApi,useValue:api}]});TestBed.inject(Session).token.set('token');TestBed.inject(Workspaces).items.set([workspace]);TestBed.inject(Workspaces).selected.set(workspace);});
  it('reutiliza a mesma chave e payload após resultado desconhecido',async()=>{
    const fixture=TestBed.createComponent(Payables);fixture.detectChanges();const component=fixture.componentInstance;
    component.open('pay',title);component.form.patchValue({amount:'40,00',occurred_on:'2026-11-02'});api.write.mockRejectedValueOnce(new HttpErrorResponse({status:0}));await component.submit();expect(component.pending()).not.toBeNull();
    const original=api.write.mock.calls[0];component.form.patchValue({amount:'99,00'});api.write.mockResolvedValueOnce({});await component.submit();const retry=api.write.mock.calls[1];expect(retry[4]).toBe(original[4]);expect(retry[2]).toEqual(original[2]);expect(retry[2]['amount']).toBe('40.00');fixture.destroy();
  });
  it('orienta novos lançamentos para Despesas', () => {
    const fixture = TestBed.createComponent(Payables);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Cadastre novas cobranças em Despesas');
    expect(fixture.nativeElement.textContent).not.toContain('Novo título');
  });
  it('descarta títulos de uma empresa quando a resposta chega depois da troca',async()=>{
    let resolveOld!:(value:unknown)=>void;api.titles.mockImplementationOnce(()=>new Promise(resolve=>resolveOld=resolve));
    const fixture=TestBed.createComponent(Payables);fixture.detectChanges();TestBed.inject(Workspaces).selected.set({...workspace,company_id:'00000000-0000-0000-0000-000000000009'});fixture.detectChanges();await Promise.resolve();resolveOld({items:[title],next_cursor:null});await Promise.resolve();await Promise.resolve();expect(fixture.componentInstance.page()?.items || []).toEqual([]);fixture.destroy();
  });
});
