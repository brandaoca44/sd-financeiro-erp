import { AccountPicker } from '../../core/account-picker';
import { LegacyAccountLink } from '../../core/legacy-account-link';
import { toSignal } from '@angular/core/rxjs-interop';
import { MonthlyPayments } from './monthly-payments';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ExpenseOrigin, FinanceApi, Movement, Page, Position, Title, money, dateLabel, today } from '../../core/finance';
import { Workspaces } from '../../core/workspaces';
import { Session, errorMessage } from '../../core/session';

type Action='edit'|'cancel'|'pay'|'reverse';
interface Pending {key:string;path:string;body:Record<string,unknown>}
@Component({selector:'sdf-payables',imports:[ReactiveFormsModule,RouterLink,MonthlyPayments,AccountPicker,LegacyAccountLink],template:`
<div class="page-heading"><div><span class="eyebrow">GESTÃO DAS OBRIGAÇÕES</span><h1>Contas a pagar</h1><p class="muted">Acompanhe vencimentos, saldos e baixas. Cadastre novas cobranças em Despesas.</p></div></div>
@if(error()){<div class="alert" role="alert">{{error()}}</div>}@if(success()){<div class="notice success" role="status">{{success()}}</div>}
@if(!workspaces.can('payables.read')){<div class="empty-state"><h2>Consulta restrita ao seu perfil</h2><p>Você pode executar somente as operações autorizadas pelo Master.<br>A permissão de lançamento não inclui a consulta dos títulos.</p></div>}@else{
<nav class="table-tools" aria-label="Seções de contas a pagar">
  <button class="secondary" type="button" [attr.aria-pressed]="!showPayments()" (click)="showTitles()">Títulos da empresa</button>
  <button class="secondary" type="button" [attr.aria-pressed]="showPayments()" (click)="openMonthlyPayments()">Pagamentos do mês</button>
</nav>
@if(showPayments()){<sdf-monthly-payments />}@else if(!detailTitle()){
<section class="panel register-list"><div class="table-toolbar"><div><h2>Títulos da empresa</h2><p>Consulte detalhes para acompanhar saldos e movimentos.</p></div><div class="table-tools"><label class="sr-only" for="status-filter">Situação cadastral</label><select id="status-filter" (change)="filter($event)"><option value="">Todas as situações</option><option value="OPEN">Ativos</option><option value="CANCELLED">Cancelados</option></select><button class="secondary" (click)="refresh()" [disabled]="busy()">Atualizar</button></div></div>
@if(busy()){<div class="loading-strip" role="status">Carregando títulos…</div>}
<div class="table-scroll"><table><thead><tr><th>Descrição</th><th>Vencimento</th><th class="numeric">Valor original</th><th>Situação cadastral</th><th><span class="sr-only">Operações</span></th></tr></thead><tbody>
@for(title of page()?.items || [];track title.id){<tr><td><strong>{{title.description}}</strong><small>Emissão {{date(title.issue_date)}}</small></td><td>{{date(title.due_date)}}</td><td class="numeric amount">{{money(title.amount)}}</td><td><span class="badge" [class.cancelled]="title.status==='CANCELLED'">{{title.status==='OPEN'?'Ativo':'Cancelado'}}</span></td><td class="row-actions"><button class="text-button" (click)="details(title)">Detalhes</button>@if(title.status==='OPEN' && workspaces.can('payables.settle')){<button class="text-button" (click)="open('pay',title)">Baixar</button>}</td></tr>}
@if(!busy() && !page()?.items?.length){<tr><td colspan="5"><div class="table-empty"><span>◇</span><h3>Nenhum título neste filtro</h3><p>Os títulos cadastrados nesta empresa aparecerão aqui.</p></div></td></tr>}</tbody></table></div>
<div class="table-footer"><span>{{page()?.items?.length || 0}} títulos nesta página</span><div><button class="secondary small" (click)="previous()" [disabled]="!history.length || busy()">Anterior</button><button class="secondary small" (click)="next()" [disabled]="!page()?.next_cursor || busy()">Próxima</button></div></div></section>}}
@if(detailTitle();as title){<section class="panel detail-panel"><div class="panel-heading"><div><span class="eyebrow">DETALHES DO TÍTULO</span><h2>{{title.description}}</h2></div><button class="icon-button" (click)="showTitles()" aria-label="Voltar à lista de títulos">×</button></div>
@if(detailBusy()){<p role="status">Carregando movimentos…</p>}@else{<div class="detail-summary"><div><span>Valor original</span><strong>{{money(title.amount)}}</strong></div><div><span>Líquido pago</span><strong>{{money(position()?.paid_amount || '0.00')}}</strong></div><div><span>Saldo em aberto</span><strong>{{money(position()?.outstanding_amount || '0.00')}}</strong></div></div>@if(origin(); as expense){
  <h3>Despesa de origem</h3>
  <dl class="detail-summary">
    <div><dt>Categoria</dt><dd>{{originLabel(expense.category)}}</dd></div>
    <div><dt>Fornecedor</dt><dd>{{expense.supplier}}</dd></div>
    <div><dt>Comprovante</dt><dd>{{originLabel(expense.document_type)}} {{expense.document_reference}}</dd></div>
  </dl>
  <p><a class="secondary small" routerLink="../expenses" [queryParams]="{view:'registered', expense:expense.id}">Ver despesa vinculada</a></p>
}@else{
  <p class="muted">Título registrado sem despesa vinculada.</p>
  @if(title.status==='OPEN' && workspaces.can('payables.manage')){
    <p><button class="secondary small" (click)="open('edit',title)">Editar título</button></p>
  }
}
<h3>Histórico de movimentos</h3><div class="table-scroll"><table><thead><tr><th>Data</th><th>Movimento</th><th class="numeric">Valor</th><th>Motivo / operação</th></tr></thead><tbody>@for(movement of movements();track movement.id){<tr><td>{{date(movement.occurred_on)}}</td><td>{{movement.kind==='PAYMENT'?'Baixa manual':'Estorno'}}</td><td class="numeric">{{money(movement.amount)}}</td><td>{{movement.reversal_reason || ''}}<small>{{movement.financial_account_id?'Conta vinculada':'Sem vínculo com conta'}}</small>@if(!movement.financial_account_id && movement.kind==='PAYMENT'){<sdf-legacy-account-link kind="payment" [path]="movementPath(title.id,movement.id)" [revision]="title.revision" (saved)="details(title)" />}@if(title.status==='OPEN' && movement.kind==='PAYMENT' && !isReversed(movement.id) && workspaces.can('payables.reverse')){<button class="text-button danger-text" (click)="open('reverse',title,movement)">Estornar</button>}</td></tr>}@if(!movements().length){<tr><td colspan="4" class="muted">Nenhum movimento registrado.</td></tr>}</tbody></table></div>@if(movementCursor()){<button class="text-button" (click)="moreMovements()">Carregar mais movimentos</button>}@if(title.status==='OPEN' && workspaces.can('payables.manage')){<button class="secondary danger-text" (click)="open('cancel',title)">Cancelar título</button>}}</section>}
@if(action();as mode){<div class="modal-backdrop"><section class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" tabindex="-1" (keydown)="trap($event)"><div class="panel-heading"><div><span class="eyebrow">CONTAS A PAGAR</span><h2 id="dialog-title">{{labels[mode]}}</h2></div><button class="icon-button" type="button" (click)="close()" [disabled]="saving()" aria-label="Fechar operação">×</button></div>
@if(target()){<p class="muted dialog-description">{{target()?.description}}</p>}
@if(dialogError()){<div class="alert" role="alert">{{dialogError()}}</div>}
<form [formGroup]="form" (ngSubmit)="submit()"><fieldset [disabled]="saving() || !!pending()">
@if(mode==='edit'){<label for="description">Descrição</label><input id="description" formControlName="description" maxlength="300" placeholder="Ex.: prestação de serviço"><div class="form-grid"><label>Emissão<input type="date" formControlName="issue_date"></label><label>Vencimento<input type="date" formControlName="due_date"></label></div>}
@if(mode==='edit' || mode==='pay'){<label for="amount">{{mode==='pay'?'Valor da baixa':'Valor do título'}}</label><div class="currency-input"><span>R$</span><input id="amount" formControlName="amount" inputmode="decimal" maxlength="19" placeholder="0,00"></div><small class="field-help">Até duas casas decimais, sem separador de milhar.</small>}
@if(mode==='pay' || mode==='reverse'){<label for="occurred">{{mode==='pay'?'Data do pagamento informado':'Data do estorno'}}</label><input id="occurred" type="date" formControlName="occurred_on" [max]="today()"><p class="info-note">Esta operação registra uma informação no ERP. Nenhuma transferência bancária será executada.</p>}
@if(mode==='pay'){<sdf-account-picker formControlName="financial_account_id" />}
@if(mode==='reverse'){<p class="field-help">O estorno usa a conta do pagamento original.</p><label for="reason">Motivo do estorno</label><textarea id="reason" formControlName="reason" maxlength="300" rows="3" placeholder="Informe o motivo da correção"></textarea><p>O estorno será integral: <strong>{{money(payment()?.amount || '')}}</strong>.</p>}
@if(mode==='cancel'){<p>O título será cancelado, preservando seu histórico. Títulos com valor líquido pago não podem ser cancelados.</p>}</fieldset>
@if(pending()){<p class="field-help">A tentativa será repetida com a mesma referência e os mesmos dados.</p>}
<div class="dialog-footer"><button class="secondary" type="button" (click)="close()" [disabled]="saving()">Voltar</button><button class="primary" type="submit" [disabled]="saving() || form.invalid">{{saving()?'Confirmando…':pending()?'Tentar novamente':'Confirmar'}}</button></div></form></section></div>}
`})
export class Payables {
  private readonly routeParams = toSignal(inject(ActivatedRoute).queryParamMap);
  readonly workspaces=inject(Workspaces);private api=inject(FinanceApi);private session=inject(Session);private generation=0;private detailGeneration=0;
  readonly page=signal<Page<Title>|null>(null);readonly busy=signal(false);readonly error=signal('');readonly success=signal('');
  readonly showPayments=signal(false);
  showTitles():void { this.detailGeneration++; this.detailTitle.set(null); this.showPayments.set(false); }
  openMonthlyPayments():void { this.detailGeneration++; this.detailTitle.set(null); this.showPayments.set(true); }
  readonly origin=signal<ExpenseOrigin|null>(null);
  originLabel(value:string|null):string {
    const labels:Record<string,string>={INTERNET:'Internet',ENERGIA:'Luz',AGUA:'Água',ESGOTO:'Esgoto',
      ALUGUEL:'Aluguel',PESSOAL:'Pessoal',ASSINATURA:'Assinaturas',OUTROS:'Outras despesas',
      BOLETO:'Boleto',NOTA_FISCAL:'Nota fiscal',OUTRO:'Outro documento'};
    return value ? labels[value] ?? value : 'Sem comprovante';
  }
  readonly detailTitle=signal<Title|null>(null);readonly position=signal<Position|null>(null);readonly movements=signal<Movement[]>([]);readonly movementCursor=signal<string|null>(null);readonly detailBusy=signal(false);
  readonly action=signal<Action|null>(null);readonly target=signal<Title|null>(null);readonly payment=signal<Movement|null>(null);readonly saving=signal(false);readonly dialogError=signal('');readonly pending=signal<Pending|null>(null);
  readonly money=money;readonly date=dateLabel;readonly today=today;
  readonly labels:Record<Action,string>={edit:'Editar título',cancel:'Cancelar título',pay:'Registrar baixa manual',reverse:'Estornar baixa'};
  readonly form=inject(FormBuilder).nonNullable.group({description:[''],amount:[''],issue_date:[''],due_date:[''],occurred_on:[''],reason:[''],financial_account_id:['']});
  history:(string|null)[]=[];private cursor:string|null=null;private status='';
  constructor(){const leave=()=>this.canLeave();this.workspaces.confirmChange=leave;const unload=(event:BeforeUnloadEvent)=>{if(this.saving() || this.pending()){event.preventDefault();event.returnValue='';}};window.addEventListener('beforeunload',unload);inject(DestroyRef).onDestroy(()=>{this.generation++;this.detailGeneration++;if(this.workspaces.confirmChange===leave)this.workspaces.confirmChange=null;window.removeEventListener('beforeunload',unload);});effect(()=>{this.workspaces.selected();const linkedTitle=this.routeParams()?.get('title');untracked(()=>{this.action.set(null);this.pending.set(null);this.detailTitle.set(null);this.position.set(null);this.movements.set([]);this.movementCursor.set(null);this.detailGeneration++;this.cursor=null;this.history=[];void this.refresh();if(linkedTitle)void this.openLinkedTitle(linkedTitle);});});}
  canLeave():boolean{if(!this.session.token())return true;if(this.saving())return false;if((this.pending()) && !window.confirm('Uma operação pode já ter sido registrada. Confira os títulos ou movimentos antes de iniciar outra tentativa. Deseja sair desta tela?'))return false;this.pending.set(null);return true;}
  trap(event:KeyboardEvent):void{if(event.key==='Escape'){event.preventDefault();this.close();return;}if(event.key!=='Tab')return;const targets=Array.from((event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled)')).filter(element=>!element.closest('fieldset:disabled'));const first=targets[0],last=targets[targets.length-1];if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}}
  async refresh():Promise<void>{const id=++this.generation,w=this.workspaces.selected();this.page.set(null);this.error.set('');this.busy.set(false);if(!w || !this.workspaces.can('payables.read'))return;this.busy.set(true);try{const result=await this.api.titles(w,this.cursor,this.status);if(id===this.generation && this.workspaces.selected()?.company_id===w.company_id)this.page.set(result);}catch(error){if(id===this.generation)this.error.set(errorMessage(error));}finally{if(id===this.generation)this.busy.set(false);}}
  filter(event:Event):void{this.status=(event.target as HTMLSelectElement).value;this.history=[];this.cursor=null;void this.refresh();}
  next():void{if(!this.page()?.next_cursor)return;this.history.push(this.cursor);this.cursor=this.page()!.next_cursor;void this.refresh();}
  previous():void{if(!this.history.length)return;this.cursor=this.history.pop()!;void this.refresh();}
  private async openLinkedTitle(titleId:string):Promise<void> {
    if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(titleId))return;
    const company=this.workspaces.selected(), generation=this.detailGeneration;
    if(!company || !this.workspaces.can('payables.read'))return;
    this.showPayments.set(false);
    try {
      const title=await this.api.title(company,titleId);
      if(generation===this.detailGeneration)await this.details(title);
    } catch(error) {
      if(generation===this.detailGeneration)this.error.set(errorMessage(error));
    }
  }
  async details(title:Title):Promise<void>{const w=this.workspaces.selected();if(!w)return;const id=++this.detailGeneration;this.origin.set(null);this.detailTitle.set(title);this.detailBusy.set(true);this.position.set(null);this.movements.set([]);this.movementCursor.set(null);this.error.set('');try{const [fresh,position,page,origin]=await Promise.all([this.api.title(w,title.id),this.api.position(w,title.id),this.api.movements(w,title.id),this.api.expenseOrigin(w,title.id)]);if(id!==this.detailGeneration || this.workspaces.selected()?.company_id!==w.company_id)return;if(fresh.revision!==position.revision)throw new Error();this.origin.set(origin);this.detailTitle.set(fresh);this.position.set(position);this.movements.set(page.items);this.movementCursor.set(page.next_cursor);}catch(error){if(id===this.detailGeneration){this.detailTitle.set(null);this.error.set(errorMessage(error));}}finally{if(id===this.detailGeneration)this.detailBusy.set(false);}}
  async moreMovements():Promise<void>{const w=this.workspaces.selected(),title=this.detailTitle(),cursor=this.movementCursor();if(!w || !title || !cursor)return;const id=this.detailGeneration;try{const page=await this.api.movements(w,title.id,cursor);if(id===this.detailGeneration && this.workspaces.selected()?.company_id===w.company_id){this.movements.update(rows=>[...rows,...page.items]);this.movementCursor.set(page.next_cursor);}}catch(error){if(id===this.detailGeneration)this.error.set(errorMessage(error));}}
  movementPath(title:string,movement:string){const company=this.workspaces.selected();return company?this.api.base(company)+'/'+title+'/payments/'+movement:'';}
  isReversed(id:string):boolean{return this.movements().some(row=>row.reverses_id===id);}
  open(action:Action,title:Title|null=null,payment:Movement|null=null):void{if(this.saving())return;this.action.set(action);this.target.set(title);this.payment.set(payment);this.dialogError.set('');this.pending.set(null);this.form.reset({description:title?.description || '',amount:action==='pay'?'':(title?.amount || '').replace('.',','),issue_date:title?.issue_date || today(),due_date:title?.due_date || today(),occurred_on:today(),reason:'',financial_account_id:''});
    for(const control of Object.values(this.form.controls)){control.clearValidators();control.updateValueAndValidity();}
    if(action==='edit'){this.form.controls.description.setValidators([Validators.required,Validators.maxLength(300)]);this.form.controls.issue_date.setValidators(Validators.required);this.form.controls.due_date.setValidators(Validators.required);}
    if(action==='edit' || action==='pay')this.form.controls.amount.setValidators([Validators.required,Validators.pattern(/^(?:0|[1-9]\d*)(?:[.,]\d{1,2})?$/)]);
    if(action==='pay' || action==='reverse')this.form.controls.occurred_on.setValidators(Validators.required);
    if(action==='reverse')this.form.controls.reason.setValidators([Validators.required,Validators.maxLength(300)]);
    for(const control of Object.values(this.form.controls))control.updateValueAndValidity();
    setTimeout(()=>document.querySelector<HTMLElement>('.dialog input, .dialog button')?.focus());
  }
  close():void{if(this.saving())return;if(this.pending() && !window.confirm('O resultado pode já ter sido registrado. Ao fechar, confira os movimentos antes de iniciar outra operação. Deseja fechar?'))return;this.action.set(null);this.pending.set(null);}
  async submit():Promise<void>{const w=this.workspaces.selected(),mode=this.action(),title=this.target();if(!w || !mode || this.form.invalid || this.saving())return;this.saving.set(true);this.dialogError.set('');const value=this.form.getRawValue();const company=w.company_id;
    let path=title?`/${encodeURIComponent(title.id)}`:'',method:'POST'|'PUT'='POST';let body:Record<string,unknown>={};
    if(mode==='edit'){body={description:value.description.trim(),amount:value.amount.replace(',','.'),issue_date:value.issue_date,due_date:value.due_date};body['expected_revision']=title!.revision;method='PUT';}
    if(mode==='cancel'){path+='/cancel';body={expected_revision:title!.revision};}
    if(mode==='pay'){path+='/payments';body={expected_revision:title!.revision,amount:value.amount.replace(',','.'),occurred_on:value.occurred_on,...(value.financial_account_id?{financial_account_id:value.financial_account_id}:{})};}
    if(mode==='reverse'){path+=`/payments/${encodeURIComponent(this.payment()!.id)}/reverse`;body={expected_revision:title!.revision,occurred_on:value.occurred_on,reason:value.reason.trim()};}
    if(mode==='pay' || mode==='reverse'){if(!this.pending())this.pending.set({key:crypto.randomUUID(),path,body});path=this.pending()!.path;body=this.pending()!.body;}
    try{await this.api.write(w,path,body,method,this.pending()?.key);if(this.workspaces.selected()?.company_id!==company)return;this.action.set(null);this.pending.set(null);this.success.set('Operação registrada com sucesso.');this.api.revision.update(n=>n+1);this.detailTitle.set(null);this.detailGeneration++;this.cursor=null;this.history=[];await this.refresh();}
    catch(error){if(this.workspaces.selected()?.company_id!==company)return;this.dialogError.set(errorMessage(error));}
    finally{this.saving.set(false);}
  }
}
