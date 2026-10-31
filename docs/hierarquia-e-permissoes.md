# Hierarquia, perfis e permissões

Status: persistência, serviço e rotas de designação/transferência implementados.
Migrations aplicadas ao PostgreSQL local do ERP, porta 5433, em `e96b2130ad74`.
Não há proprietários ou perfis atribuídos automaticamente ou alteração das concessões existentes.
A política exige usuário/vínculo ativos e concessão válida. O [catálogo e a gestão
de perfis](perfis-e-permissoes.md) integram perfis à leitura, preservando flags antigas.

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

O banco exige existência e pertencimento dos vínculos. O serviço de propriedade
verifica usuários e vínculos ativos. O [ciclo dos vínculos](ciclo-de-vida-de-vinculos.md)
protege o Master atual contra desativação e exige transferência prévia. Organizações existentes
permanecem sem proprietário até uma designação explícita. A [leitura de cadastro
por empresa](acesso-por-empresa.md) exige concessão específica; permissões dos módulos
futuros permanecem pendentes. Delegação de perfis não concede autoridade por empresa.

Doze testes novos cobrem constraints, defaults no ORM e no banco, isolamento,
ausência de privilégios implícitos e downgrade/upgrade com preservação das estruturas
anteriores. O catálogo de ações já está integrado às funcionalidades existentes,
com alterações administrativas reautenticadas e auditadas.

## Designação e transferência implementadas

`identity/ownership.py` oferece dois casos de uso, expostos por `api/v1/ownership.py`:

- `designate`: operador ativo com permissão de provisionamento indica o primeiro
  proprietário de uma organização ativa que ainda não tenha proprietário.
- `transfer`: apenas o proprietário atual, com vínculo ativo, pode transferir para
  outro usuário ativo que já tenha vínculo ativo na mesma organização.

Ambos exigem token de sessão válido e confirmação da senha do próprio ator.
O serviço identifica o ator pelo token, sem aceitar um identificador de autor do
cliente. Revalida expiração e revogação depois da verificação de senha. Designação
não cria nem ativa vínculo e não torna o operador proprietário implicitamente.
Transferência não concede permissões da plataforma nem altera concessões de leitura.
O antigo proprietário mantém seus vínculos/perfis; perde a autoridade de transferir.

Cada chamada usa uma sessão de escrita nova e transação própria. Locks na organização
serializam designações e transferências concorrentes; usuários, credencial, sessão,
proprietário e vínculos são bloqueados durante a validação. A espera por locks tem
limite de cinco segundos. Falhas de autoridade usam mensagem única; falhas de banco
recebem tratamento seguro no adaptador HTTP, sem conceder acesso.

A migration `e7b1c90a42d3`, após `d2a6f09b84c1`, adiciona `OwnershipChange`.
O histórico grava organização, ator, proprietário anterior, novo proprietário e
horário, na mesma transação. Não contém senha, hash, token, nome ou e-mail.
Se essa gravação falhar, a mudança de propriedade também é revertida. O serviço não
oferece alteração ou exclusão do histórico; a tabela não é um armazenamento imutável
contra administradores com acesso direto ao banco. Downgrade remove esse histórico.

Quatorze testes novos cobrem autoridade, senha, sessão expirada/revogada, logout
durante a reautenticação, vínculos inativos ou de outro tenant, atomicidade,
concorrência e migrations. Testes HTTP adicionais cobrem os limites de tentativas,
cancelamento, concorrência compartilhada com login e respostas mínimas e seguras.
Onboarding e convites estão descritos no [fluxo implementado](onboarding-e-convites.md).
Recuperação de proprietário indisponível continua pendente.

### Contrato HTTP

Requer Bearer e JSON com somente `new_owner_id` (UUID do destinatário) e `password`
(senha do ator, de 1 a 128 caracteres para verificação; não altera a política de cadastro).

| POST | Autoridade necessária |
| --- | --- |
| `/api/v1/organizations/{organization_id}/ownership/designate` | Provisionador ativo; organização ativa e sem proprietário |
| `/api/v1/organizations/{organization_id}/ownership/transfer` | Proprietário atual ativo com vínculo ativo; destinatário diferente |

Sucesso retorna **204 sem corpo**, com `Cache-Control: no-store`. O prazo de
inatividade da sessão é renovado na mesma transação, somente em caso de sucesso.
Sessão inválida retorna 401. Organização, autoridade, destinatário ou senha recusados
retornam o mesmo 404: `Não foi possível alterar o proprietário.` Não há consulta
pública de usuários ou de proprietário para descobrir destinatários.

As duas rotas compartilham contadores Redis próprios: **5 admissões por ator em
15 minutos, 30 por origem/minuto e 300 gerais/minuto**. Esses valores iniciais são
definidos no servidor, independentes dos ajustes `AUTH_ACCOUNT_*` do login.
O identificador do ator vem da sessão; trocar token, tenant ou destinatário não
reinicia seu contador. Chaves protegem UUID e IP com HMAC. O IP vem da conexão,
sem interpretar headers encaminhados. Recusa retorna 429 com `Retry-After`.

Login e propriedade compartilham `AUTH_HASH_CONCURRENCY` por worker e espera máxima
de 250 ms por vaga. Cancelamento mantém a vaga até terminar Argon2 e reverte a
mudança. Redis indisponível, falta de configuração, capacidade esgotada ou falha de
banco retornam 503; logout continua disponível. Erros inesperados retornam 500
genérico, inclusive com debug ligado. Corpo limitado a 4096 bytes; 413 para excesso,
415 para formato não JSON, 422 para dados inválidos ou extras, sem refletir entradas.
HTTPS é exigido em staging/production. Não repetir automaticamente uma operação
com resultado incerto: o histórico interno permite investigação, mas ainda não há
contrato de idempotência para cliente HTTP.

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
   vira Master implicitamente. Migrations revisadas e aplicadas ao banco local após testes.
2. Designação explícita e transferência concluídas, com contratos e rotas protegidas
   por reautenticação limitada. Não há backfill automático de organizações.
3. Onboarding e convites implementados: cadastro ou confirmação de conta no aceite,
   primeiro Master e vínculos mínimos, revogação e trilha de emissão/aceite/revogação.
   Administrador não define senha do convidado. Atribuição de perfis pode ser delegada
   com teto; ativação/desativação de vínculos implementada com proteção do Master.
   Só Master convida colaboradores. Administração global de usuários permanece separada.
4. Catálogo e gestão de perfis implementados nas funcionalidades existentes, com
   concessões de leitura, atribuições e tetos de delegação auditados. Flags anteriores
   preservadas; conversão de leitura já disponível por operação explícita, restrita
   e auditada, sem ampliar acesso. Remoção da flag e novos contratos não são automáticos.
5. Acrescentar perfis e permissões de áreas e verticais conforme seus módulos forem
   implementados. Construir a interface de gestão após estabilizar os contratos.

Critérios de validação: isolamento entre tenants e empresas, proibição de
autoelevação, limites de delegação, proteção do proprietário, revogação, concorrência
na transferência e execução/aprovação separadas quando aplicáveis. Testar primeiro
em banco temporário; o ambiente real só recebe migrations revisadas.

Validação da etapa de propriedade: suíte completa com 173 testes aprovada. No banco local,
Alembic confirmou alinhamento do schema, contagens anteriores preservadas e nenhum
proprietário automático. Health respondeu 200; ambas as rotas constam no OpenAPI
e retornam 401 sem sessão. Sucesso com credenciais foi testado apenas na infraestrutura
isolada; não foram usadas credenciais reais do desenvolvedor para transferir propriedade.
Após onboarding/convites, a suíte completa passou a 208 testes; a validação atual
está no [documento de convites](onboarding-e-convites.md#respostas-e-operação-local).
Após perfis e permissões, a suíte completa passou a 248 testes. A validação atual
está no [contrato de perfis](perfis-e-permissoes.md#validação-da-entrega).
Com o ciclo de vida dos vínculos, a suíte completa passou a 274 testes. Validação
atual no [contrato de vínculos](ciclo-de-vida-de-vinculos.md#validação).
Após revisão de leitura antiga, a suíte passou a 302 testes. Validação atual no
[contrato de revisão de acessos](revisao-de-acessos.md#validação-da-entrega).
Com o cadastro jurídico de Company, a suíte passou a 332 testes. Validação atual
no [contrato de empresas](api-companies.md#validação-da-entrega). Cadastro de empresas
é administrado pelo Master; colaboradores só consultam empresas mediante concessão
específica. Permissões operacionais dos módulos futuros continuam separadas.

Com a leitura por empresa, a suíte passou a 363 testes. Validação atual no
[contrato de acesso por empresa](acesso-por-empresa.md).
