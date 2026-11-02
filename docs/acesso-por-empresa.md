# Acesso de colaboradores por empresa

## Escopo implementado

O Master pode conceder `companies.read` a um vínculo existente para uma empresa
exata da organização. Essa permissão consulta somente o cadastro jurídico:
razão social, nome fantasia, CNPJ, status e metadados do cadastro. Operações
financeiras, fiscais, edição de empresas e administração de usuários têm regras
próprias e não são concedidas por essa autorização.

O catálogo identifica `companies.read` como escopo `COMPANY`, com origem
`OWNER_OR_COMPANY_GRANT`. `companies.access.manage` é exclusiva do Master.
`companies.manage` continua exclusiva do Master para criação/edição de cadastros.
As [permissões financeiras](permissoes-financeiras.md) têm chaves e rotas próprias;
o contrato `read-access` deste documento não concede essas operações.
Essas chaves não podem entrar nos perfis ou tetos de delegação organizacionais.

A concessão combina organização, empresa, vínculo e chave conhecida. Não há
coringa, acesso a todas as empresas, herança por cargo ou concessão para empresas
futuras. Cadastrar o mesmo CNPJ em outro tenant não compartilha essa autorização.
Leitura de Organization, perfis organizacionais e provisionamento da plataforma
também não concedem leitura de empresas automaticamente.

## Fluxo e contratos

1. Master consulta o cadastro da empresa e o vínculo do colaborador, incluindo
   suas revisões atuais. O vínculo deve existir no mesmo tenant.
2. Define a concessão como `ACTIVE`, confirma a própria senha e informa as revisões
   da empresa, do vínculo e da concessão (0 quando ainda não houver registro).
3. O colaborador usa as rotas de Company existentes. A consulta por UUID e a
   listagem passam pela mesma política de visibilidade, avaliada no banco.
4. Para revogar, Master envia `INACTIVE` com as revisões atuais.

| Método e rota | Acesso e resposta |
| --- | --- |
| `GET /api/v1/organizations/{org}/companies/{company}/members/{user}/read-access` | Master; configuração mínima ou `null` se inexistente |
| `PUT /api/v1/organizations/{org}/companies/{company}/members/{user}/read-access` | Master com senha; cria/altera a concessão e retorna 200 |
| `GET /api/v1/organizations/{org}/companies` | Master ou colaborador com concessão efetiva; página de empresas visíveis |
| `GET /api/v1/organizations/{org}/companies/{company}` | Master ou concessão efetiva para a empresa exata |

Exemplo do PUT, com senha ilustrativa:

```json
{
  "status": "ACTIVE",
  "expected_revision": 0,
  "expected_company_revision": 1,
  "expected_membership_revision": 1,
  "password": "SENHA_DO_MASTER"
}
```

Não aceita chave de permissão, ator, escopo global, empresa ou organização no corpo.
A chave `companies.read` é definida pelo servidor; identificadores vêm da rota.
Para ativar, usuário, vínculo, organização e empresa devem estar ativos. Revogação
é permitida para alvo/empresa inativos, em organização ativa, sem reativá-los.
O Master atual não recebe nem perde seus direitos administrativos por essa rota;
pedidos para alterar a concessão do próprio proprietário são recusados.

Resposta de concessão contém apenas `company_id`, `user_id`, `permission_key`,
`status`, `revision`, `company_revision`, `membership_revision` e `effective`.
`effective` descreve essa concessão específica; o acesso administrativo do Master
é uma origem independente. A resposta não inclui nome, e-mail, CNPJ, senha ou token.

A listagem de Company aplica o filtro de autorização **antes** da paginação.
Mantém `items`, `next_cursor`, `limit` de 1 a 100 e `cursor` UUID. Sem concessões
efetivas, um colaborador recebe 404; ao terminar uma página autorizada, recebe
lista vazia. Master pode listar vazio e revisar empresas inativas. Colaborador só
vê empresas ativas para as quais tenha concessão ativa.

## Revogação e ciclo de vida

- Inativar uma concessão retira essa origem na próxima avaliação, preservando
  outros escopos e a sessão global do usuário. Não concede leitura de Organization.
- Desativar o vínculo inativa suas concessões de empresa naquele tenant e avança
  suas revisões. Outros tenants permanecem independentes.
- Inativar uma empresa inativa as concessões dela e avança suas revisões, sem
  alterar as concessões de outras empresas.
- Reativar vínculo ou empresa não restaura concessões antigas. A limpeza também
  é aplicada na reativação, impedindo recuperar concessões remanescentes por acidente.
  Master deve revisar e conceder novamente, com todas as revisões atuais.
- Editar nomes de uma empresa ativa preserva concessões, mas muda a revisão do
  cadastro: um formulário antigo de concessão deverá ser atualizado.
- Transferir Master muda quem administra as concessões. As concessões diretas já
  aprovadas persistem até revogação ou desativação; não são delegações administrativas.

Locks da organização serializam concessão, revogação, transferência e mudanças de
status. As três revisões evitam que uma solicitação antiga restabeleça acesso após
mudança no cadastro, no vínculo ou na concessão. Consulta não usa permissão embutida
no token nem cache de atributos ORM. Administração do status global da identidade
continua fora desta entrega; usuário globalmente inativo sempre tem acesso negado.

## Segurança e operação

Somente Master consulta/administra configurações de concessão, inclusive quando
um colaborador já pode consultar o cadastro da empresa. Delegação de atribuição de
perfis não permite conceder leitura de empresa nem administrar o próprio acesso.

| HTTP | Situação |
| --- | --- |
| 401 | Sessão ausente ou inválida |
| 404 | Autoridade, senha, tenant, empresa ou vínculo recusados, sem distinguir a causa |
| 409 | Revisão de concessão, vínculo ou empresa desatualizada |
| 413 / 415 / 422 | Corpo acima de 4096 bytes, formato não JSON ou entrada inválida, sem refletir dados |
| 429 | Limite excedido, com `Retry-After` |
| 503 / 500 | Infraestrutura/capacidade/configuração indisponível ou erro inesperado, sem detalhes internos |

Escritas compartilham os contadores de gestão de acesso: 5 admissões por ator/15
minutos, 30 por origem/minuto e 300 gerais/minuto. A senha usa concorrência limitada
por `AUTH_HASH_CONCURRENCY`, inclusive no cancelamento. Redis indisponível impede
escrita; logout permanece disponível. Sucesso registra atividade; recusas não renovam
sessão. Respostas usam `no-store`, e HTTPS é exigido em staging/production.

`company_permission_grants` tem FKs compostas para empresa e vínculo do mesmo tenant,
chave restrita, revisão positiva e status inicial inativo. A auditoria de concessão
registra ator, escopo, status e revisões, sem nomes, e-mails, CNPJ, senha ou token nos
snapshots. Limpezas de concessões são registradas nas auditorias de status do vínculo
ou da empresa, com quantidade processada e atualização do responsável no registro.
Falha da auditoria reverte toda a escrita, inclusive as revogações automáticas.

A migration `e96b2130ad74`, após `d85fa1049ce3`, cria apenas as tabelas de concessões
e histórico, sem semear acesso. Downgrade é bloqueado quando existem concessões ou
histórico; não apaga registros para forçar retorno à versão anterior.

Permanecem pendentes: interface de seleção/gestão, permissões dos módulos futuros
com escopo de empresa e demais controles operacionais de produção. Esta entrega
não implementa financeiro/fiscal nem acesso a dados de empresas não autorizadas.

## Validação da entrega

Suíte completa: **363 testes aprovados**, incluindo 31 novos (27 de integração,
3 de contratos e 1 de migrations). Cobrem ausência de privilégios implícitos,
escopo por empresa/vínculo, proteção do tenant na própria expressão de visibilidade,
filtro anterior à paginação, ausência de acesso a empresas futuras, ciclo de vida,
revisões, revogação concorrente, troca de Master, falhas de auditoria, rate limit,
cancelamento e constraints contra referências a outro tenant.

Migration aplicada ao PostgreSQL local em `e96b2130ad74 (head)`, porta 5433, com
schema alinhado e dados/flags/status/revisões/contagens anteriores preservados.
Nenhuma concessão real ou histórico de concessão criado; nenhum banco temporário
restante. Health local 200, GET/PUT de acesso por empresa no OpenAPI e recusa 401
sem sessão com `no-store`. Testes de sucesso usaram infraestrutura isolada, sem
senhas, tokens ou cadastros reais do desenvolvedor.
