import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProductCatalog, SubscriptionPage } from './subscription';
import { Session } from '../../core/session';

const catalog:ProductCatalog={version:'business-v1-draft',segment:'BUSINESS',published:false,checkout_available:false,
  available_features:['business.payables'],plans:[
    {key:'ESSENTIAL',companies_limit:1,users_limit:3,features:['business.payables']},
    {key:'PROFESSIONAL',companies_limit:5,users_limit:20,features:['business.payables','business.planning']},
    {key:'ENTERPRISE',companies_limit:null,users_limit:null,features:['business.payables','business.planning','business.integrations']},
  ]};
function setup(embedded=false){
  TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting(),provideRouter([]),
    {provide:ActivatedRoute,useValue:{snapshot:{data:{embedded}}}}]});
  return TestBed.inject(HttpTestingController);
}
describe('Página de assinatura',()=>{
  afterEach(()=>TestBed.inject(HttpTestingController).verify());
  it('mostra os três planos e distingue disponibilidade sem oferecer pagamento',async()=>{
    const http=setup(),fixture=TestBed.createComponent(SubscriptionPage);
    http.expectOne('/api/v1/catalog/plans').flush(catalog);await fixture.whenStable();fixture.detectChanges();
    const root=fixture.nativeElement as HTMLElement;
    expect(root.querySelectorAll('.console-options button').length).toBe(3);
    expect(root.textContent).toContain('Contratação em preparação');
    expect(root.textContent).toContain('Implementado');expect(root.textContent).toContain('Planejado');
    expect(root.textContent).toContain('Valores e contratação ainda não estão disponíveis');
    expect(root.querySelector<HTMLDetailsElement>('.comparison-panel')?.open).toBe(false);expect(root.textContent).not.toContain('R$');
    expect(root.querySelector('form')).toBeNull();
    expect(TestBed.inject(Session).token()).toBeNull();
  });
  it('seleciona detalhes agrupados sem ativar acesso nem enviar alteração',async()=>{
    const http=setup(),fixture=TestBed.createComponent(SubscriptionPage);
    http.expectOne('/api/v1/catalog/plans').flush(catalog);await fixture.whenStable();fixture.detectChanges();
    const dialog=fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    dialog.showModal=vi.fn();
    fixture.componentInstance.viewPlan('ENTERPRISE');fixture.detectChanges();
    expect(dialog.showModal).toHaveBeenCalledOnce();
    expect(dialog.querySelector('h2')?.textContent).toBe('Enterprise');
    expect(dialog.textContent).toContain('Integrações contratadas');
    expect(dialog.textContent).not.toContain('Contas a receber');
    expect(TestBed.inject(Session).token()).toBeNull();
    http.expectNone(request=>request.method!=='GET');
  });
  it('integra a mesma página às configurações sem duplicar a navegação externa',async()=>{
    const http=setup(true),fixture=TestBed.createComponent(SubscriptionPage);
    http.expectOne('/api/v1/catalog/plans').flush(catalog);await fixture.whenStable();fixture.detectChanges();
    const root=fixture.nativeElement as HTMLElement;
    expect(root.querySelector('.plans-nav')).toBeNull();
    expect(root.textContent).toContain('Assinatura e planos');
    expect(root.querySelector('.embedded')).not.toBeNull();
  });
  it('erro de rede não fabrica planos, preços ou contrato ativo',async()=>{
    const http=setup(),fixture=TestBed.createComponent(SubscriptionPage);
    http.expectOne('/api/v1/catalog/plans').flush({detail:'privado'},{status:503,statusText:'Unavailable'});
    await fixture.whenStable();fixture.detectChanges();
    expect(fixture.componentInstance.catalog()).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Não foi possível carregar os planos');
    expect(fixture.nativeElement.textContent).not.toContain('privado');
    expect(fixture.nativeElement.querySelectorAll('.console-options button').length).toBe(0);
  });
});
