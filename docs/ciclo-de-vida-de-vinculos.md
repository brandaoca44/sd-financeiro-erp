# Ativação e desativação de vínculos

## Comportamento

O Master pode ativar ou desativar um **vínculo existente na sua organização**.
Isso não altera a identidade global, a senha, sessões ou vínculos em outros tenants.
Um usuário desativado em uma organização ainda pode autenticar e operar outra
organização em que continue autorizado. A autorização do tenant desativado é
negada na próxima verificação; não há logout global forçado.

O próprio Master atual não pode ser alterado por essa rota, nem mesmo com pedido
de ativação. Primeiro deve transferir a propriedade para outro usuário/vínculo
ativos pelo fluxo protegido existente. Depois, o novo Master pode desativar o
vínculo do proprietário anterior. Delegados e operadores da plataforma não recebem
esse poder automaticamente; a permissão `identity.members.manage` é exclusiva do Master.

Na desativação, a mesma transação:

- Define o vínculo como `INACTIVE` e remove sua concessão antiga de leitura.
- Inativa os perfis atribuídos ao vínculo, incrementando suas revisões.
- Inativa sua delegação, incrementa a revisão e inativa atribuições originadas dela
  na organização, inclusive as concedidas a outros membros.
- Revoga convites pendentes emitidos pelo alvo ou destinados ao seu e-mail nessa
  organização. Convites já aceitos e convites de outras organizações são preservados.
- Registra ator, tenant, alvo, status/revisões e contagens mínimas de concessões
  processadas. Falha de auditoria reverte toda a alteração.

Reativar **não restaura acesso anterior**: mantém leitura antiga desabilitada,
perfis e delegação inativos. Também processa concessões remanescentes para impedir
reativação de acessos inseridos fora do fluxo normal. O Master deverá revisar e
atribuir novamente os perfis necessários com as revisões atuais. Uma conta global
inativa não pode ser ativada por esse fluxo.

Pedir `ACTIVE` para vínculo já ativo preserva suas concessões e ainda incrementa
a revisão do vínculo. Pedir `INACTIVE` novamente, com a revisão atual, executa a
limpeza de segurança novamente. Repetir uma revisão antiga retorna conflito.

## Contrato HTTP

| Método e rota | Condição e resposta |
| --- | --- |
| `GET /api/v1/organizations/{organization_id}/members/{user_id}/status` | Sessão do Master atual; consulta mínima |
| `PUT /api/v1/organizations/{organization_id}/members/{user_id}/status` | Sessão do Master atual e confirmação da própria senha; alteração transacional |

Corpo do PUT, com senha apenas ilustrativa:

```json
{
  "status": "INACTIVE",
  "expected_revision": 1,
  "password": "SENHA_DO_MASTER"
}
```

`status` aceita somente `ACTIVE` ou `INACTIVE`. `expected_revision` deve ser inteiro
positivo e corresponder ao vínculo consultado. Não aceita status global, permissões,
empresa ou identificador do ator no corpo. Autor vem exclusivamente da sessão.

Ambas as respostas de sucesso são HTTP 200 e contêm somente `user_id`, `status`
e `revision`. O diretório já existente também informa a revisão do vínculo ao Master.
Revisões das atribuições/delegações são independentes: após desativar/reativar,
consultar as revisões atuais antes de conceder perfis ou delegação novamente.

| HTTP | Significado |
| --- | --- |
| 401 | Sessão ausente, inválida, expirada ou revogada |
| 404 | Operação recusada, senha incorreta, Master protegido, alvo ausente ou fora do tenant, sem distinguir a causa |
| 409 | Revisão desatualizada, inclusive em requisições concorrentes |
| 413 / 415 / 422 | Corpo acima de 4096 bytes, formato não JSON ou entrada inválida, sem reproduzir valores |
| 429 | Limite compartilhado da gestão de acesso, com `Retry-After` |
| 503 / 500 | Infraestrutura/capacidade/configuração indisponível ou erro inesperado, sem detalhes internos |

PUT compartilha com a gestão de perfis o limite de 5 admissões por ator/15 minutos,
30 por origem/minuto e 300 gerais/minuto. Redis indisponível impede alterações;
logout permanece disponível. Há concorrência limitada de Argon2, incluindo no
cancelamento. Todas as respostas usam `Cache-Control: no-store`, e HTTPS é exigido
em staging/production. Somente ações autorizadas e concluídas renovam inatividade.

Locks na organização, propriedade, usuários e vínculos serializam a alteração
com atribuições e transferência. Uma disputa entre desativar um membro e torná-lo
Master não deixa um proprietário inativo: a operação incompatível é recusada.
Não existe exclusão física de vínculo pela API.

## Persistência e limites

`MembershipService` reutiliza a autorização, reautenticação e auditoria da gestão
de acesso. A migration `b92f8d06e4a1`, após `a81e73c405bf`, adiciona revisão positiva
ao vínculo e a ação `MEMBERSHIP_SET` ao histórico. Upgrade não muda status, flags,
usuários ou permissões existentes.

Downgrade é recusado quando já existe histórico `MEMBERSHIP_SET`: registros de
segurança não são apagados para forçar compatibilidade com uma versão anterior.
O downgrade transacional sem esse histórico é coberto pelos testes.

A proteção do Master vale para os fluxos da aplicação. Alterações privilegiadas
diretas no banco exigem controle operacional próprio. Administração do status
global de usuários, recuperação de Master indisponível e exclusão de contas não
foram introduzidas nesta etapa. Entrega/verificação de e-mail e controles restantes
de produção continuam pendentes.

## Validação

Suíte completa: **274 testes aprovados**, incluindo 26 novos (22 HTTP, 3 de schemas
e 1 de migrations). Os testes cobrem isolamento, revogação sem restauração implícita,
conta global preservada, proteção do Master, transferência concorrente, revisões,
rate limit, cancelamento de hash, rollback de auditoria e bloqueio de downgrade
que perderia histórico.

Migration aplicada ao PostgreSQL local do ERP em `b92f8d06e4a1 (head)`, porta 5433.
Schema alinhado aos models, flags/status/contagens anteriores preservados e nenhum
vínculo real alterado. Não restaram bancos temporários. A API local respondeu health
200, publicou GET/PUT de status no OpenAPI e recusou ambas as operações sem sessão
com 401 e `no-store`. Testes de sucesso usaram infraestrutura isolada, sem senhas
ou tokens reais do desenvolvedor.
