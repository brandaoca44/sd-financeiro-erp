import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';
import { ContextHelp, HelpPreferences } from './context-help';

describe('Ajuda contextual', () => {
  afterEach(() => localStorage.removeItem('sdf.contextual-help'));

  it('oculta os balões ao desativar e restaura a preferência após recarregar', () => {
    localStorage.removeItem('sdf.contextual-help');
    const fixture = TestBed.createComponent(ContextHelp);
    fixture.componentRef.setInput('text', 'Guia de teste');
    fixture.detectChanges();

    const button = () => fixture.nativeElement.querySelector('button');
    button().click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Guia de teste');

    document.body.click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Guia de teste');

    const preferences = TestBed.inject(HelpPreferences);
    preferences.setEnabled(false);
    fixture.detectChanges();
    expect(button()).toBeNull();
    expect(new HelpPreferences().enabled()).toBe(false);

    preferences.setEnabled(true);
    fixture.detectChanges();
    expect(button()).not.toBeNull();
  });
});
