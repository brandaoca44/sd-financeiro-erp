import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { describe, expect, it, vi } from 'vitest';
import { BankSelector } from './bank-selector';

describe('Seletor de banco', () => {
  it('preserva banco anterior, permite buscar e trocar para banco internacional', () => {
    TestBed.configureTestingModule({providers: [provideHttpClient(), provideHttpClientTesting()]});
    const fixture = TestBed.createComponent(BankSelector);
    const component = fixture.componentInstance;
    const change = vi.fn();
    component.registerOnChange(change);
    component.writeValue('Banco estrangeiro anterior');
    TestBed.inject(HttpTestingController).expectOne('/catalog/banks.json').flush({
      source: 'BCB', updated: '2026-11-04',
      banks: [{ispb: '00000000', code: '001', name: 'Banco do Brasil', value: '001 - BCO DO BRASIL S.A.'}],
    });
    fixture.detectChanges();
    expect(component.custom()).toBe(true);
    expect(component.value()).toBe('Banco estrangeiro anterior');
    expect(change).not.toHaveBeenCalled();
    component.query.set('brasil');
    expect(component.filtered()).toHaveLength(1);
    const select = fixture.nativeElement.querySelector('select') as HTMLSelectElement;
    select.value = '001 - BCO DO BRASIL S.A.';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(change).toHaveBeenLastCalledWith('001 - BCO DO BRASIL S.A.');
    select.value = '__custom__';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(component.custom()).toBe(true);
    expect(change).toHaveBeenLastCalledWith('');
    component.setDisabledState(true);
    fixture.detectChanges();
    expect(select.disabled).toBe(true);
    TestBed.inject(HttpTestingController).verify();
  });
});
