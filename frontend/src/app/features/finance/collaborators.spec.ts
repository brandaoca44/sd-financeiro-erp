import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { afterEach, describe, expect, it } from 'vitest';
import { Collaborators } from './collaborators';
import { Workspaces } from '../../core/workspaces';

const base='/api/v1/organizations/org/companies/company/collaborators';
const row={id:'person',name:'Pessoa sintética',job_title:'Analista financeiro',employment_type:null,work_model:null,
  admission_date:null,termination_date:null,termination_reason:null};
function setup(permissions:string[]){
  TestBed.configureTestingModule({imports:[Collaborators],providers:[provideHttpClient(),provideHttpClientTesting(),
    {provide:Workspaces,useValue:{selected:signal({organization_id:'org',company_id:'company'}),can:(key:string)=>permissions.includes(key)}}]});
  const fixture=TestBed.createComponent(Collaborators), http=TestBed.inject(HttpTestingController);
  fixture.detectChanges();http.expectOne(base).flush([row]);return {fixture,http};
}
afterEach(()=>TestBed.resetTestingModule());
describe('Permissões de colaboradores no cliente',()=>{
  it('omite documentos, salário e banco no envio de uma edição básica',async()=>{
    const {fixture,http}=setup(['people.read','people.update']);await fixture.whenStable();
    const component=fixture.componentInstance;
    const edit=component.edit(row);http.expectOne(base+'/person/details').flush({});await edit;
    component.form.controls.name.setValue('Nome atualizado');
    const save=component.save();const request=http.expectOne(base+'/person');
    expect(request.request.method).toBe('PUT');expect(request.request.body.details).toEqual({});
    request.flush({...row,name:'Nome atualizado'});await Promise.resolve();
    http.expectOne(base).flush([{...row,name:'Nome atualizado'}]);await save;http.verify();fixture.destroy();
  });
  it('esconde cadastro e desligamento de quem tem somente consulta',async()=>{
    const {fixture,http}=setup(['people.read']);await fixture.whenStable();fixture.detectChanges();
    expect(fixture.componentInstance.canCreate()).toBe(false);
    expect([...fixture.nativeElement.querySelectorAll('button')].filter((button:any)=>!button.hidden)
      .some((button:any)=>button.textContent.trim()==='Desligar')).toBe(false);
    const edit=fixture.componentInstance.edit(row);http.expectOne(base+'/person/details').flush({});await edit;
    expect(fixture.componentInstance.form.disabled).toBe(true);http.verify();fixture.destroy();
  });
});
