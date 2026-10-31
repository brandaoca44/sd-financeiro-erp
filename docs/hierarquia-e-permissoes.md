# Hierarquia, perfis e permissões

Status: primeira etapa de persistência implementada e validada em banco temporário.
A migration ainda não foi aplicada ao banco local. Não há proprietários ou perfis
atribuídos automaticamente, novas rotas ou alteração das concessões existentes.
A política atual continua exigindo usuário ativo, vínculo e permissão de leitura.

## Persistência implementada

Os models estão em `identity/access_models.py`, com migration `d2a6f09b84c1`:

| Estrutura | Finalidade | Proteção de integridade |
| --- | --- | --- |
| `OrganizationOwnership` | Registrar o proprietário do tenant | No máximo um por organização, com vínculo existente no mesmo tenant |
| `OrganizationRole` | Definir perfil com nome e categoria | Nome único por organização, sem diferenciar maiúsculas/minúsculas; status inicial inativo |
| `OrganizationRoleAssignment` | Atribuir perfil a um vínculo | FKs compostas impedem perfil ou vínculo de outro tenant; atribuição inicial inativa |

As sete categorias propostas estão disponíveis, além de `CUSTOM` para perfis
personalizados. Categoria é classificação, sem nível numérico ou herança. Não há
perfis pré-preenchidos nem permissões de módulos futuros.

O banco exige existência e pertencimento dos vínculos. Verificações de usuário e
vínculo ativos, designação inicial, transferência e proteção contra desativação do
proprietário pertencem ao próximo fluxo de aplicação. Organizações já existentes
permanecem sem proprietário até uma designação explícita. Este incremento não
altera a autorização atual nem implementa permissões por empresa ou delegação.

Doze testes novos cobrem constraints, defaults no ORM e no banco, isolamento,
ausência de privilégios implícitos e downgrade/upgrade com preservação das estruturas
anteriores. O catálogo de ações e sua integração à política continuam pendentes.

## Segmentos e áreas atendidas

Os segmentos previstos no master prompt são Saúde, Varejo, Indústria e Serviços.
O core permanece empresarial generalista. Novos segmentos precisam de definição
própria; não presumir cobertura de qualquer atividade ou antecipar suas regras.

| Camada | Cobertura planejada |
| --- | --- |
| Base comum | Organizações, empresas, usuários, cadastros, financeiro, comercial, compras, estoque, fiscal, relatórios e painel de oportunidades |
| Saúde | Gestão de suprimentos, medicamentos, lotes, validade, rastreabilidade, convênios, faturamento e centros de custo hospitalares |
| Varejo | PDV, caixa, fechamento, promoções, estoque por loja e integrações fiscais/comerciais |
| Indústria | Matérias-primas, ficha técnica/BOM, ordens de produção, apontamentos, planejamento e custos industriais |
| Serviços | Perfis específicos a detalhar conforme os primeiros fluxos de prestação de serviços escolhidos |

Segmento é o tipo de negócio; área é uma responsabilidade dentro dele. Uma empresa
de saúde também precisa de financeiro, compras e estoque, mas isso não concede
acesso a informações de todas essas áreas a cada usuário. Regras clínicas e novos
módulos, como RH ou contabilidade completa, não estão automaticamente incluídos.

As permissões comuns serão reutilizadas pelas verticais. Permissões específicas
serão introduzidas com suas funcionalidades, mantendo o isolamento e evitando
forks da política de segurança. Cada vertical poderá continuar em repositório próprio,
conforme a estratégia do produto; o mecanismo de compartilhamento ainda será definido.

## Proprietário, cargos e perfis

O proprietário da organização cliente será o **Master**. No futuro fluxo de abertura
da organização pelo cliente, o responsável criador será registrado como proprietário
na mesma transação dos vínculos iniciais. Se a plataforma provisionar o cliente,
o proprietário deverá ser indicado explicitamente, sem tornar automaticamente o
operador da plataforma dono dos dados do cliente. Esse onboarding ainda será implementado.

O proprietário pode administrar usuários, perfis e delegações dentro de sua organização.
Não pode acessar outro tenant nem obter permissões administrativas da plataforma.
O operador inicial do SD Financeiro continua sendo uma identidade separada, com
permissão de provisionamento e sem leitura global dos dados dos clientes.

Cargo representa posição organizacional. Perfil reúne permissões. Uma pessoa pode
ser gerente de compras e não ter acesso ao fiscal ou ao financeiro. Os nomes abaixo
são modelos iniciais adaptáveis; a ordem entre liderança, gerência e coordenação
depende da estrutura do cliente e não gera herança automática de privilégios.

| Categoria | Responsabilidade típica | Limite de acesso sugerido |
| --- | --- | --- |
| Colaborador | Executar tarefas específicas | Ações pontuais da função |
| Auxiliar | Apoiar uma área | Cadastros e operações assistidas, sem aprovações críticas |
| Líder | Acompanhar equipe e execução | Visão da equipe e aprovações explicitamente delegadas |
| Gerente | Gerir uma área ou unidade | Indicadores e operações da área, dentro de escopo e alçadas |
| Coordenador | Coordenar processos ou equipes | Acesso transversal somente aos processos autorizados |
| Diretor | Acompanhar áreas sob sua responsabilidade | Visão gerencial e aprovações de alçada superior, quando concedidas |
| CEO | Acompanhar a empresa ou grupo | Indicadores estratégicos autorizados, sem administração técnica automática |
| Proprietário/Master | Controlar a organização e suas delegações | Administração do tenant; transferência de propriedade por fluxo específico |

Uma pessoa pode acumular funções. CEO e Master podem ser a mesma pessoa, mas são
conceitos independentes. Não usar um número de cargo para liberar todas as ações
de cargos supostamente inferiores.

## Permissões por recurso, ação e escopo

Uma concessão deverá responder: **qual ação, sobre qual recurso, em qual empresa?**

| Área/recurso | Ações a separar conforme a funcionalidade |
| --- | --- |
| Produtos e serviços | Consultar, cadastrar, editar, inativar e alterar preços |
| Comercial | Consultar, elaborar proposta/pedido, conceder desconto e aprovar |
| Compras | Solicitar, cotar, emitir pedido e aprovar compra |
| Estoque | Consultar saldo, movimentar, transferir e aprovar ajustes |
| Financeiro | Consultar, lançar títulos, aprovar pagamentos, executar e conciliar |
| Fiscal | Consultar documentos, preparar, emitir/cancelar e acessar obrigações |
| Relatórios e oportunidades | Consultar indicadores, detalhar dados e exportar |
| Administração de acesso | Convidar, ativar/desativar, atribuir perfis e administrar perfis |
| Vertical específica | Ações próprias, registradas somente quando o módulo existir |

Essas ações são exemplos para o catálogo futuro, não endpoints ou permissões já
implementadas. Chaves estáveis poderão seguir `area.recurso.acao`, como
`catalog.products.create` e `fiscal.documents.read`. Não criar permissões coringa
que liberem automaticamente módulos futuros.

Exemplos de perfis: Auxiliar de Cadastro, Analista Fiscal, Operador de Caixa,
Comprador, Gerente Financeiro e Diretor de Operações. O perfil “Auxiliar de Cadastro”
pode permitir cadastrar produtos/serviços sem alterar preços ou consultar tributos.
O perfil “Analista Fiscal” pode permitir a área fiscal sem acesso a pagamentos.

O escopo combina organização obrigatória e empresas autorizadas. Unidades, centros
de custo e equipes serão adicionados somente quando modelados. Acesso a todas as
empresas deve ser uma concessão explícita; acesso a empresas futuras não será inferido.
Restringir exportação e detalhamento independentemente da visualização de um gráfico.

## Controles de delegação

- Negar por padrão. Exigir usuário e vínculo ativos, permissão conhecida e escopo
  autorizado. Falta de informação ou erro na avaliação não concede acesso.
- Não aceitar autoatribuição de cargo, perfil, propriedade ou permissão no cadastro.
  O frontend pode ocultar menus, mas cada operação é validada novamente no servidor.
- O proprietário pode delegar administração de usuários, com teto explícito de
  permissões e escopo. Delegados não podem conceder além desse teto, promover-se
  a Master ou conceder o direito de redelegar sem autorização específica.
- Cada concessão considera a origem da autoridade. Acumular dois perfis operacionais
  não deve permitir contornar o teto de delegação administrativa.
- Separar execução e aprovação quando o processo exigir. Cargo elevado não autoriza
  aprovar a própria operação ou exceder alçadas automaticamente. Valores e regras
  serão definidos nos respectivos módulos, sem motor de aprovação antecipado.
- Manter um proprietário responsável por organização. Transferência deve ser
  explícita, transacional, auditada e com reautenticação; não remover/desativar o
  proprietário por um fluxo comum que deixe a organização sem administração.
- Convites não criam sessões ou acesso antes da aceitação e ativação previstas no
  fluxo. Tokens de convite deverão ser únicos, expiráveis e armazenados por hash.
- Auditar quem concedeu, alterou ou revogou acesso, quando e em qual escopo, sem
  senhas ou tokens. Revogações devem valer nas próximas verificações, incluindo
  APIs, gráficos, exports e rotinas em segundo plano.
- Regras para substituir proprietário indisponível exigem recuperação administrativa
  própria e verificação de legitimidade. Não reutilizar o bootstrap para isso.

## Implementação incremental proposta

1. Concluído nesta etapa: persistir proprietário, perfis e atribuições por tenant
   com integridade contra referências a outro tenant. Nenhum usuário existente
   vira Master implicitamente. Migration aguarda revisão antes de aplicação local.
2. Definir a atribuição inicial de proprietário no provisionamento e sua transferência.
   Tratar organizações existentes sem proprietário explicitamente.
3. Implementar cadastro/convite de usuários e delegação administrativa com auditoria
   mínima e sem conhecimento da senha do convidado pelo administrador.
4. Aplicar o catálogo às funcionalidades existentes, mantendo a proteção atual e
   validando a migração das concessões anteriores sem ampliar acesso silenciosamente.
5. Acrescentar perfis e permissões de áreas e verticais conforme seus módulos forem
   implementados. Construir a interface de gestão após estabilizar os contratos.

Critérios de validação: isolamento entre tenants e empresas, proibição de
autoelevação, limites de delegação, proteção do proprietário, revogação, concorrência
na transferência e execução/aprovação separadas quando aplicáveis. Testar primeiro
em banco temporário; o ambiente real só recebe migrations revisadas.
