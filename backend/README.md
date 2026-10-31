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
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-proxy-headers --no-access-log
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

As migrations foram aplicadas ao banco local, na revisão `b92f8d06e4a1 (head)`.
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
Master sem remover o proprietário atual. Conversão das flags antigas segue pendente;
desativação explícita remove a leitura antiga daquele vínculo como parte da revogação.
A migration de convites foi aplicada à porta 5433 após os testes, preservando as
contagens das tabelas anteriores. Alembic check confirmou alinhamento; não foram
criadas contas, organizações ou convites reais nesta validação.

## Testes

Última validação completa: 274 testes aprovados. A etapa de vínculos adicionou 26
testes, cobrindo proteção do Master, isolamento, revogação, reativação mínima,
concorrência e auditoria. Migration aplicada à porta 5433, com flags/status e contagens
anteriores preservados, schema alinhado e nenhuma alteração real de vínculo criada.
A API local foi reiniciada e validada com health 200, GET/PUT de status no OpenAPI e
recusa 401 sem sessão. O sucesso foi validado em infraestrutura isolada.

Testes sem infraestrutura externa:

```powershell
uv run python -m unittest discover -s tests -v
```

Suíte completa, com PostgreSQL e Redis locais ativos:

```powershell
$env:SD_RUN_DATABASE_TESTS = '1'
$env:SD_RUN_REDIS_TESTS = '1'
try {
    uv run python -m unittest discover -s tests -v
} finally {
    Remove-Item Env:SD_RUN_DATABASE_TESTS
    Remove-Item Env:SD_RUN_REDIS_TESTS
}
```

PostgreSQL: banco temporário `sd_repository_test_<uuid>`, com migrations e remoção
ao final. Redis: banco lógico 15 e namespace exclusivo por cenário, sem flush global.
Uma interrupção forçada pode exigir limpeza posterior. Não executar em produção.

## Proteção dos dados e documentação

Não versionar `.env`, credenciais ou dados reais. Manter `APP_DEBUG=false` e
`DATABASE_ECHO=false` ao lidar com informações sensíveis. Não registrar URL de banco,
senhas ou tokens; os parâmetros SQL da conexão oficial ficam ocultos nos logs.

- [Autenticação, segurança e configuração](../docs/autenticacao.md)
- [Contrato e permissões de Organization](../docs/api-organizations.md)
- [Planejamento do produto](../docs/planejamento.md)
