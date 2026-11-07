import { Component,inject,input,output,signal } from '@angular/core';
import { FormBuilder,ReactiveFormsModule,Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom,timeout } from 'rxjs';
import { AccountPicker } from './account-picker';
import { Workspaces } from './workspaces';
import { FinanceApi,today } from './finance';
@Component({selector:'sdf-legacy-account-link',imports:[ReactiveFormsModule,AccountPicker],styles:`:host{display:block}.link-form{display:grid;gap:.6rem;padding:.75rem;border:1px solid #dce5f0;border-radius:.5rem;min-width:16rem;margin-top:.4rem}.link-actions{display:flex;gap:.5rem}`,template:`
  @if(allowed()){
    @if(!open()){<button class="secondary small" type="button" (click)="open.set(true)">Vincular conta</button>}
    @else{<form class="link-form" [formGroup]="form" (ngSubmit)="save()"><sdf-account-picker formControlName="account" />
      @if(kind()==='receipt' && reversed() && !reversalDate()){<label>Data efetiva do estorno antigo<input type="date" formControlName="reversed_on" [max]="today"></label>}
      @if(error()){<p class="field-help" role="alert">{{error()}}</p>}
      <div class="link-actions"><button class="secondary small" type="button" (click)="open.set(false)" [disabled]="busy()">Voltar</button><button class="primary small" type="submit" [disabled]="busy() || form.invalid">Vincular</button></div>
    </form>}
  }
`})
export class LegacyAccountLink {
  readonly path=input.required<string>();readonly kind=input.required<'payment'|'receipt'>();readonly revision=input(1);readonly reversed=input(false);readonly reversalDate=input<string|null>(null);readonly saved=output<void>();
  private workspaces=inject(Workspaces);private http=inject(HttpClient);private api=inject(FinanceApi);readonly today=today();readonly open=signal(false);readonly busy=signal(false);readonly error=signal('');
  readonly form=inject(FormBuilder).nonNullable.group({account:['',Validators.required],reversed_on:['']});
  allowed(){return this.workspaces.can('accounts.read')&&this.workspaces.can('accounts.manage')&&this.workspaces.can(this.kind()==='payment'?'payables.settle':'billing.receive')&&(!(this.kind()==='receipt'&&this.reversed()&&!this.reversalDate())||this.workspaces.can('billing.reverse'));}
  async save(){if(!this.allowed()||this.form.invalid||this.busy())return;const value=this.form.getRawValue(),company=this.workspaces.selected();
    if(this.kind()==='receipt'&&this.reversed()&&!this.reversalDate()&&!value.reversed_on){this.error.set('Informe a data efetiva do estorno.');return;}
    const body=this.kind()==='payment'?{financial_account_id:value.account,expected_revision:this.revision()}:{financial_account_id:value.account,expected_reversed:this.reversed(),...(value.reversed_on?{reversed_on:value.reversed_on}:{})};
    this.busy.set(true);this.error.set('');try{await firstValueFrom(this.http.post(this.path()+'/account',body).pipe(timeout(15000)));
      if(this.workspaces.selected()?.company_id===company?.company_id){this.open.set(false);this.api.revision.update(value=>value+1);this.saved.emit();}}
    catch{this.error.set('Não foi possível vincular. Confira a data inicial, a situação da conta e atualize a operação.');}finally{this.busy.set(false);}}
}
