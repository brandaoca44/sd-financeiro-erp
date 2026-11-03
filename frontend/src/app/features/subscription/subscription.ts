import { Component, ElementRef, ViewChild, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom, timeout } from 'rxjs';
import { Session } from '../../core/session';

export interface CatalogPlan {key:string;companies_limit:number|null;users_limit:number|null;features:string[]}
export interface ProductCatalog {version:string;segment:string;published:boolean;checkout_available:boolean;plans:CatalogPlan[];available_features:string[]}
const presentation:Record<string,{name:string;label:string;description:string;features:string[]}>={
  ESSENTIAL:{name:'Essential',label:'OPERAÇÃO FINANCEIRA',description:'Controles essenciais para organizar a rotina de uma empresa.',features:['Financeiro do dia a dia','Cadastros e despesas organizados','Boletos e alertas de vencimento']},
  PROFESSIONAL:{name:'Professional',label:'GESTÃO E ANÁLISE',description:'Visão consolidada e processos para equipes com uma operação mais ampla.',features:['Tudo do Essential','Gestão de múltiplas empresas','Aprovações, recorrências e análises']},
  ENTERPRISE:{name:'Enterprise',label:'GOVERNANÇA E INTEGRAÇÃO',description:'Estrutura configurada para operações com necessidades específicas de controle.',features:['Tudo do Professional','Governança e integrações contratadas','Implantação e migração assistidas']},
};
const comparisonRows=[
  {key:'business.payables',name:'Contas a pagar, baixas e estornos',group:'Financeiro'},
  {key:'business.payables.summary',name:'Posição a pagar e indicadores básicos',group:'Financeiro'},
  {key:'business.receivables',name:'Contas a receber',group:'Financeiro'},
  {key:'business.expenses',name:'Aluguel, água, luz, internet e demais despesas',group:'Financeiro'},
  {key:'business.boletos',name:'Cadastro de boletos vinculados a títulos',group:'Financeiro'},
  {key:'business.cashflow',name:'Fluxo de caixa',group:'Financeiro'},
  {key:'business.due_alerts',name:'Alertas internos de vencimento',group:'Financeiro'},
  {key:'business.parties',name:'Clientes e fornecedores',group:'Cadastros'},
  {key:'business.services',name:'Catálogo de serviços',group:'Cadastros'},
  {key:'business.products',name:'Catálogo básico de produtos',group:'Cadastros'},
  {key:'business.staff_costs',name:'Funcionários e custos informados de pessoal',group:'Pessoas'},
  {key:'business.documents',name:'Organização de notas de entrada e saída',group:'Fiscal'},
  {key:'business.tax.basic',name:'Enquadramento e acompanhamento de obrigações',group:'Fiscal'},
  {key:'business.tax.review',name:'Conferências e indícios de inconsistências fiscais',group:'Fiscal'},
  {key:'business.import.standard',name:'Importação por modelos padronizados',group:'Implantação'},
  {key:'business.import.mapping',name:'Mapeamentos de importação reutilizáveis',group:'Implantação'},
  {key:'business.contracts',name:'Contratos e recorrências de serviços',group:'Gestão'},
  {key:'business.expenses.allocation',name:'Rateios e comparação de despesas',group:'Gestão'},
  {key:'business.consolidation',name:'Consolidação de empresas autorizadas',group:'Gestão'},
  {key:'business.results.basic',name:'Faturamento e resultado gerencial básico',group:'Gestão'},
  {key:'business.staff_analysis',name:'Análises de custos de pessoal',group:'Pessoas'},
  {key:'business.tax.governance',name:'Governança fiscal ampliada',group:'Fiscal'},
  {key:'business.planning',name:'Orçamento e projeções',group:'Gestão'},
  {key:'business.opportunities',name:'Análise de desperdícios e oportunidades',group:'Gestão'},
  {key:'business.approvals',name:'Fluxos configuráveis de aprovação',group:'Governança'},
  {key:'business.governance',name:'Políticas ampliadas de segregação de funções',group:'Governança'},
  {key:'business.integrations',name:'Integrações contratadas',group:'Integrações'},
  {key:'assistance.product',name:'Tutorial e assistência sobre o produto',group:'Assistência'},
  {key:'assistance.company',name:'IA com consultas a dados autorizados',group:'Assistência'},
  {key:'assistance.private_knowledge',name:'Fontes corporativas privadas',group:'Assistência'},
  {key:'interface.languages',name:'Português e inglês',group:'Interface'},
];

@Component({selector:'sdf-subscription',imports:[RouterLink],styleUrl:'./subscription.css',template:`
<div class="plans-page" [class.embedded]="embedded">
@if(!embedded){<header class="plans-nav"><a class="plans-brand" routerLink="/login"><img src="/brand/sdf-mark.svg" alt="SDF" width="42" height="42"><span>Sistema Digital Financeiro<small>Gestão empresarial</small></span></a><a class="plans-return" [routerLink]="session.token()?'/finance':'/login'">{{session.token()?'Voltar ao financeiro':'Acessar o sistema'}} <span aria-hidden="true">↗</span></a></header>}
<section class="plans-hero"><div class="hero-inner"><span class="hero-label">EMPRESARIAL · SERVIÇOS</span><h1>{{embedded?'Assinatura e planos':'Planos para a sua operação'}}</h1><p>Compare os recursos de gestão financeira, análise e governança do Sistema Digital Financeiro.</p><div class="hero-meta"><span><i aria-hidden="true"></i> Segmento Empresarial</span><span>Essential · Professional · Enterprise</span></div></div></section>
<main class="plans-content" [attr.aria-busy]="loading()">
<div class="catalog-notice"><span class="notice-symbol" aria-hidden="true">i</span><div><strong>Contratação em preparação</strong><p>Consulte o escopo dos planos. Valores e contratação ainda não estão disponíveis.</p></div></div>
@if(error()){<div class="catalog-error" role="alert"><p>{{error()}}</p><button type="button" (click)="load()">Tentar novamente</button></div>}
@if(loading()){<div class="plans-loading" role="status">Carregando a comparação dos planos…</div>}
@if(catalog();as data){
<section class="plan-grid" aria-label="Planos Empresarial">
@for(plan of data.plans;track plan.key){
<article class="plan-card" [class.professional]="plan.key==='PROFESSIONAL'" [class.selected]="selected()===plan.key">
<div class="plan-card-heading"><span class="plan-label">{{info(plan.key).label}}</span><span class="plan-number" aria-hidden="true">{{plan.key==='ESSENTIAL'?'01':plan.key==='PROFESSIONAL'?'02':'03'}}</span></div>
<h2>{{info(plan.key).name}}</h2><p class="plan-description">{{info(plan.key).description}}</p>

<div class="plan-limits"><span>Empresas <strong>{{plan.companies_limit===null?'Sob contrato':plan.companies_limit}}</strong></span><span>Usuários <strong>{{plan.users_limit===null?'Sob contrato':plan.users_limit}}</strong></span></div>
<ul>@for(item of info(plan.key).features;track item){<li><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m4 10 4 4 8-8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg><span>{{item}}</span></li>}</ul>
<button class="compare-button" type="button" aria-haspopup="dialog" [attr.aria-label]="'Ver detalhes de '+info(plan.key).name" (click)="viewPlan(plan.key)">Ver detalhes <span aria-hidden="true">→</span></button>
</article>}
</section>
<section class="security-baseline"><div class="security-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Z"/><path d="m8 12 3 3 5-6"/></svg></div><div><h2>Segurança em todos os planos</h2><p>Isolamento entre empresas, permissões por operação e proteção de dados fazem parte da base do sistema. O plano contratado não substitui as permissões do usuário.</p></div><span class="segment-note">Outros segmentos exigem contratação própria.</span></section>
<details class="comparison-panel"><summary class="comparison-heading"><div><h2>Comparar todos os planos</h2><p>Confira o escopo e a disponibilidade lado a lado.</p></div><span class="comparison-chevron" aria-hidden="true">+</span></summary>
<div class="comparison-scroll"><table><caption class="sr-only">Comparação de recursos e disponibilidade por plano Empresarial</caption><thead><tr><th scope="col">Recurso</th><th scope="col">Disponibilidade</th>@for(plan of data.plans;track plan.key){<th scope="col" >{{info(plan.key).name}}</th>}</tr></thead><tbody>@for(row of rows;track row.key){<tr><th scope="row"><small>{{row.group}}</small>{{row.name}}</th><td><span class="availability" [class.ready]="data.available_features.includes(row.key)">{{data.available_features.includes(row.key)?'Implementado':'Planejado'}}</span></td>@for(plan of data.plans;track plan.key){<td ><span [class.included]="plan.features.includes(row.key)">{{plan.features.includes(row.key)?'Incluído':'—'}}</span></td>}</tr>}</tbody></table></div>
</details>
<dialog class="plan-detail" #planDetail aria-labelledby="plan-detail-title" (close)="selected.set('')">
<div class="detail-heading"><div><span class="section-label">EMPRESARIAL · SERVIÇOS</span><h2 id="plan-detail-title">{{info(selected()).name}}</h2></div><button type="button" class="detail-close" autofocus (click)="planDetail.close()" aria-label="Fechar detalhes">×</button></div>
@if(selectedPlan();as plan){
<p class="detail-intro">{{info(plan.key).description}}</p><p class="detail-limits"><strong>Empresas:</strong> {{plan.companies_limit ?? 'Sob contrato'}} <strong>Usuários:</strong> {{plan.users_limit ?? 'Sob contrato'}}</p>
<p class="detail-note">Escopo previsto. A contratação ainda não está disponível.</p>
<div class="detail-groups">@for(group of selectedGroups();track group.name;let first=$first){<details [open]="first"><summary>{{group.name}} <span>{{group.rows.length}} recursos</span></summary><ul>@for(row of group.rows;track row.key){<li><span>{{row.name}}</span><span class="availability" [class.ready]="data.available_features.includes(row.key)">{{data.available_features.includes(row.key)?'Implementado':'Planejado'}}</span></li>}</ul></details>}</div>
}
</dialog>
}
<footer class="plans-footer"><span>Sistema Digital Financeiro</span><span>Empresarial · Financeiro e gestão de serviços</span></footer>
</main></div>`})
export class SubscriptionPage {
  readonly session=inject(Session);private http=inject(HttpClient);
  readonly embedded=inject(ActivatedRoute).snapshot.data['embedded']===true;
  readonly catalog=signal<ProductCatalog|null>(null);readonly loading=signal(false);readonly error=signal('');
  readonly selected=signal('');readonly rows=comparisonRows;
  readonly selectedPlan=computed(()=>this.catalog()?.plans.find(plan=>plan.key===this.selected()));
  readonly selectedGroups=computed(()=>{const plan=this.selectedPlan();if(!plan)return [];const groups=new Map<string,typeof comparisonRows>();for(const row of this.rows){if(plan.features.includes(row.key)){const group=groups.get(row.group)||[];group.push(row);groups.set(row.group,group);}}return Array.from(groups,([name,rows])=>({name,rows}));});
  @ViewChild('planDetail')planDetail?:ElementRef<HTMLDialogElement>;
  constructor(){void this.load();}
  info(key:string){return presentation[key] || presentation['ESSENTIAL'];}
  async load(){if(this.loading())return;this.loading.set(true);this.error.set('');
    try{const result=await firstValueFrom(this.http.get<ProductCatalog>('/api/v1/catalog/plans').pipe(timeout(15000)));this.catalog.set(result);}
    catch{this.error.set('Não foi possível carregar os planos. Tente novamente mais tarde.');}finally{this.loading.set(false);}}
  viewPlan(key:string){if(!this.catalog()?.plans.some(plan=>plan.key===key))return;this.selected.set(key);const dialog=this.planDetail?.nativeElement;if(dialog && !dialog.open)dialog.showModal();}
}
