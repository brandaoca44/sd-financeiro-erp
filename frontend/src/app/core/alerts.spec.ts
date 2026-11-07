import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { Alerts } from './alerts';
import { FinanceApi } from './finance';
import { Session } from './session';
import { Workspaces } from './workspaces';

describe('Alertas por empresa', () => {
  it('cancela a consulta anterior e limpa os dados ao trocar empresa ou perder permissão', () => {
    const selected = signal({company_id: 'a', organization_id: 'org', permissions: ['payables.read']});
    const token = signal<string | null>('token');
    TestBed.configureTestingModule({providers: [
      provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
      {provide: Session, useValue: {token}},
      {provide: Workspaces, useValue: {selected, can: (key: string) => selected().permissions.includes(key)}},
      {provide: FinanceApi, useValue: {revision: signal(0), base: (company: {company_id: string}) => '/api/' + company.company_id + '/payables'}},
    ]});
    const alerts = TestBed.inject(Alerts), control = TestBed.inject(HttpTestingController);
    TestBed.tick();
    const first = control.expectOne('/api/a/alerts');
    selected.set({...selected(), company_id: 'b'});
    TestBed.tick();
    expect(first.cancelled).toBe(true);
    expect(alerts.report()).toBeNull();
    control.expectOne('/api/b/alerts').flush({
      as_of: '2026-11-06', total: 0, overdue: 0, today: 0, upcoming: 0, review: 0, items: [],
    });
    expect(alerts.report()?.total).toBe(0);
    selected.set({...selected(), permissions: []});
    TestBed.tick();
    expect(alerts.report()).toBeNull();
    control.expectNone('/api/b/alerts');
    control.verify();
    TestBed.resetTestingModule();
  });
});
