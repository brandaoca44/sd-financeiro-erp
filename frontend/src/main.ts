import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { Component } from '@angular/core';
import { provideRouter, RouterOutlet, Routes } from '@angular/router';
import { authGuard, sessionInterceptor } from './app/core/session';

const routes: Routes = [
  {path: 'login', loadComponent: () => import('./app/features/auth/login').then(m => m.Login)},
  {path:'register',data:{mode:'register'},loadComponent:()=>import('./app/features/auth/account-pages').then(m=>m.AccountPage)},
  {path:'forgot-password',data:{mode:'forgot'},loadComponent:()=>import('./app/features/auth/account-pages').then(m=>m.AccountPage)},
  {path:'resend-confirmation',data:{mode:'resend'},loadComponent:()=>import('./app/features/auth/account-pages').then(m=>m.AccountPage)},
  {path:'confirm-email',data:{mode:'confirm'},loadComponent:()=>import('./app/features/auth/account-pages').then(m=>m.AccountPage)},
  {path:'reset-password',data:{mode:'reset'},loadComponent:()=>import('./app/features/auth/account-pages').then(m=>m.AccountPage)},
  {path:'mfa',loadComponent:()=>import('./app/features/auth/mfa-login').then(m=>m.MfaLogin)},
  {path:'plans',loadComponent:()=>import('./app/features/subscription/subscription').then(m=>m.SubscriptionPage)},
  {path: 'finance', canActivate: [authGuard], loadComponent: () => import('./app/features/finance/shell').then(m => m.FinanceShell), children: [
    {path: 'alerts', loadComponent: () => import('./app/features/finance/alerts').then(m => m.AlertsPage)},
    {path: 'financial-accounts', loadComponent: () => import('./app/features/finance/financial-accounts').then(m => m.FinancialAccountsPage)},
    {path: 'cashflow', loadComponent: () => import('./app/features/finance/cashflow').then(m => m.CashflowPage)},
    {path: 'overview', loadComponent: () => import('./app/features/finance/overview').then(m => m.Overview)},
    {path: 'audit', loadComponent: () => import('./app/features/finance/audit').then(m => m.AuditPage)},
    {path: 'access', loadComponent: () => import('./app/features/finance/company-access').then(m => m.CompanyAccess)},
    {path: 'collaborators', loadComponent: () => import('./app/features/finance/collaborators').then(m => m.Collaborators)},
    {path: 'billing', loadComponent: () => import('./app/features/finance/billing').then(m => m.Billing)},
    {path: 'expenses', loadComponent: () => import('./app/features/finance/expenses').then(m => m.Expenses)},
    {path: 'payables', canDeactivate:[(component:{canLeave:()=>boolean})=>component.canLeave()], loadComponent: () => import('./app/features/finance/payables').then(m => m.Payables)},
    {path:'subscription',data:{embedded:true},loadComponent:()=>import('./app/features/subscription/subscription').then(m=>m.SubscriptionPage)},
    {path:'help',loadComponent:()=>import('./app/core/context-help').then(m=>m.HelpSettings)},
    {path:'account',loadComponent:()=>import('./app/features/auth/my-account').then(m=>m.MyAccount)},
    {path:'security',loadComponent:()=>import('./app/features/auth/security').then(m=>m.AccountSecurityPage)},
    {path: '', redirectTo: 'overview', pathMatch: 'full'}
  ]},
  {path: '', redirectTo: 'finance', pathMatch: 'full'}, {path: '**', redirectTo: 'finance'}
];
@Component({selector:'sdf-root', imports:[RouterOutlet], template:'<router-outlet />'})
class App {}
bootstrapApplication(App, {providers:[provideRouter(routes), provideHttpClient(withInterceptors([sessionInterceptor]))]}).catch(() => {
  document.body.textContent = 'Não foi possível iniciar a interface. Recarregue a página.';
});
