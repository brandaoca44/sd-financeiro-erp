import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { afterEach, describe, expect, it } from 'vitest';
import { CompanyAccess } from './company-access';
import { Workspaces } from '../../core/workspaces';

afterEach(()=>TestBed.resetTestingModule());
describe('Administração de permissões',()=>{
  it('não consulta diretório nem concessões para usuário sem autoridade',()=>{
    TestBed.configureTestingModule({imports:[CompanyAccess],providers:[provideHttpClient(),provideHttpClientTesting(),
      {provide:Workspaces,useValue:{selected:signal({organization_id:'org',company_id:'a',can_manage_access:false})}}]});
    const fixture=TestBed.createComponent(CompanyAccess);fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('disponível ao Master');
    TestBed.inject(HttpTestingController).expectNone(()=>true);fixture.destroy();
  });
  it('envia a concessão com as revisões atuais e limpa a senha ao trocar empresa',async()=>{
    const selected=signal({organization_id:'org',company_id:'a',can_manage_access:true});
    TestBed.configureTestingModule({imports:[CompanyAccess],providers:[provideHttpClient(),provideHttpClientTesting(),
      {provide:Workspaces,useValue:{selected,label:()=> 'Empresa sintética'}}]});
    const fixture=TestBed.createComponent(CompanyAccess), http=TestBed.inject(HttpTestingController);
    fixture.detectChanges();http.expectOne('/api/v1/organizations/org/members?limit=100').flush({items:[{user_id:'user',name:'Usuário',status:'ACTIVE',revision:2}],next_cursor:null});
    await fixture.whenStable();const component=fixture.componentInstance;
    component.choose({target:{value:'user'}} as unknown as Event);
    http.expectOne('/api/v1/organizations/org/companies/a').flush({revision:3});await Promise.resolve();
    const grants=http.match(request=>request.url.includes('/permissions/'));expect(grants.length).toBe(18);
    grants.forEach(request=>request.flush(null));await new Promise<void>(resolve=>setTimeout(resolve,0));
    http.expectOne('/api/v1/organizations/org/members/user/status').flush({revision:2,status:'ACTIVE'});
    await fixture.whenStable();const action=component.groups[1].actions[0];
    component.open(action);component.form.controls.password.setValue('Senha sintética');
    const save=component.save(action);
    const request=http.expectOne('/api/v1/organizations/org/companies/a/members/user/permissions/billing.read');
    expect(request.request.body).toEqual({status:'ACTIVE',expected_revision:0,expected_company_revision:3,
      expected_membership_revision:2,password:'Senha sintética'});
    expect(component.form.controls.password.value).toBe('');
    selected.set({...selected(),company_id:'b'});fixture.detectChanges();
    http.expectOne('/api/v1/organizations/org/members?limit=100').flush({items:[],next_cursor:null});
    request.flush({status:'ACTIVE',revision:1,effective:true});await save;
    expect(component.confirmation()).toBeNull();expect(component.ready()).toBe(false);expect(component.grants()).toEqual({});
    http.verify();fixture.destroy();
  });
});
