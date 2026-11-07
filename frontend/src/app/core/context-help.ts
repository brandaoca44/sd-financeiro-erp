import { Component, Injectable, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

export const helpGuides = [
  {path: 'financial-accounts', title: 'Contas financeiras', text: 'Cadastre caixas e contas da empresa com saldo e data de referência. O saldo inicial fica preservado. A inativação mantém o histórico. Os dados bancários exigem acesso próprio. Use Vincular conta nos históricos antigos e consulte o saldo e o extrato nos detalhes da conta.'},
  {path: 'cashflow', title: 'Fluxo de caixa', text: 'Consulte entradas e saídas registradas, pendências por vencimento e variações acumuladas do período. A consulta exige acesso às duas áreas. As projeções partem dos títulos cadastrados e não incluem um saldo bancário inicial.'},
  {path: 'audit', title: 'Histórico de operações', text: 'O Master consulta operações da empresa por período, área e ação. O histórico identifica responsável, horário e registro, sem revelar valores pessoais ou dados bancários. Carregue mais para continuar a consulta.'},
  {path: 'access', title: 'Permissões da empresa', text: 'O Master escolhe o usuário e concede ou revoga cada ação, confirmando sua senha. Documentos, remuneração e dados bancários têm acessos separados. Para cadastrar colaboradores, também são necessários os acessos aos dados pessoais e bancários obrigatórios.'},
  {path: 'alerts', title: 'Central de alertas', text: 'Consulte contas vencidas, vencimentos de hoje e dos próximos sete dias. Cobranças variáveis aguardando revisão também aparecem aqui. Abra o alerta para acessar a cobrança.'},
  {path: 'account', title: 'Minha conta', text: 'Confira seus dados pessoais e bancários. Para salvar alterações, confirme sua senha atual. O CPF registrado identifica o titular e fica protegido contra alteração nesta tela.'},
  {path: 'overview', title: 'Visão financeira', text: 'Contas a receber mostra recebimentos do mês e saldos atuais das cobranças, conforme seu acesso. Em Contas a pagar, use as datas para consultar baixas e estornos do período.'},
  {path: 'expenses', title: 'Despesas', text: 'Cadastre a cobrança com categoria e fornecedor. Informe o vencimento para gerar o título. Consulte os lançamentos e as recorrências nas abas da tela.'},
  {path: 'payables', title: 'Contas a pagar', text: 'Abra os detalhes para consultar o saldo, registrar uma baixa ou verificar a origem. Use Pagamentos do mês para consultar baixas e estornos.'},
  {path: 'billing', title: 'Faturamento', text: 'Registre o serviço e sua competência. Com vencimento, a cobrança aparece em Contas a receber, onde você pode registrar o recebimento.'},
  {path: 'collaborators', title: 'Colaboradores', text: 'Cadastre ou edite colaboradores da empresa selecionada. Consulte os vínculos encerrados na aba Desligados.'},
  {path: 'security', title: 'Segurança da conta', text: 'Revise as opções de segurança e autenticação da sua conta.'},
  {path: 'subscription', title: 'Assinatura e planos', text: 'Compare os planos e abra os detalhes para consultar os recursos de cada opção.'},
] as const;

@Injectable({providedIn: 'root'})
export class HelpPreferences {
  private readonly key = 'sdf.contextual-help';
  readonly enabled = signal(localStorage.getItem(this.key) !== 'off');

  setEnabled(enabled: boolean): void {
    localStorage.setItem(this.key, enabled ? 'on' : 'off');
    this.enabled.set(enabled);
  }
}

@Component({
  selector: 'sdf-help',
  host: {
    '(document:click)': 'open.set(false)',
    '(document:keydown.escape)': 'open.set(false)',
  },
  template: `
    @if (preferences.enabled() && text()) {
      <button type="button" [attr.aria-label]="label()" [attr.aria-expanded]="open()"
        (click)="toggle($event)">?</button>
      @if (open()) { <span class="help-panel" role="status" (click)="$event.stopPropagation()">{{text()}}</span> }
    }
  `,
  styles: `
    :host { display: inline-block; position: relative; }
    button { border-radius: 50%; min-width: 1.5rem; min-height: 1.5rem; color: #294665; background: #edf3fa; }
    .help-panel { position: absolute; z-index: 10; inset-block-start: calc(100% + .4rem); inset-inline-end: 0;
      width: min(15rem, 65vw); padding: .75rem; border: 1px solid #d6e0ed; border-radius: .5rem;
      background: white; color: #294665; box-shadow: 0 6px 20px #17376222; font-size: .8125rem; }
  `,
})
export class ContextHelp {
  readonly preferences = inject(HelpPreferences);
  readonly label = input('Ajuda desta tela');
  readonly text = input.required<string>();
  readonly open = signal(false);

  toggle(event: MouseEvent): void {
    const wasOpen = this.open();
    document.dispatchEvent(new Event('click'));
    event.stopPropagation();
    this.open.set(!wasOpen);
  }
}

@Component({
  selector: 'sdf-help-settings',
  imports: [RouterLink],
  template: `
    <section class="panel detail-panel">
      <h1>Tutoriais e ajuda</h1>
      <p class="muted">Os balões abrem pelo botão ? e fecham ao clicar fora ou pressionar Esc. A preferência vale neste navegador.</p>
      <label class="help-toggle"><input type="checkbox" [checked]="preferences.enabled()"
        (change)="preferences.setEnabled($any($event.target).checked)"> Exibir ajuda contextual</label>
      <p role="status">{{preferences.enabled() ? 'Balões ativados' : 'Balões desativados'}}</p>
    </section>
    <section class="panel detail-panel help-guides">
      <h2>Guias rápidos</h2>
      <p class="muted">Os guias ficam disponíveis aqui mesmo quando os balões estão desativados.</p>
      @for (guide of guides; track guide.path) {
        <details>
          <summary>{{guide.title}}</summary>
          <p>{{guide.text}}</p>
          <a class="secondary small" [routerLink]="['/finance', guide.path]">Abrir {{guide.title}}</a>
        </details>
      }
    </section>
  `,
  styles: `
    .help-toggle { display: flex; align-items: center; gap: .5rem; }
    .help-toggle input { appearance: auto; width: 1rem; height: 1rem; min-height: 0; accent-color: #27548d; }
    .help-guides { margin-top: 1rem; }
    details { border-top: 1px solid #dbe5f0; padding: .8rem 0; }
    summary { cursor: pointer; font-weight: 650; color: #173762; }
    details p { margin: .6rem 0; }
  `,
})
export class HelpSettings {
  readonly guides = helpGuides;
  readonly preferences = inject(HelpPreferences);
}
