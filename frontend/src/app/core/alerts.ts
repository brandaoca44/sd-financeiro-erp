import { HttpClient } from '@angular/common/http';
import { DestroyRef, Injectable, effect, inject, signal } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timeout } from 'rxjs';
import { FinanceApi } from './finance';
import { Session } from './session';
import { Workspaces } from './workspaces';

export type AlertKind = 'OVERDUE' | 'TODAY' | 'UPCOMING' | 'REVIEW';
export interface FinancialAlert {id: string; kind: AlertKind; description: string; due_date: string; amount: string | null}
export interface FinancialAlerts {as_of: string; total: number; overdue: number; today: number; upcoming: number; review: number; items: FinancialAlert[]}

@Injectable({providedIn: 'root'})
export class Alerts {
  private readonly http = inject(HttpClient);
  private readonly workspaces = inject(Workspaces);
  private readonly session = inject(Session);
  private readonly api = inject(FinanceApi);
  private readonly version = signal(0);
  readonly report = signal<FinancialAlerts | null>(null);
  readonly loading = signal(false);
  readonly failed = signal(false);

  constructor() {
    const destroy = inject(DestroyRef);
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') this.refresh();
    }, 60000);
    destroy.onDestroy(() => clearInterval(timer));
    inject(Router).events.pipe(takeUntilDestroyed()).subscribe(event => {
      if (event instanceof NavigationEnd) this.refresh();
    });
    effect(onCleanup => {
      const company = this.workspaces.selected(), token = this.session.token();
      this.version();
      this.api.revision();
      this.report.set(null);
      this.failed.set(false);
      this.loading.set(false);
      if (!company || !token || !this.workspaces.can('payables.read')) return;
      this.loading.set(true);
      const url = this.api.base(company).replace(/payables$/, 'alerts');
      const subscription = this.http.get<FinancialAlerts>(url).pipe(timeout(15000)).subscribe({
        next: report => { this.report.set(report); this.loading.set(false); },
        error: () => { this.failed.set(true); this.loading.set(false); },
      });
      onCleanup(() => subscription.unsubscribe());
    });
  }

  refresh(): void { this.version.update(value => value + 1); }
}
