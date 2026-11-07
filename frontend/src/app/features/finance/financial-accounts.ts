import { AccountStatementPanel } from './account-statement';
import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom, timeout } from 'rxjs';
import { BankSelector } from '../../core/bank-selector';
import { ContextHelp } from '../../core/context-help';
import { FinanceApi, money, dateLabel, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';
interface Account {id:string;name:string;kind:'BANK'|'CASH'|'PAYMENT';currency:string;opening_balance:string;opening_date:string;status:string;revision:number}
interface Position {as_of:string;current_balance:string;receipts_amount:string;payments_amount:string;receipt_reversals_amount:string;payment_reversals_amount:string;unassigned_payments:number;unassigned_receipts:number}
interface Bank {institution:string;branch:string|null;account:string}
@Component({selector:'sdf-financial-accounts',imports:[ReactiveFormsModule,BankSelector,ContextHelp,AccountStatementPanel],styles:`
  .account-form {display:grid;gap:1rem;max-width:58rem}.account-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr));gap:1rem}
  .account-form label {display:grid;gap:.4rem;margin:0;min-width:0}.account-form input,.account-form select {width:100%;min-width:0}
  .account-section {padding:1rem;border:1px solid #dce5f0;border-radius:.7rem;background:linear-gradient(145deg,#fff,#f5f8fc)}
  .account-section h3 {margin-top:0}.account-actions {display:flex;justify-content:flex-end;gap:.6rem;flex-wrap:wrap}
  .account-header {display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-bottom:1rem}
  .account-initial {display:grid;gap:.5rem;font-size:.875rem}.account-initial strong {font-size:1.5rem;color:#173762}
`,template:`
  <div class="page-heading"><div><span class="eyebrow">FINANCEIRO</span><h1>Contas financeiras</h1><p class="muted">Contas da empresa e posições iniciais de referência.</p></div></div>
  @if(error()){<p class="alert" role="alert">{{error()}}</p>}
  @if(message()){<p class="notice" role="status">{{message()}}</p>}
  @if(loading()){<p role="status">Consultando contas…</p>}
  @if(!workspaces.can('accounts.read') && !workspaces.can('accounts.manage')){<p class="panel">Seu perfil não permite acessar contas financeiras desta empresa.</p>}
  @else if(creating() || selected()){
    <section class="panel"><div class="account-header"><h2>{{creating()?'Nova conta financeira':'Detalhes da conta'}}</h2>
      <button class="secondary small" type="button" (click)="close()" [disabled]="busy()">Voltar à lista</button></div>
      <form class="account-form" [formGroup]="form" (ngSubmit)="save()">
        <div class="account-grid" [attr.inert]="busy() || pending ? '' : null"><label>Nome da conta<input formControlName="name" maxlength="100"></label>
          @if(creating()){
            <label>Tipo<select formControlName="kind" (change)="kindChanged()"><option value="CASH">Caixa</option>
              @if(workspaces.can('accounts.bank')){<option value="BANK">Conta bancária</option><option value="PAYMENT">Conta de pagamento</option>}
            </select></label>
            <label>Saldo inicial (R$)<input formControlName="opening_balance" inputmode="decimal" maxlength="20" placeholder="0,00"></label>
            <label>Data do saldo inicial<input type="date" formControlName="opening_date" [max]="today"></label>
          }@else{<label>Situação<select formControlName="status"><option value="ACTIVE">Ativa</option><option value="INACTIVE">Inativa</option></select></label>}
        </div>
        @if(selected();as row){<section class="account-section account-initial"><span>{{kindLabel(row.kind)}} · {{row.currency}}</span><strong>{{money(row.opening_balance)}}</strong><span>Saldo inicial de {{date(row.opening_date)}}</span></section>}
        @if(position();as balance){<section class="account-section account-initial"><span>Saldo calculado pelo ERP em {{date(balance.as_of)}}</span><strong>{{money(balance.current_balance)}}</strong>
          <div class="account-grid"><span>Recebimentos: {{money(balance.receipts_amount)}}</span><span>Pagamentos: {{money(balance.payments_amount)}}</span><span>Estornos de recebimentos: {{money(balance.receipt_reversals_amount)}}</span><span>Estornos de pagamentos: {{money(balance.payment_reversals_amount)}}</span></div>
          <p class="muted">Saldo inicial mais movimentos vinculados. A empresa possui {{balance.unassigned_payments}} pagamentos e {{balance.unassigned_receipts}} recebimentos sem vínculo, não incluídos neste saldo.</p></section>}
        @if(positionLoading()){<p role="status">Calculando saldo da conta…</p>}
        @if(positionError()){<p class="field-help">Não foi possível consultar o saldo. <button class="secondary small" type="button" (click)="loadPosition()">Atualizar saldo</button></p>}
        @if(selected() && !canPosition()){<p class="muted">Consultar o saldo calculado exige também leitura de Contas a pagar e Faturamento.</p>}
        @if(creating() && form.controls.kind.value!=='CASH' || bankOpen()){
          <section class="account-section" [attr.inert]="busy() || pending ? '' : null" [formGroup]="bankForm"><h3>Dados bancários</h3><div class="account-grid">
            <div><label id="financial-account-bank">Instituição</label><sdf-bank-selector formControlName="institution" aria-labelledby="financial-account-bank" /></div>
            <label>Agência {{form.controls.kind.value==='PAYMENT'?'(opcional)':''}}<input formControlName="branch" inputmode="numeric" maxlength="30" (input)="digits('branch',$event)"></label>
            <label>Conta com dígito<input formControlName="account" inputmode="numeric" maxlength="30" (input)="digits('account',$event)"></label>
          </div></section>
        }
        @if(selected();as row){@if(row.kind!=='CASH' && workspaces.can('accounts.bank') && !bankOpen()){
          <div><button class="secondary" type="button" (click)="openBank(row)" [disabled]="busy()">{{workspaces.can('accounts.manage')?'Consultar ou editar dados bancários':'Consultar dados bancários'}}</button></div>
        }}
        <p class="muted">O saldo inicial representa a abertura da data informada e fica preservado após o cadastro. Movimentações antigas não serão atribuídas automaticamente a esta conta.</p>
        @if(workspaces.can('accounts.manage')){<div class="account-actions"><button class="secondary" type="button" (click)="close()" [disabled]="busy()">Voltar</button>
          <button class="primary" type="submit" [disabled]="busy() || form.invalid || bankRequired() && bankForm.invalid">{{busy()?'Salvando…':pending?'Confirmar cadastro':creating()?'Cadastrar conta':'Salvar alterações'}}</button></div>}
      </form>
      @if(selected();as row){@if(canPosition()){<sdf-account-statement [accountId]="row.id" [openingDate]="row.opening_date" />}}
    </section>
  }@else{
    <section class="panel register-list"><div class="account-header"><div class="account-header"><h2>Contas cadastradas</h2><sdf-help text="Cadastre uma conta por caixa, banco ou instituição de pagamento. O saldo inicial representa a posição informada em uma data de referência. Pagamentos e recebimentos podem ser vinculados à conta. Consulte saldo e extrato nos detalhes. Inativar preserva o cadastro e seu histórico." /></div>
      <div class="account-actions">@if(workspaces.can('accounts.read')){<button class="secondary" type="button" (click)="load()" [disabled]="loading()">Atualizar</button>}@if(workspaces.can('accounts.manage')){<button class="primary" type="button" (click)="start()">Nova conta</button>}</div>
    </div>
      @if(!workspaces.can('accounts.read')){<p class="muted">Você pode cadastrar contas, mas não possui permissão de consulta.</p>}
      @else if(!loading() && !rows().length){<p class="muted">Nenhuma conta cadastrada nesta empresa.</p>}
      @if(rows().length){<div class="table-scroll"><table><thead><tr><th>Nome</th><th>Tipo</th><th class="numeric">Saldo inicial</th><th>Data de referência</th><th>Situação</th><th>Ações</th></tr></thead>
        <tbody>@for(row of rows();track row.id){<tr><td>{{row.name}}</td><td>{{kindLabel(row.kind)}}</td><td class="numeric">{{money(row.opening_balance)}}</td><td>{{date(row.opening_date)}}</td><td><span class="badge">{{row.status==='ACTIVE'?'Ativa':'Inativa'}}</span></td><td><button class="secondary small" type="button" (click)="open(row)">{{workspaces.can('accounts.manage')?'Editar':'Consultar'}}</button></td></tr>}</tbody>
      </table></div>}
      @if(cursor()){<div class="account-actions"><button class="secondary" (click)="load(true)" [disabled]="loading()">Carregar mais</button></div>}
      <p class="muted">Abra os detalhes para consultar o saldo calculado de cada conta. A lista apresenta as posições iniciais informadas.</p>
    </section>
  }
`})
export class FinancialAccountsPage {
  readonly workspaces=inject(Workspaces);private http=inject(HttpClient);private api=inject(FinanceApi);private generation=0;private positionGeneration=0;
  readonly rows=signal<Account[]>([]);readonly selected=signal<Account|null>(null);readonly creating=signal(false);readonly bankOpen=signal(false);
  readonly position=signal<Position|null>(null);readonly positionLoading=signal(false);readonly positionError=signal(false);
  readonly loading=signal(false);readonly busy=signal(false);readonly error=signal('');readonly message=signal('');readonly cursor=signal<string|null>(null);
  readonly today=today();readonly money=money;readonly date=dateLabel;
  readonly form=inject(FormBuilder).nonNullable.group({name:['',Validators.required],kind:['CASH'],opening_balance:['0,00',[Validators.required,Validators.pattern(/^-?(?:0|[1-9]\d*)(?:[.,]\d{1,2})?$/)]],opening_date:[today(),Validators.required],status:['ACTIVE']});
  readonly bankForm=inject(FormBuilder).nonNullable.group({institution:['',Validators.required],branch:['',Validators.pattern(/^[0-9]+$/)],account:['',[Validators.required,Validators.pattern(/^[0-9]+$/)]]});
  pending:{url:string;key:string;body:object}|null=null;
  constructor(){effect(()=>{this.workspaces.selected();untracked(()=>{this.generation++;this.pending=null;this.selected.set(null);this.creating.set(false);this.bankOpen.set(false);this.bankForm.reset();this.form.reset();this.position.set(null);this.positionLoading.set(false);this.positionError.set(false);this.rows.set([]);this.cursor.set(null);this.error.set('');this.message.set('');this.loading.set(false);void this.load();});});}
  private base(){const company=this.workspaces.selected();return company?this.api.base(company).replace(/payables$/,'financial-accounts'):null;}
  kindLabel(kind:string){return ({BANK:'Conta bancária',CASH:'Caixa',PAYMENT:'Conta de pagamento'} as Record<string,string>)[kind]??kind;}
  bankRequired(){return this.creating()?this.form.controls.kind.value!=='CASH':this.bankOpen();}
  kindChanged(){this.bankForm.reset();const branch=this.bankForm.controls.branch;branch.setValidators(this.form.controls.kind.value==='BANK'?[Validators.required,Validators.pattern(/^[0-9]+$/)]:[Validators.pattern(/^[0-9]+$/)]);branch.updateValueAndValidity();}
  digits(field:'branch'|'account',event:Event){const input=event.target as HTMLInputElement;input.value=input.value.replace(/[^0-9]/g,'');this.bankForm.controls[field].setValue(input.value);}
  close(){if(this.busy())return;this.pending=null;this.selected.set(null);this.creating.set(false);this.bankOpen.set(false);this.bankForm.reset();this.form.reset();this.positionGeneration++;this.position.set(null);this.positionLoading.set(false);this.positionError.set(false);}
  start(){this.close();this.error.set('');this.message.set('');this.form.enable();this.form.reset({kind:'CASH',opening_balance:'0,00',opening_date:today(),status:'ACTIVE'});this.bankForm.enable();this.kindChanged();this.creating.set(true);}
  open(row:Account){this.close();this.error.set('');this.message.set('');this.form.enable();this.form.reset({name:row.name,kind:row.kind,opening_balance:row.opening_balance,opening_date:row.opening_date,status:row.status});this.kindChanged();this.selected.set(row);if(!this.workspaces.can('accounts.manage'))this.form.disable();void this.loadPosition();}
  canPosition(){return this.workspaces.can('accounts.read')&&this.workspaces.can('payables.read')&&this.workspaces.can('billing.read');}
  async loadPosition(){const request=++this.positionGeneration,url=this.base(),row=this.selected(),generation=this.generation;if(!url||!row||!this.canPosition())return;this.position.set(null);this.positionLoading.set(true);this.positionError.set(false);
    try{const value=await firstValueFrom(this.http.get<Position>(url+'/'+row.id+'/position').pipe(timeout(15000)));if(request===this.positionGeneration&&generation===this.generation&&this.selected()?.id===row.id)this.position.set(value);}
    catch{if(request===this.positionGeneration&&generation===this.generation&&this.selected()?.id===row.id)this.positionError.set(true);}
    finally{if(request===this.positionGeneration&&generation===this.generation&&this.selected()?.id===row.id)this.positionLoading.set(false);}}
  async openBank(row:Account){const url=this.base(),generation=this.generation;if(!url||!this.workspaces.can('accounts.bank')||this.busy())return;this.busy.set(true);this.error.set('');
    try{const bank=await firstValueFrom(this.http.get<Bank>(url+'/'+row.id+'/bank-details').pipe(timeout(15000)));
      if(generation===this.generation&&this.selected()?.id===row.id){this.bankForm.enable();this.bankForm.reset({...bank,branch:bank.branch??''});if(!this.workspaces.can('accounts.manage'))this.bankForm.disable();this.bankOpen.set(true);}}
    catch{if(generation===this.generation)this.error.set('Não foi possível consultar os dados bancários.');}finally{this.busy.set(false);}}
  async load(more=false){const url=this.base(),generation=this.generation;if(!url||!this.workspaces.can('accounts.read'))return;this.loading.set(true);this.error.set('');
    const params:Record<string,string>={limit:'50'};if(more&&this.cursor())params['cursor']=this.cursor()!;
    try{const page=await firstValueFrom(this.http.get<{items:Account[];next_cursor:string|null}>(url,{params}).pipe(timeout(15000)));
      if(generation===this.generation){this.rows.set(more?[...this.rows(),...page.items]:page.items);this.cursor.set(page.next_cursor);}}
    catch{if(generation===this.generation){this.rows.set([]);this.error.set('Não foi possível consultar as contas financeiras.');}}finally{if(generation===this.generation)this.loading.set(false);}}
  async save(){const url=this.base(),row=this.selected(),generation=this.generation;if(!url||!this.workspaces.can('accounts.manage')||this.busy()||this.form.invalid||this.bankRequired()&&this.bankForm.invalid)return;
    const value=this.form.getRawValue();const bank=this.bankForm.getRawValue();const details={institution:bank.institution,branch:bank.branch||null,account:bank.account};
    const body=this.creating()?{name:value.name,kind:value.kind,opening_balance:value.opening_balance.replace(',','.'),opening_date:value.opening_date,...(value.kind!=='CASH'?{bank_details:details}:{})}
      :{name:value.name,status:value.status,expected_revision:row!.revision,...(this.bankOpen()?{bank_details:details}:{})};
    const attempt=this.pending??{url,key:crypto.randomUUID(),body};if(attempt.url!==url)return;
    if(this.creating())this.pending=attempt;this.busy.set(true);this.error.set('');
    try{await firstValueFrom((this.creating()?this.http.post(url,attempt.body,{headers:{'Idempotency-Key':attempt.key}}):this.http.put(url+'/'+row!.id,body)).pipe(timeout(15000)));
      if(generation===this.generation){this.pending=null;this.busy.set(false);this.close();this.message.set('Conta financeira salva.');this.api.revision.update(value=>value+1);await this.load();}}
    catch(failure){if(generation===this.generation){const status=(failure as {status?:number}).status;if(status&&status>=400&&status<500)this.pending=null;
      this.error.set(status===409?'A conta foi alterada. Atualize a lista antes de editar novamente.':this.pending?'Envio sem confirmação. Tente novamente para confirmar o mesmo cadastro.':'Não foi possível salvar. Confira os campos e sua autorização.');}}
    finally{this.busy.set(false);}}
}
