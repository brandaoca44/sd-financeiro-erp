import { HttpClient } from '@angular/common/http';
import { Component, computed, forwardRef, inject, signal } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

interface Bank {ispb: string; code: string | null; name: string; value: string}
interface BankCatalog {source: string; updated: string; banks: Bank[]}

@Component({
  selector: 'sdf-bank-selector',
  providers: [{provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => BankSelector), multi: true}],
  template: `
    <div class="bank-selector">
      <input type="search" aria-label="Buscar banco por nome ou código" placeholder="Buscar por nome ou código"
        [value]="query()" (input)="query.set($any($event.target).value)" [disabled]="disabled()" maxlength="100">
      <select aria-label="Selecionar banco" [value]="selection()" [disabled]="disabled()" (change)="selectBank($event)" (blur)="onTouched()">
        <option value="">Selecione o banco</option>
        @if (currentBank(); as bank) {
          <option [value]="bank.value">{{bank.value}}</option>
        }
        @for (bank of filtered(); track bank.ispb) {
          <option [value]="bank.value">{{bank.value}}</option>
        }
        <option value="__custom__">Banco internacional ou outro não listado</option>
      </select>
      @if (custom()) {
        <input type="text" aria-label="Nome do banco internacional ou não listado" placeholder="Nome do banco e país"
          [value]="value()" (input)="customName($event)" [disabled]="disabled()" maxlength="80" (blur)="onTouched()">
      }
      @if (failed()) {
        <small role="status">Catálogo indisponível. Use a opção de instituição não listada.</small>
      } @else if (catalog(); as data) {
        <small>Instituições do STR · Banco Central · Atualização {{data.updated}}</small>
      }
    </div>
  `,
  styles: `
    :host { display: block; width: 100%; min-width: 0; max-width: 100%; }
    .bank-selector { display: grid; grid-template-columns: minmax(0, 1fr); min-width: 0; gap: .4rem; }
    input, select { box-sizing: border-box; width: 100%; min-width: 0; max-width: 100%; min-height: 44px; font-size: .875rem; }
    small { color: #526680; font-weight: 400; line-height: 1.4; }
  `,
})
export class BankSelector implements ControlValueAccessor {
  readonly catalog = signal<BankCatalog | null>(null);
  readonly failed = signal(false);
  readonly value = signal('');
  readonly query = signal('');
  readonly disabled = signal(false);
  private readonly customSelected = signal(false);
  readonly currentBank = computed(() => this.catalog()?.banks.find(bank => bank.value === this.value()));
  readonly custom = computed(() => this.customSelected() || (!!this.value() && (this.failed() || (!!this.catalog() && !this.currentBank()))));
  readonly selection = computed(() => this.custom() ? '__custom__' : this.value());
  readonly filtered = computed(() => {
    const query = this.normalize(this.query());
    return (this.catalog()?.banks ?? []).filter(bank =>
      bank.value !== this.value() && this.normalize(bank.name + ' ' + bank.value).includes(query));
  });
  private onChange: (value: string) => void = () => {};
  onTouched: () => void = () => {};

  constructor() {
    inject(HttpClient).get<BankCatalog>('/catalog/banks.json').subscribe({
      next: catalog => this.catalog.set(catalog),
      error: () => this.failed.set(true),
    });
  }

  private normalize(value: string): string {
    return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  writeValue(value: string | null): void { this.value.set(value ?? ''); this.customSelected.set(false); }
  registerOnChange(callback: (value: string) => void): void { this.onChange = callback; }
  registerOnTouched(callback: () => void): void { this.onTouched = callback; }
  setDisabledState(disabled: boolean): void { this.disabled.set(disabled); }

  selectBank(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.customSelected.set(value === '__custom__');
    this.value.set(value === '__custom__' ? '' : value);
    this.onChange(this.value());
    this.onTouched();
  }

  customName(event: Event): void {
    this.value.set((event.target as HTMLInputElement).value);
    this.onChange(this.value());
  }
}
