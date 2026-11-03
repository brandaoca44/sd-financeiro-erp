# Backend do SD Financeiro ERP

API em Python 3.14, FastAPI, SQLAlchemy Async e Psycopg 3. A arquitetura é um
monólito modular, com separação entre contratos, persistência, aplicação e HTTP.

## Execução local

Na raiz, configure `.env` a partir de `.env.example`. Em `backend`, configure
`backend/.env` a partir de seu exemplo. Nome do banco, usuário e senha devem
coincidir nos dois arquivos. Não sobrescreva configurações já existentes.

Na raiz:

```powershell
docker compose up -d --wait
```

Dentro de `backend`, após conferir o banco de destino:

```powershell
uv sync --locked --python 3.14
uv run alembic upgrade head
uv run python -m ops.serve --reload
```

PostgreSQL utiliza `127.0.0.1:5433`; Redis, `127.0.0.1:6379`. As portas publicadas
pelo Compose ficam restritas ao computador local. O backend lê especificamente
`backend/.env`; variáveis de ambiente do processo têm precedência.

## Módulos atuais

| Componente | Responsabilidade |
| --- | --- |
| `organizations/models.py` | Organizações, empresas e integridade estrutural |
| `organizations/schemas.py` | Contratos de criação e resposta |
| `organizations/repository.py` | Persistência com flush, sem commit |
| `organizations/service.py` | Casos de uso e transação da criação |
| `organizations/router.py` | Rotas protegidas por sessão e permissões |
| `organizations/cnpj.py` | Normalização ASCII e dígitos verificadores do CNPJ numérico/alfanumérico |
| `organizations/company_schemas.py` | Contratos jurídicos sem CPF ou alteração de tenant/CNPJ na edição |
| `organizations/company_repository.py` | Persistência sempre limitada ao tenant, sem commit |
| `organizations/company_service.py` | Cadastro/edição com reautenticação, revisão e auditoria atômica |
| `organizations/company_router.py` | Cadastro pelo Master e leitura no escopo autorizado da empresa |
| `identity/access_security.py` | Autorização transacional e reautenticação compartilhadas por perfis e empresas |
| `identity/authorization.py` | Usuário ativo e concessões por tenant |
| `identity/access_models.py` | Proprietário, perfis e atribuições com FKs entre registros do mesmo tenant |
| `identity/ownership.py` | Designação e transferência com senha, sessão, locks e histórico atômico |
| `api/v1/ownership.py` | Rotas de propriedade com rate limit e concorrência compartilhada com login |
| `identity/invitation_models.py` | Convites de uso único, concessão e trilha de aceite/revogação |
| `identity/invitations.py` | Onboarding, confirmação de conta e vínculo transacional |
| `api/v1/invitations.py` | Emissão, aceite e revogação com limites próprios |
| `identity/permissions.py` | Catálogo fechado das ações existentes e fontes de concessão |
| `identity/permission_models.py` | Concessões por perfil, delegação com teto e snapshots de auditoria |
| `identity/roles.py` | Gestão transacional de perfis, atribuições e delegações |
| `api/v1/roles.py` | Rotas administrativas com senha, rate limit e revisões |
| `identity/memberships.py` | Ciclo do vínculo, limpeza de concessões e proteção do Master |
| `api/v1/memberships.py` | Consulta e alteração mínima do status do vínculo |
| `identity/legacy_access.py` | Revisão de origem, conversão restrita e revogação da flag de leitura antiga |
| `api/v1/legacy_access.py` | Rotas de revisão/conversão somente para Master |
| `identity/company_access_models.py` | Concessões diretas por empresa/vínculo e auditoria |
| `identity/company_authorization.py` | Política de visibilidade aplicada na consulta e antes da paginação |
| `identity/company_access.py` | Concessão/revogação pelo Master com revisões de empresa, vínculo e concessão |
| `api/v1/company_access.py` | Consulta e gestão de leitura por empresa |
| `identity/passwords.py` | Argon2id e atualização dos parâmetros do hash |
| `identity/sessions.py` | Tokens opacos, inatividade e revogação |
| `identity/rate_limit.py` | Limites compartilhados no Redis |
| `identity/bootstrap.py` | Inicialização única do primeiro operador |
| `identity/authentication.py` | Rate limit, senha e emissão da sessão |
| `api/v1/auth.py` | Login, logout e dependências de autenticação |
| `core/http_security.py` | Limites de entrada e erros seguros nas rotas sensíveis |

## Autenticação e acesso

Login usa JSON com e-mail e senha. Rotas protegidas usam `Authorization: Bearer`.
A sessão expira por inatividade, sem prazo absoluto enquanto houver uso válido.
Logout revoga o token no servidor e não depende dos contadores de login.

Configure `AUTH_RATE_LIMIT_KEY` com segredo aleatório de pelo menos 32 bytes, igual
entre workers. Sem essa chave, login e acesso protegido permanecem indisponíveis.
As demais variáveis estão no [exemplo de ambiente](.env.example).

O primeiro operador é criado somente por comando interativo:

```powershell
uv run python -m app.modules.identity.bootstrap_cli
```

Ele confirma o destino e solicita nome, e-mail e senha oculta. Cria usuário ativo,
hash e marcador único na mesma transação, sem acesso automático a tenants.
Não cria conta padrão, não promove contas existentes e não emite sessão.

As migrations foram aplicadas ao banco local, na revisão `b29e6431da08 (head)`.
O segredo do rate limit foi gerado no `.env`, sem exibição. A API local foi validada
com health 200 e recusa de acessos sem sessão. O operador foi criado e o desenvolvedor
confirmou login 200, logout 204 e recusa do token revogado 401 via Swagger em
31/10/2026. A base ainda não está pronta para produção.

As migrations `d2a6f09b84c1` (hierarquia) e `e7b1c90a42d3` (histórico de propriedade)
foram validadas em bancos temporários e depois aplicadas ao PostgreSQL local na porta
5433. O schema está alinhado aos models e as contagens das tabelas anteriores foram
preservadas. Nenhum proprietário foi atribuído. Perfis e atribuições começam inativos.
As rotas já permitem designação explícita e transferência com confirmação da senha,
sessão válida, limites de reautenticação e histórico atômico. Não há privilégios
automáticos. Onboarding e convites/vínculos mínimos já estão implementados, conforme o
[desenho de acessos e contrato HTTP](../docs/hierarquia-e-permissoes.md).

O [fluxo de onboarding e convites](../docs/onboarding-e-convites.md) cobre conta nova
ou existente, primeiro Master, colaboradores e revogação. Não envia e-mail: o token
é entregue uma única vez ao emissor para entrega privada. Aceite não emite sessão
nem concede perfis automaticamente. O [catálogo e a gestão de perfis](../docs/perfis-e-permissoes.md)
já permitem concessões explícitas e delegação limitada de atribuições. O [ciclo
dos vínculos](../docs/ciclo-de-vida-de-vinculos.md) permite ativação/desativação pelo
Master sem remover o proprietário atual. A [revisão das concessões antigas](../docs/revisao-de-acessos.md)
permite converter a leitura antiga em perfil restrito ou revogar somente essa origem,
com auditoria e revisões. A flag permanece por compatibilidade, sem conversão automática.
O [cadastro de Company](../docs/api-companies.md) já permite criação, consulta e
edição jurídica por Master, com CNPJ validado na API e no banco, unicidade por tenant
e identificação imutável na edição. [Concessões explícitas por empresa](../docs/acesso-por-empresa.md)
já permitem leitura dos cadastros autorizados para colaboradores, sem acesso a
outras empresas ou módulos. Criação, edição e concessão continuam exclusivas do Master.
A migration de convites foi aplicada à porta 5433 após os testes, preservando as
contagens das tabelas anteriores. Alembic check confirmou alinhamento; não foram
criadas contas, organizações ou convites reais nesta validação.

## Testes

Validação da entrega de acesso por empresa: 363 testes aprovados, incluindo 31
testes de autorização, paginação, ciclo de vida, concorrência, auditoria e migrations.
Migration aplicada à porta 5433, com dados/flags/status/revisões/contagens anteriores
preservados e schema alinhado. Nenhuma concessão real foi criada. API local com
health 200, GET/PUT de concessão no OpenAPI e recusa 401 sem sessão. Sucesso com
credenciais foi validado em infraestrutura isolada, sem acesso a dados reais.

Validação da entrega de backup: **380 testes aprovados**, incluindo 17 novos de backup
(15 de formato/segurança e dois de recuperação real em contêiner descartável).
O PostgreSQL local permaneceu saudável e não restaram contêineres de ensaio.

Validação da entrega de erros e logs: **399 testes aprovados**, incluindo 19 novos de erros,
logs e configuração operacional. API local pelo launcher seguro: health 200 e
rota de organização sem sessão 401, ambas com `X-Request-ID` e `no-store`.

Validação da fundação financeira: **413 testes aprovados**, incluindo 14 novos da fundação
financeira. Migration `f07c4219be86` aplicada na porta 5433, contagens anteriores
preservadas, schema alinhado e tabelas financeiras vazias. Sem bancos temporários.

Validação de permissões financeiras: **437 testes aprovados**, incluindo 24 novos de permissões
financeiras. Migration `a18d5320cf97` aplicada à porta 5433, contagens e concessões
anteriores preservadas, schema alinhado, nenhuma concessão financeira real criada.

Validação de títulos: **452 testes aprovados**, incluindo 15 novos de HTTP
financeiro. API local: health 200, leitura/escrita de títulos sem sessão 401.
Sem migration nova; nenhum título, movimento ou histórico financeiro real criado.

Validação de baixas/estornos: **477 testes aprovados**, 25 novos de baixas/estornos.
Migration `b29e6431da08` aplicada à porta 5433, contagens preservadas e schema
alinhado. Zero movimentos/resultados idempotentes reais e bancos temporários.

Validação mais recente: **495 testes aprovados**, 18 novos de resumo financeiro.
Totais exatos e série diária conferidos em infraestrutura isolada. Sem migration
nova; nenhuma escrita financeira real. API local: health 200, resumo no OpenAPI
e recusa 401 sem sessão com `no-store`.

Comando sem infraestrutura externa:

```powershell
uv run python -m unittest discover -s tests -v
```

Suíte completa, com PostgreSQL e Redis locais ativos:

```powershell
$env:SD_RUN_DATABASE_TESTS = '1'
$env:SD_RUN_REDIS_TESTS = '1'
$env:SD_RUN_BACKUP_TESTS = '1'
try {
    uv run python -m unittest discover -s tests -v
} finally {
    Remove-Item Env:SD_RUN_DATABASE_TESTS
    Remove-Item Env:SD_RUN_REDIS_TESTS
    Remove-Item Env:SD_RUN_BACKUP_TESTS
}
```

PostgreSQL: banco temporário `sd_repository_test_<uuid>`, com migrations e remoção
ao final. Redis: banco lógico 15 e namespace exclusivo por cenário, sem flush global.
Uma interrupção forçada pode exigir limpeza posterior. Não executar em produção.
Os testes de backup também usam contêineres descartáveis sem rede ou portas,
removidos ao terminar, e exigem acesso ao Docker.

## Contas a pagar

O módulo `finance` tem contratos, persistência e rotas protegidas de lançamento,
consulta, edição e cancelamento, descritas na [API de títulos](../docs/api-contas-a-pagar.md).
A administração de concessões e a política financeira por
empresa estão implementadas; contrato em
[permissões financeiras](../docs/permissoes-financeiras.md). Regras e limites em
[fundação de contas a pagar](../docs/persistencia-contas-a-pagar.md).

Baixas manuais, estornos, posição individual e consulta de movimentos estão
disponíveis com permissões próprias, saldo exato e idempotência no PostgreSQL.
Contrato em [baixas e estornos](../docs/baixas-e-estornos.md).

O [resumo por empresa/período](../docs/resumo-contas-a-pagar.md) fornece saldos
atuais, vencimentos, atividade do período e série diária para a interface. Exige
leitura financeira; não representa caixa ou fechamento histórico.

## Backup e ensaio de recuperação

`uv run python -m ops.postgres_backup create CAMINHO.sdfbackup` cria um arquivo
cifrado do PostgreSQL local. `verify CAMINHO.sdfbackup` ensaia sua recuperação em
contêiner separado, sem substituir o banco existente. A senha é interativa e não
deve ser compartilhada. Limite inicial: dump comprimido de 128 MiB.
Procedimento, limitações e pendências em
[backup e recuperação](../docs/backup-e-recuperacao.md).

## Proteção dos dados e documentação

Não versionar `.env`, credenciais ou dados reais. Manter `APP_DEBUG=false` e
`DATABASE_ECHO=false` ao lidar com informações sensíveis. Não registrar URL de banco,
senhas ou tokens; os parâmetros SQL da conexão oficial ficam ocultos nos logs.

- [Autenticação, segurança e configuração](../docs/autenticacao.md)
- [Erros, logs e segredos por ambiente](../docs/erros-logs-e-segredos.md)
- [Contrato e permissões de Organization](../docs/api-organizations.md)
- [Planejamento do produto](../docs/planejamento.md)

O ciclo de identidade agora inclui cadastro preparado com CPF cifrado, confirmação, recuperação e MFA TOTP. O envio de e-mail permanece desativado por decisão de produto. Requisitos, limites e variáveis estão em [Ciclo de conta](../docs/ciclo-de-conta.md). Migration atual: `c30f7542eb19`. Validação deste incremento: 515 testes do backend aprovados em infraestrutura isolada.
