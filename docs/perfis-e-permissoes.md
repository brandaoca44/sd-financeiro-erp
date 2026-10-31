# Catálogo de permissões e gestão de perfis

## Regras implementadas

O catálogo cobre somente ações existentes. O escopo desta entrega é a organização
exata da rota, sem empresas, módulos futuros, curingas ou herança entre cargos.
Categoria como CEO ou Gerente apenas classifica o perfil; não concede autoridade.

| Chave | Como é concedida |
| --- | --- |
| `organizations.read` | Perfil ativo atribuído ao vínculo ativo, ou concessão anterior `can_read_organization` |
| `identity.roles.read` | Perfil ativo atribuído ao vínculo ativo, ou Master atual |
| `identity.roles.manage` | Somente Master atual |
| `identity.assignments.manage` | Master atual ou delegação explícita com teto |
| `identity.delegations.manage` | Somente Master atual |
| `identity.members.read` | Somente Master atual |
| `identity.members.manage` | Somente Master atual; ciclo de vida protegido |

Somente as duas primeiras chaves podem compor perfis ou tetos. As demais descrevem
regras administrativas específicas, sem concessão por perfil. Somar perfis não cria
autoridade de delegação. Provisionamento continua separado no usuário da plataforma;
convites continuam restritos ao Master/provisionador conforme seu tipo, e propriedade
continua no fluxo protegido de transferência. Nenhuma dessas ações nasce do cargo.

Master exige usuário e vínculo ativos. Não recebe leitura de dados empresariais
implicitamente: pode atribuir a si um perfil operacional de leitura de forma explícita
e auditada. Isso não o torna operador da plataforma.

## Fluxo básico

1. Master consulta o catálogo e cria um perfil, com nome, categoria, status e
   permissões explícitas. Perfil começa **inativo** e sem permissões por padrão.
2. Consulta o diretório mínimo da organização para identificar o vínculo existente.
3. Atribui um perfil ativo ao vínculo ativo de usuário ativo, confirmando a própria
   senha. Atribuição não cria usuário, não reativa vínculo e não concede leitura antiga.
4. Para retirar essa fonte de acesso, inativa a atribuição ou o perfil. Revogação
   vale na próxima avaliação; não encerra à força toda a sessão nem outras concessões.

Editar permissões de um perfil afeta seus vínculos ativos. O nome deve ser único
na organização, sem distinguir maiúsculas/minúsculas. Perfis de organizações distintas
podem usar o mesmo nome. Não há exclusão física dos perfis ou concessões pela API.

## Delegação com teto

Somente Master pode delegar atribuição/revogação de perfis, indicando um vínculo e
um teto explícito, por exemplo `["organizations.read"]`. Delegação começa inativa
no banco; ativá-la pela API exige teto não vazio. O delegado:

- Só atribui ou revoga perfis cujas permissões estejam inteiramente no teto.
- Não amplia o teto usando suas próprias permissões ou a soma de seus perfis.
- Não altera o próprio vínculo, o Master ou vínculos com registro de delegação.
- Não cria/edita perfis, concede delegações, transfere Master ou administra plataforma.
- Pode consultar atribuições dentro do teto para um UUID de vínculo conhecido,
  sem receber nome/e-mail ou descobrir todos os membros da organização.

As atribuições registram a origem da autoridade e a revisão da delegação. Mudar
o teto, inativar ou renovar uma delegação incrementa sua revisão e invalida as
atribuições emitidas pela revisão anterior. Reativar o mesmo teto **não reativa
essas atribuições**: é preciso confirmá-las novamente, com revisões atuais.

Transferir Master incrementa a revisão da propriedade e invalida as delegações
anteriores, mesmo se o proprietário antigo voltar depois. A origem delegada também
exige Master e delegado com usuário/vínculo ativos. Um perfil ampliado pelo Master
não permite que atribuições de origem delegada ultrapassem seu teto.

Master pode confirmar uma atribuição como concessão direta, com nova revisão e
auditoria. Nesse caso ela deixa de depender da delegação anterior. Concessões
diretas do Master e permissões antigas não são apagadas pela revogação de delegação.

## Contratos HTTP

Todas as rotas exigem Bearer. Escritas também exigem `password` do próprio ator.
Campos extras, chaves desconhecidas, permissões administrativas em perfis e escopos
de empresa são recusados. Senhas, hashes, tokens ou configurações não são retornados.

| Método e rota | Autoridade e resultado |
| --- | --- |
| `GET /api/v1/auth/permissions` | Qualquer sessão válida; catálogo estático, sem concessões ou dados de usuários |
| `GET /api/v1/organizations/{org}/roles` | Master ou `identity.roles.read`; página de perfis |
| `POST /api/v1/organizations/{org}/roles` | Master; cria perfil e retorna 201 |
| `PUT /api/v1/organizations/{org}/roles/{role}` | Master; substitui configuração e retorna 200 |
| `GET /api/v1/organizations/{org}/members` | Master; diretório mínimo paginado |
| `GET /api/v1/organizations/{org}/members/{user}/roles` | Master ou delegado dentro do teto; atribuições paginadas |
| `PUT /api/v1/organizations/{org}/members/{user}/roles/{role}` | Master ou delegado limitado; define status da atribuição |
| `GET /api/v1/organizations/{org}/members/{user}/delegation` | Master; configuração ou `null` se ainda inexistente |
| `PUT /api/v1/organizations/{org}/members/{user}/delegation` | Master; define status e teto da delegação |

Criação de perfil recebe `name`, `category` opcional, `status` opcional e `permissions`
opcional, além da senha. PUT de perfil é substituição completa: enviar nome,
categoria, status, permissões e `expected_revision` atual. Permissões omitidas ficam
vazias; status omitido fica inativo. Resposta contém somente `id`, `name`, `category`,
`status`, `permissions` e `revision`.

PUT de atribuição recebe `status`, `expected_revision`, `expected_role_revision`
e senha. Revisão de atribuição deve ser **0 para criar**; nas próximas alterações,
usar a revisão retornada. A revisão do perfil deve corresponder à configuração
consultada, impedindo atribuir um perfil que foi alterado entre leitura e escrita.

PUT de delegação recebe `status`, `permissions` como teto, `expected_revision`
e senha. Revisão **0 para criar**, ou revisão atual para alterar. A resposta inclui
`effective`: um registro pode estar configurado ativo, mas sem autoridade efetiva
porque mudou o Master ou um vínculo ficou inativo.

Páginas retornam `items` e `next_cursor`; aceitar `cursor` UUID e `limit` de 1 a
100, padrão 50. O diretório entrega apenas UUID, nome, e-mail, status do vínculo e
indicador `legacy_read`, somente ao Master. Atribuições entregam UUIDs, status e
revisão. O diretório também inclui `revision` do vínculo para alterações de status.
Delegados não consultam vínculos administrativos ou perfis fora do teto.

| HTTP | Situação |
| --- | --- |
| 401 | Sessão ausente ou inválida |
| 404 | Operação não autorizada, senha incorreta ou recurso fora do tenant, sem distinguir a causa |
| 409 | Revisão desatualizada ou nome de perfil já utilizado no tenant autorizado |
| 413 / 415 / 422 | Corpo acima de 4096 bytes, formato não JSON ou entrada inválida, sem reproduzir valores |
| 429 | Limite excedido, com `Retry-After` |
| 503 / 500 | Falha de infraestrutura/capacidade/configuração ou erro inesperado, sem detalhes internos |

Respostas usam `Cache-Control: no-store`. HTTPS é exigido em staging/production.
Escritas compartilham limite próprio de 5 admissões por ator/15 minutos, 30 por
origem/minuto e 300 gerais/minuto. Contadores são separados de login, propriedade
e convites. Trocar sessão ou headers encaminhados não reinicia o contador do ator.
Redis indisponível impede escrita; logout permanece disponível.

`AUTH_HASH_CONCURRENCY` é compartilhado com os demais fluxos de senha. Cancelamento
aguarda o fim de Argon2 antes de liberar a vaga e reverte a transação. Locks por
organização e revisões protegem alterações concorrentes. Sucesso registra atividade;
recusas não renovam sessão. Consultar o catálogo não mantém a sessão viva.

## Compatibilidade, auditoria e limites

A migration `a81e73c405bf`, após `f3a82c17d905`, adiciona concessões, delegações,
auditoria e revisões, sem semear permissões ou converter flags antigas. Perfis
preexistentes continuam sem permissões até uma alteração explícita e auditada.
Conhecer um cargo ou UUID não concede acesso.

`can_read_organization` e `can_provision_organizations` são preservados. Leitura do
tenant combina concessão antiga **ou** perfil autorizado. Retirar um perfil não
revoga uma concessão antiga; conferir `legacy_read` quando houver acesso remanescente.
A conversão dessas flags exige um incremento próprio, sem ampliar acesso silenciosamente.

Cada escrita registra ator, tenant, alvo, ação e estados mínimos de status,
permissões, revisões e origem. Não grava senha, token, nome ou e-mail nos snapshots.
Se a auditoria falhar, toda a mudança é revertida. Não há API para apagar o histórico;
isso não é imutabilidade contra um administrador com acesso direto ao banco.

Downgrade remove concessões e auditoria desta migration. Antes de remover a origem,
inativa atribuições delegadas para não transformá-las em concessões diretas. Não
usar downgrade como mecanismo de revogação de produção.

O [ciclo de vida dos vínculos](ciclo-de-vida-de-vinculos.md) já oferece ativação e
desativação protegidas. Desativação explícita remove a leitura antiga e inativa perfis
e delegações; reativação não restaura essas concessões. Ainda pendentes: administração
global/recuperação do proprietário, conversão das flags antigas, permissões por empresa e dos módulos futuros, interface
de gestão e entrega/verificação de e-mail antes da produção. Não há liberação fiscal,
financeira, clínica, de produtos ou serviços sem os módulos e contratos correspondentes.

## Validação da entrega

Na etapa de perfis: **248 testes aprovados**, incluindo 40 novos de perfis. Cobertura
inclui isolamento, ausência de privilégios por cargo, preservação das flags,
limites de delegação, proibição de autoelevação/redelegação, origem das concessões,
transferência e retorno do Master, revogação concorrente, revisões, rate limit,
cancelamento de hash, auditoria transacional e downgrade/upgrade com schema alinhado.

Migration aplicada ao PostgreSQL local em `a81e73c405bf (head)`, porta 5433.
Contagens, flags e status anteriores foram preservados. Nenhuma concessão de perfil
ou delegação real foi criada; não restaram bancos temporários. Health local 200,
sete caminhos novos no OpenAPI e recusa 401 nas consultas/escritas sem sessão.
Sucesso com credenciais foi validado na infraestrutura isolada, sem uso das senhas
ou tokens reais do desenvolvedor.
Depois do ciclo de vínculos, a suíte passou a 274 testes; a validação atual está
no [documento de vínculos](ciclo-de-vida-de-vinculos.md#validação).
