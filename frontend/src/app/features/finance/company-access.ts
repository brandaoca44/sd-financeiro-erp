import { Component, effect, inject, signal, untracked } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { Workspaces, Permission } from '../../core/workspaces';

interface Member {user_id:string; name:string; status:string; revision:number}
interface Grant {status:string; revision:number; effective:boolean}
interface Action {key:Permission; label:string}

@Component({selector:'sdf-company-access', imports:[ReactiveFormsModule], styles:`
  .access-selector {display:grid; gap:.5rem; max-width:34rem; margin-bottom:1.25rem}
  .access-groups {display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,21rem),1fr)); gap:1rem}
  .access-group {margin:0; padding:1.25rem; min-width:0}
  .access-row {display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:.85rem 0; border-top:1px solid #e3eaf4}
  .access-row span {display:grid; gap:.25rem; font-size:.875rem; color:#173762}
  .access-row small {font-size:.75rem; color:#64748b}
  .access-confirm {max-width:36rem; display:grid; gap:1rem; margin-bottom:1rem}
  .access-actions {display:flex; justify-content:flex-end; gap:.6rem}
`, template:`
  <div class="page-heading"><div><span class="eyebrow">CONFIGURAÇÕES</span><h1>Permissões da empresa</h1>
    <p class="muted">Defina as ações de cada usuário na empresa selecionada.</p></div></div>
  @if (error()) {<p role="alert" class="alert">{{error()}}</p>}
  @if (message()) {<p role="status" class="notice">{{message()}}</p>}
  @if (!workspaces.selected()?.can_manage_access) {
    <p class="panel">A administração de permissões está disponível ao Master da organização.</p>
  } @else {
    <div class="access-selector">
      <label for="access-member">Usuário da organização</label>
      <select id="access-member" [value]="memberId()" (change)="choose($event)" [disabled]="loading() || busy()">
        <option value="">Selecione um usuário</option>
        @for (member of members(); track member.user_id) {<option [value]="member.user_id">{{member.name}} · {{member.status === 'ACTIVE' ? 'Ativo' : 'Inativo'}}</option>}
      </select>
      @if (cursor()) {<button class="secondary small" (click)="loadMembers(true)" [disabled]="loading() || busy()">Carregar mais usuários</button>}
    </div>
    @if (loading()) {<p role="status">Consultando permissões…</p>}
    @if (confirmation(); as action) {
      <form class="panel access-confirm" [formGroup]="form" (ngSubmit)="save(action)">
        <h2>{{grants()[action.key]?.status === 'ACTIVE' ? 'Revogar' : 'Conceder'}} acesso</h2>
        <p>{{action.label}} · {{selectedMember()?.name}}</p>
        <p class="muted">{{companyLabel()}}</p>
        <label>Confirme sua senha<input type="password" formControlName="password" autocomplete="current-password" maxlength="128"></label>
        <div class="access-actions"><button class="secondary" type="button" (click)="cancel()" [disabled]="busy()">Voltar</button>
          <button class="primary" type="submit" [disabled]="busy() || form.invalid">{{busy() ? 'Salvando…' : 'Confirmar alteração'}}</button></div>
      </form>
    }
    @if (ready()) {
      <p class="muted">O Master mantém acesso à própria organização. Cargos não concedem permissões. As operações também dependem de vínculo, empresa e contrato ativos.</p>
      <div class="access-groups">
        @for (group of groups; track group.label) {
          <section class="panel access-group"><h2>{{group.label}}</h2>
            @for (action of group.actions; track action.key) {
              @let grant = grants()[action.key];
              <div class="access-row"><span>{{action.label}}<small>{{grant?.effective ? 'Ativo' : grant?.status === 'ACTIVE' ? 'Concedido · sem efeito no contexto atual' : 'Sem concessão'}}</small></span>
                <button class="secondary small" type="button" (click)="open(action)" [disabled]="busy() || loading() || !!confirmation()">{{grant?.status === 'ACTIVE' ? 'Revogar' : 'Conceder'}}</button></div>
            }
          </section>
        }
      </div>
    }
  }
`})
export class CompanyAccess {
  readonly workspaces=inject(Workspaces); private http=inject(HttpClient);
  readonly members=signal<Member[]>([]); readonly memberId=signal(''); readonly cursor=signal<string|null>(null);
  readonly grants=signal<Partial<Record<Permission,Grant|null>>>({}); readonly loading=signal(false); readonly busy=signal(false);
  readonly ready=signal(false); readonly error=signal(''); readonly message=signal(''); readonly confirmation=signal<Action|null>(null);
  readonly form=inject(FormBuilder).nonNullable.group({password:['',[Validators.required,Validators.maxLength(128)]]});
  private generation=0; private companyRevision=0;
  readonly groups:{label:string;actions:Action[]}[]=[
    {label:'Contas a pagar e despesas',actions:[{key:'payables.read',label:'Consultar'},{key:'payables.manage',label:'Cadastrar, editar e cancelar'},{key:'payables.settle',label:'Registrar pagamentos'},{key:'payables.reverse',label:'Estornar pagamentos'}]},
    {label:'Faturamento',actions:[{key:'billing.read',label:'Consultar faturamento e cobranças'},{key:'billing.manage',label:'Cadastrar clientes e faturamento'},{key:'billing.receive',label:'Registrar recebimentos'},{key:'billing.reverse',label:'Estornar recebimentos'}]},
    {label:'Contas financeiras da empresa',actions:[{key:'accounts.read',label:'Consultar contas e saldos iniciais'},{key:'accounts.manage',label:'Cadastrar, editar e inativar contas'},{key:'accounts.bank',label:'Acessar dados bancários da empresa'}]},
    {label:'Colaboradores',actions:[{key:'people.read',label:'Consultar cadastro profissional'},{key:'people.create',label:'Cadastrar colaboradores'},{key:'people.update',label:'Editar colaboradores'},{key:'people.terminate',label:'Registrar desligamentos'}]},
    {label:'Dados protegidos de colaboradores',actions:[{key:'people.documents',label:'Documentos, contato e endereço'},{key:'people.compensation',label:'Remuneração e prévia de folha'},{key:'people.bank',label:'Dados bancários e Pix'}]},
  ];
  constructor(){effect(()=>{const company=this.workspaces.selected();untracked(()=>{
    this.generation++;this.members.set([]);this.memberId.set('');this.cursor.set(null);this.ready.set(false);this.grants.set({});this.cancel();this.error.set('');this.message.set('');
    if(company?.can_manage_access)void this.loadMembers();
  });});}
  companyLabel(){const company=this.workspaces.selected();return company?this.workspaces.label(company):'';}
  selectedMember(){return this.members().find(row=>row.user_id===this.memberId());}
  private base(){const company=this.workspaces.selected();return company?`/api/v1/organizations/${company.organization_id}`:null;}
  private get<T>(url:string){return firstValueFrom(this.http.get<T>(url).pipe(timeout(15000)));}
  async loadMembers(more=false){const base=this.base(), generation=this.generation;if(!base)return;this.loading.set(true);this.error.set('');
    try{const page=await this.get<{items:Member[];next_cursor:string|null}>(base+'/members?limit=100'+(more&&this.cursor()?'&cursor='+encodeURIComponent(this.cursor()!):''));
      if(generation===this.generation){this.members.set(more?[...this.members(),...page.items]:page.items);this.cursor.set(page.next_cursor);}
    }catch{if(generation===this.generation)this.error.set('Não foi possível consultar os usuários desta organização.');}
    finally{if(generation===this.generation)this.loading.set(false);}}
  choose(event:Event){this.memberId.set((event.target as HTMLSelectElement).value);this.cancel();void this.loadGrants();}
  private async loadGrants(){const base=this.base(), company=this.workspaces.selected(), member=this.memberId(), generation=++this.generation;
    this.ready.set(false);this.grants.set({});if(!base||!company||!member)return;this.loading.set(true);this.error.set('');
    try{const companyData=await this.get<{revision:number}>(base+'/companies/'+company.company_id);
      const entries=await Promise.all(this.groups.flatMap(group=>group.actions).map(async action=>[action.key,await this.get<Grant|null>(base+'/companies/'+company.company_id+'/members/'+member+'/permissions/'+action.key)] as const));
      const membership=await this.get<{revision:number;status:string}>(base+'/members/'+member+'/status');
      if(generation===this.generation){this.companyRevision=companyData.revision;this.members.update(rows=>rows.map(row=>row.user_id===member?{...row,...membership}:row));this.grants.set(Object.fromEntries(entries));this.ready.set(true);}
    }catch{if(generation===this.generation)this.error.set('Não foi possível consultar as permissões. Atualize a empresa e tente novamente.');}
    finally{if(generation===this.generation)this.loading.set(false);}}
  open(action:Action){this.message.set('');this.form.reset();this.confirmation.set(action);}
  cancel(){this.confirmation.set(null);this.form.reset();}
  async save(action:Action){const company=this.workspaces.selected(), member=this.selectedMember(), base=this.base(), generation=this.generation;
    if(!company||!member||!base||this.busy()||this.form.invalid||!this.ready())return;
    const grant=this.grants()[action.key];this.busy.set(true);this.error.set('');
    const body={status:grant?.status==='ACTIVE'?'INACTIVE':'ACTIVE',expected_revision:grant?.revision??0,
      expected_company_revision:this.companyRevision,expected_membership_revision:member.revision,password:this.form.getRawValue().password};
    this.form.reset();
    try{await firstValueFrom(this.http.put(base+'/companies/'+company.company_id+'/members/'+member.user_id+'/permissions/'+action.key,body).pipe(timeout(15000)));
      if(generation===this.generation){this.cancel();this.message.set('Permissão atualizada.');await this.loadGrants();}
    }catch(failure){if(generation===this.generation){const status=(failure as {status?:number}).status;this.error.set(status===409?'Os dados foram alterados. Selecione o usuário novamente antes de tentar.':status===429?'Muitas tentativas. Aguarde antes de tentar novamente.':'Não foi possível alterar o acesso. Confira sua senha e a situação do usuário.');}}
    finally{this.busy.set(false);}}
}
