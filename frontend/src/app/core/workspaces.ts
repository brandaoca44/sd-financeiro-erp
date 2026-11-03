import { Injectable, effect, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom, timeout } from 'rxjs';
import { Session, errorMessage } from './session';

export type Permission='payables.read'|'payables.manage'|'payables.settle'|'payables.reverse';
export interface Workspace {organization_id:string; company_id:string; company_name:string|null; permissions:Permission[]}
@Injectable({providedIn:'root'})
export class Workspaces {
  confirmChange:(()=>boolean)|null=null;
  private http=inject(HttpClient); private session=inject(Session); private generation=0;
  readonly items=signal<Workspace[]>([]); readonly selected=signal<Workspace|null>(null);
  readonly loading=signal(false); readonly error=signal(''); readonly cursor=signal<string|null>(null);
  constructor(){effect(() => {if(!this.session.token()){this.generation++;this.items.set([]);this.selected.set(null);this.error.set('');this.cursor.set(null);this.loading.set(false);}});}
  can(permission:Permission):boolean {return this.selected()?.permissions.includes(permission) ?? false;}
  label(workspace:Workspace):string {const name=workspace.company_name;if(!name)return `Empresa autorizada · ${workspace.company_id.slice(-8)}`;return this.items().filter(item=>item.company_name===name).length>1?`${name} · ${workspace.company_id.slice(-8)}`:name;}
  choose(id:string):boolean {if(this.confirmChange && !this.confirmChange())return false;this.selected.set(this.items().find(w => w.company_id===id) || null);return true;}
  async load(more=false):Promise<void> {
    if(!more && this.confirmChange && !this.confirmChange())return;
    const request=++this.generation;
    if(!more){this.items.set([]);this.selected.set(null);this.cursor.set(null);}
    this.error.set('');this.loading.set(true);
    try {
      const params:Record<string,string>={limit:'100'}; if(more && this.cursor())params['cursor']=this.cursor()!;
      const page=await firstValueFrom(this.http.get<{items:Workspace[];next_cursor:string|null}>('/api/v1/auth/workspaces',{params}).pipe(timeout(15000)));
      if(request!==this.generation || !this.session.token())return;
      this.items.update(old => more ? [...old,...page.items] : page.items); this.cursor.set(page.next_cursor);
      if(!this.selected())this.selected.set(this.items()[0] || null);
    }catch(error){if(request===this.generation)this.error.set(errorMessage(error));}
    finally{if(request===this.generation)this.loading.set(false);}
  }
}
