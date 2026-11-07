import { Alerts } from '../../core/alerts';
import { ContextHelp, helpGuides } from '../../core/context-help';
import { Component, effect, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Session, errorMessage } from '../../core/session';
import { Workspaces } from '../../core/workspaces';

@Component({selector:'sdf-finance-shell',imports:[RouterLink,RouterLinkActive,RouterOutlet,ContextHelp],styles:`
  .alert-bell { position: relative; display: inline-flex; align-items: center; justify-content: center; min-width: 38px; min-height: 38px; border: 1px solid #dbe2ed; border-radius: .5rem; color: #294665; background: #fff; }
  .alert-bell svg { width: 19px; height: 19px; }
  .alert-count { position: absolute; right: -.3rem; top: -.35rem; min-width: 1.1rem; padding: .1rem .2rem; border-radius: 1rem; background: #a83140; color: #fff; font-size: .625rem; text-align: center; }
  .workspace-menu { margin-top: 1.75rem; overflow-y: auto; min-height: 0; }
  .menu-group + .menu-group { margin-top: .85rem; padding-top: .8rem; border-top: 1px solid #ffffff16; }
  .menu-label { display: block; padding: 0 .7rem .35rem; font-size: .6875rem; letter-spacing: .08em; color: #a5b8d5; font-weight: 650; }
  .workspace-menu a { display: flex; align-items: center; gap: .625rem; min-height: 2.5rem; padding: .5rem .625rem; border: 1px solid transparent; }
  .workspace-menu a > span { font-size: .8125rem; line-height: 1.25; width: auto; white-space: nowrap; }
  .workspace-menu a svg { width: 1.125rem; height: 1.125rem; flex: 0 0 auto; }
  .sidebar-bottom { padding-top: .75rem; border-top: 1px solid #ffffff20; }
  .sidebar-bottom .logout {
    display: inline-flex; align-items: center; justify-content: center; gap: .45rem;
    width: auto; min-height: 34px; padding: .35rem .65rem; border-radius: .5rem;
    border: 1px solid #8e5261; background: #ffffff08; color: #ffd5dc; font-size: .75rem; font-weight: 650;
  }
  .sidebar-bottom .logout:hover:not(:disabled) { background: #553247; border-color: #c67986; }
  @media (max-width: 760px) {
    .sidebar-bottom .logout { justify-content: center; min-width: 34px; padding-inline: .25rem; }
    .sidebar-bottom .logout-label { display: none; }
  }
  @media (max-width: 760px) {
    .workspace-menu a { justify-content: center; padding-inline: .25rem; }
    .workspace-menu a span, .menu-label { display: none; }
  }
`,template:`
<div class="app-layout"><aside class="sidebar"><a class="brand brand-light" routerLink="/finance"><img class="brand-mark" src="/brand/sdf-mark.svg" alt="SDF" width="44" height="44"><span>Sistema Digital Financeiro<small>Gestão empresarial</small></span></a>
<nav class="workspace-menu" aria-label="Menu principal">
  @for (group of visibleMenu(); track group.label) {
    <div class="menu-group" role="group" [attr.aria-label]="group.label">
      <span class="menu-label" aria-hidden="true">{{group.label}}</span>
      @for (item of group.items; track item.path) {
        <a [routerLink]="item.path" routerLinkActive="active" ariaCurrentWhenActive="page"
          [attr.aria-label]="item.label" [attr.title]="item.label">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"
            stroke-linejoin="round" aria-hidden="true"><path [attr.d]="item.icon" /></svg>
          <span>{{item.label}}</span>
        </a>
      }
    </div>
  }
</nav>
<div class="sidebar-bottom"><button class="logout" aria-label="Sair da conta" title="Sair da conta" (click)="logout()" [disabled]="leaving()"><span class="logout-label">{{leaving()?'Encerrando…':'Sair da conta'}}</span> <span aria-hidden="true">↗</span></button></div></aside>
<div class="main-layout"><header class="topbar"><div class="breadcrumb">Organização <span>/</span> <strong>Financeiro</strong></div><div class="topbar-actions"><label class="sr-only" for="workspace">Empresa</label><select id="workspace" [value]="workspaces.selected()?.company_id || ''" (change)="choose($event)" [disabled]="workspaces.loading()"><option value="" disabled>Selecione uma empresa</option>@for(workspace of workspaces.items();track workspace.company_id){<option [value]="workspace.company_id">{{workspaces.label(workspace)}}</option>}</select><button class="icon-button" (click)="workspaces.load()" title="Atualizar empresas" aria-label="Atualizar empresas">↻</button>@if (workspaces.can('payables.read')) {
  <a class="alert-bell" routerLink="/finance/alerts" [attr.aria-label]="alerts.failed() ? 'Central de alertas. Consulta indisponível.' : 'Central de alertas. ' + (alerts.report()?.total ?? 0) + ' pendências.'">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>
    @if (alerts.report()?.total; as count) { <span class="alert-count" aria-hidden="true">{{count > 99 ? '99+' : count}}</span> }
  </a>
}@if (helpText; as text) {<sdf-help [text]="text" />}<span class="avatar" aria-label="Conta autenticada">SDF</span></div></header>
<main class="page-content" id="main-content">@if(error()){<div class="alert" role="alert">{{error()}}</div>}@if(workspaces.error()){<div class="alert" role="alert">{{workspaces.error()}} <button class="text-button" (click)="workspaces.load()">Tentar novamente</button></div>}
@if(isAccountSettings){<router-outlet />}@else if(workspaces.loading() && !workspaces.selected()){<div class="empty-state" role="status">Carregando suas empresas…</div>}@else if(!workspaces.selected()){<div class="empty-state"><span class="empty-icon">◇</span><h1>Nenhuma empresa disponível</h1><p>Nenhuma empresa com acesso financeiro está disponível para sua conta.<br>Peça ao Master da organização para revisar seu vínculo e suas permissões.</p><button class="secondary" (click)="workspaces.load()">Atualizar acessos</button></div>}@else{<router-outlet />}
@if(workspaces.cursor()){<button class="text-button" (click)="workspaces.load(true)" [disabled]="workspaces.loading()">Carregar mais empresas</button>}
</main><footer class="app-footer">Sistema Digital Financeiro <span>Sistema de gestão empresarial</span></footer></div></div>`})
export class FinanceShell {
  readonly alerts=inject(Alerts);
  readonly workspaces=inject(Workspaces);private session=inject(Session);private router=inject(Router);
  readonly error=signal('');readonly leaving=signal(false);
  constructor(){effect(()=>{if(!this.session.token())void this.router.navigateByUrl('/login');});void this.workspaces.load();}
  get isAccountSettings():boolean{return ['/finance/account','/finance/security','/finance/subscription','/finance/help','/finance/access','/finance/audit'].includes(this.router.url.split('?')[0].split('#')[0]);}
  readonly menu = [
    {label: 'Financeiro', items: [
      {path: 'alerts', label: 'Central de alertas', icon: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4'},
      {path: 'financial-accounts', label: 'Contas financeiras', icon: 'M3 7l9-4 9 4M5 10v8m7-8v8m7-8v8M3 21h18M3 7h18'},
      {path: 'cashflow', label: 'Fluxo de caixa', icon: 'M3 17l6-6 4 4 8-10m-5 0h5v5'},
      {path: 'overview', label: 'Visão financeira', icon: 'M4 19V5m0 14h16M8 15v-3m4 3V8m4 7v-5m4 5V6'},
      {path: 'expenses', label: 'Despesas', icon: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3Zm3 5h6m-6 4h6'},
      {path: 'payables', label: 'Contas a pagar', icon: 'M4 7h16v12H4zM4 11h16m-5 4h2'},
      {path: 'billing', label: 'Faturamento', icon: 'M5 19h14M7 15l5-5 3 3 5-6m-4 0h4v4'},
    ]},
    {label: 'Pessoas', items: [
      {path: 'collaborators', label: 'Colaboradores', icon: 'M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2m10-13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Zm6 13v-2a4 4 0 0 0-3-4'},
    ]},
    {label: 'Configurações', items: [
      {path: 'audit', label: 'Histórico de operações', icon: 'M9 3h6v4H9zM7 5H5v16h14V5h-2M8 11h8m-8 4h8'},
      {path: 'access', label: 'Permissões da empresa', icon: 'M12 22s7-3 7-10V5l-7-3-7 3v7c0 7 7 10 7 10Zm-3-10 2 2 4-4'},
      {path: 'account', label: 'Minha conta', icon: 'M20 21v-2a6 6 0 0 0-12 0v2m10-13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'},
      {path: 'security', label: 'Segurança da conta', icon: 'M12 22s7-3 7-10V5l-7-3-7 3v7c0 7 7 10 7 10Zm-3-10 2 2 4-4'},
      {path: 'subscription', label: 'Assinatura e planos', icon: 'M5 4h14v16H5zM8 9h8m-8 4h8m-8 4h4'},
      {path: 'help', label: 'Tutoriais e ajuda', icon: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0ZM9 9a3 3 0 1 1 4 2.8c-.7.3-1 1-1 2.2m0 3h.01'},
    ]},
  ];

  visibleMenu() {
    return this.menu.map(group => ({...group, items: group.items.filter(item => {
      const permissions = this.workspaces.selected()?.permissions ?? [];
      if (item.path === 'access' || item.path === 'audit') return !!this.workspaces.selected()?.can_manage_access;
      if (item.path === 'billing') return permissions.some(key => key.startsWith('billing.'));
      if (item.path === 'collaborators') return permissions.some(key => ['people.read', 'people.create'].includes(key));
      if (item.path === 'financial-accounts') return this.workspaces.can('accounts.read') || this.workspaces.can('accounts.manage');
      if (item.path === 'cashflow') return this.workspaces.can('payables.read') && this.workspaces.can('billing.read');
      if (item.path === 'overview') return this.workspaces.can('payables.read') || this.workspaces.can('billing.read');
      if (['alerts', 'payables', 'expenses'].includes(item.path)) return permissions.some(key => key.startsWith('payables.'));
      return true;
    })})).filter(group => group.items.length);
  }

  get helpText(): string | undefined {
    const path = this.router.url.split(/[?#]/)[0].split('/').at(-1);
    return helpGuides.find(guide => guide.path === path)?.text;
  }
  choose(event:Event):void{const select=event.target as HTMLSelectElement;if(!this.workspaces.choose(select.value))select.value=this.workspaces.selected()?.company_id || '';}
  async logout():Promise<void>{if(this.leaving() || (this.workspaces.confirmChange && !this.workspaces.confirmChange()))return;this.leaving.set(true);this.error.set('');try{await this.session.logout();await this.router.navigateByUrl('/login');}catch(error){this.error.set('Não foi possível confirmar o encerramento da sessão. Tente novamente. '+errorMessage(error));}finally{this.leaving.set(false);}}
}
