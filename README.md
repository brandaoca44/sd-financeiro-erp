# SD Financeiro ERP

Sistema de gestão empresarial brasileiro em desenvolvimento, projetado para
integrar processos administrativos, financeiros, comerciais, operacionais e fiscais
em uma base modular e extensível.

O produto atende exclusivamente empresas. `Company` utiliza CNPJ; CPF não é um
identificador alternativo. As contas de usuário representam as pessoas autorizadas
a operar o sistema em nome das empresas.

O produto tem como direção atuar também como parceiro virtual da empresa:
transformar dados operacionais em indicadores e oportunidades para melhorar
receita, margem, caixa e eficiência. O escopo é generalista, com possibilidade de
especializações futuras por segmento.

## Estado atual

O projeto está na construção da fundação técnica e do domínio organizacional.
Ainda não está pronto para produção ou uso multi-tenant com dados reais.

| Implementado | Situação |
| --- | --- |
| Backend FastAPI | Configuração por ambiente e ciclo de vida das conexões |
| PostgreSQL e Redis | Infraestrutura local via Docker Compose; Redis utilizado pelo limitador interno de login |
| Health check | Verificação real de conexão com PostgreSQL |
| Organizations e Companies | Models ORM, relacionamento, UUIDs, status e timestamps com fuso horário |
| Alembic | Migration inicial `ed92b41e1e71` e execução assíncrona |
| Contratos de Organization | Schemas de criação e resposta com Pydantic |
| Persistência de Organization | Repository com criação por `flush` e busca por UUID |
| Aplicação de Organization | Service com criação transacional e consulta |
| Base de identidade | Models de usuários e vínculos, com permissões negadas por padrão; migration validada em banco temporário |
| Política de acesso | Verificação de sessão, usuário ativo, vínculo e concessões nas rotas de Organization |
| Proteção de senhas | Hash e verificação com Argon2id; credenciais separadas |
| Autenticação HTTP | Login e logout com token opaco, inatividade e revogação |
| Rate limit | Limites por conta, origem e geral no login, com Redis e contagem atômica |
| Bootstrap administrativo | Comando interativo para inicialização única do primeiro operador, sem cadastro público |
| Hierarquia organizacional | Proprietário, perfis e atribuições por tenant; rotas de designação/transferência com reautenticação limitada e histórico atômico |
| Onboarding e convites | Provisionamento com convite ao primeiro Master; aceite de conta nova ou existente, convites mínimos a colaboradores e revogação |
| Perfis e permissões | Catálogo fechado, gestão de perfis, atribuições por tenant e delegação com teto e origem auditados |
| Ciclo dos vínculos | Ativação/desativação pelo Master, com limpeza de concessões e proteção do proprietário atual |
| Revisão de acessos | Origem da leitura, conversão explícita da flag antiga em perfil restrito e revogação auditada |
| Empresas | Cadastro jurídico por tenant, CNPJ numérico/alfanumérico, nomes e status interno; administração inicial pelo Master |
| Acesso por empresa | Leitura explícita do cadastro para colaboradores, filtragem antes da paginação e revogação no ciclo de vida |
| Backup local | Arquivo cifrado e ensaio de restauração em PostgreSQL descartável, sem substituir a base existente |
| Erros e logs | Proteção global, identificador de requisição, logs por campos permitidos e política de segredos por ambiente |
| Contas a pagar | API protegida de lançamento, consulta, edição e cancelamento; baixas e estornos pendentes |
| Permissões financeiras | Quatro concessões independentes por empresa, administração pelo Master e revogação no ciclo de vida |
| Testes | 452 testes validados com `unittest`, incluindo integração HTTP, PostgreSQL, Redis e recuperação de backup |

Organization possui criação e consulta autenticadas com isolamento de acesso testado
nessas rotas. Módulos empresariais, permissões operacionais por módulo e painel executivo ainda
não estão implementados. O login exige configuração segura antes do uso.
O frontend ainda não possui uma aplicação implementada.

## Visão do produto

O desenvolvimento prevê módulos de financeiro, comercial, compras, estoque,
fiscal e relatórios, introduzidos conforme os fluxos escolhidos para o MVP.

Uma área executiva, com nome a definir, deverá reunir indicadores das áreas
disponíveis e oportunidades fundamentadas nos dados da empresa:

- Receita e rentabilidade: oportunidades comerciais, margens, descontos e custos.
- Caixa: recebimentos, prazos e recursos comprometidos na operação.
- Gastos e desperdícios: possíveis duplicidades, encargos evitáveis, perdas e
  contratos que mereçam revisão.
- Oportunidades tributárias: análise de possíveis créditos, pagamentos em excesso
  e incentivos aplicáveis, incluindo o estudo da Lei do Bem.
- Inovação: identificação de gargalos e acompanhamento de projetos tecnológicos.

Essas capacidades são planejadas. Cada recomendação deverá apresentar evidências,
premissas e impacto estimado, distinguindo resultados realizados de previsões.
Decisões operacionais e tributárias dependerão de revisão pelos responsáveis.
Benefícios projetados não serão tratados como saldo disponível ou resultado garantido.

## Arquitetura

O backend segue um **monólito modular**, com responsabilidades introduzidas
gradualmente:

- `models`: mapeamento ORM e integridade estrutural dos dados.
- `schemas`: contratos de entrada e saída.
- `repository`: acesso ao banco, sem confirmação de transações.
- `service`: coordenação dos casos de uso e transações.
- `api`: interface HTTP, conforme cada funcionalidade for disponibilizada.

`Organization` representa o cliente e a fronteira lógica de propriedade dos dados.
`Company` representa uma entidade jurídica pertencente a uma organização.
Essa relação estabelece ownership, mas não implementa autorização ou isolamento
seguro por si só. A estratégia física de tenancy ainda será definida.

Integrações externas serão adicionadas por contratos e adapters quando houver
necessidade concreta. Especializações por segmento não serão antecipadas no core.

## Stack

| Tecnologia | Uso |
| --- | --- |
| Python 3.14 | Runtime do backend |
| FastAPI | API HTTP |
| Pydantic e Pydantic Settings | Contratos e configurações |
| pwdlib com Argon2 | Hash e verificação de senhas |
| SQLAlchemy 2 Async | ORM e acesso assíncrono |
| Psycopg 3 | Driver PostgreSQL |
| PostgreSQL 18 | Banco relacional |
| Alembic | Versionamento do schema |
| Redis 8 e redis-py | Contadores compartilhados do rate limit interno |
| uv | Ambiente virtual e dependências com lockfile |
| Docker Compose | Serviços locais |
| unittest | Testes automatizados |

## Estrutura do repositório

```text
sd-financeiro-erp/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── core/
│   │   ├── database/
│   │   ├── modules/organizations/
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   ├── pyproject.toml
│   └── uv.lock
├── docs/
│   └── planejamento.md
├── .env.example
└── docker-compose.yml
```

## Execução local

Pré-requisitos: Python 3.14, uv e Docker com Docker Compose. No Windows, mantenha
o Docker Desktop em execução. Os comandos abaixo usam PowerShell a partir da raiz.

### 1. Configurar o ambiente

Crie os arquivos locais a partir dos exemplos, somente se ainda não existirem:

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
if (-not (Test-Path -LiteralPath 'backend/.env')) {
    Copy-Item -LiteralPath 'backend/.env.example' -Destination 'backend/.env'
}
```

Edite ambos os arquivos e substitua as senhas ilustrativas por credenciais locais
fortes. Nome do banco, usuário e senha devem coincidir entre a configuração do
container e a do backend. Mantenha `APP_DEBUG=false` e `DATABASE_ECHO=false`.

| Serviço | Endereço local padrão | Porta interna |
| --- | --- | --- |
| PostgreSQL | `127.0.0.1:5433` | `5432` |
| Redis | `127.0.0.1:6379` | `6379` |

Confira se as portas estão disponíveis. Se alterar `POSTGRES_PORT` na raiz,
ajuste também `DATABASE_PORT` em `backend/.env`. O Compose publica os serviços
somente em `127.0.0.1`.

### 2. Iniciar a infraestrutura

```powershell
docker compose up -d --wait
docker compose ps
```

### 3. Preparar e executar o backend

```powershell
Set-Location backend
uv sync --locked --python 3.14
uv run alembic upgrade head
uv run python -m ops.serve --reload
```

Confira o banco de destino antes de aplicar migrations. A aplicação lê
`backend/.env`; variáveis de ambiente do processo têm precedência. A URL de conexão
é montada pelo código, sem necessidade de uma variável `DATABASE_URL`.

Com o servidor no endereço padrão, a documentação interativa fica disponível em
`http://127.0.0.1:8000/docs`. O endpoint `GET /api/v1/health` retorna HTTP 200 quando
o banco está acessível e HTTP 503 quando a conexão está indisponível.

## Testes

Dentro de `backend`, execute os testes sem integração:

```powershell
uv run python -m unittest discover -s tests -v
```

Os 73 testes PostgreSQL, oito Redis e 16 HTTP com ambas as infraestruturas são
ignorados por padrão.
Para executar a suíte completa, com PostgreSQL local na porta 5433 e Redis na 6379:

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

A integração cria um banco exclusivo `sd_repository_test_<uuid>` no servidor local,
aplica as migrations e o remove ao concluir. O usuário local precisa de permissão
para criar bancos. Os testes não utilizam o banco de negócio do ERP. Uma interrupção
forçada pode deixar o banco temporário para limpeza posterior. Execute apenas em
ambiente de desenvolvimento.

Os testes Redis usam o banco lógico 15 e um namespace aleatório por teste. A limpeza
remove somente as chaves próprias, sem `FLUSHDB` ou `FLUSHALL`. Senhas, e-mails e IPs
reais não são usados nos cenários.

## Segurança

- Credenciais, arquivos `.env`, dumps e dados reais não devem ser versionados.
- Não registre a URL de conexão: ela contém a senha do banco.
- UUIDs não concedem acesso; autorização deverá ser aplicada no servidor.
- Isolamento entre tenants, permissões por empresa e auditoria são requisitos
  para as entregas futuras, inclusive gráficos, exportações e recomendações.
- TLS, proteção dos dados armazenados, gestão de chaves e procedimentos de
  backup e recuperação deverão ser definidos e validados antes da produção.

## Primeiro operador da plataforma

Após revisar e aplicar as migrations no banco de destino, execute dentro de
`backend`, em um terminal interativo:

```powershell
uv run python -m app.modules.identity.bootstrap_cli
```

O comando exibe o destino para conferência, exige confirmação e solicita nome,
e-mail, senha e confirmação da senha. A senha é digitada sem exibição e não é aceita
por argumento. Não use senha padrão ou envie credenciais pelo chat.

A inicialização cria usuário ativo, hash Argon2id e marcador único na mesma
transação. Execuções repetidas ou concorrentes são recusadas. Contas existentes
não são promovidas automaticamente. O operador recebe apenas a permissão de
provisionar organizações, sem vínculos de leitura ou sessão de login.

Os testes criam contas somente em bancos temporários. O primeiro operador local
foi criado pelo desenvolvedor e o login HTTP foi validado. Recuperação de acesso
continua pendente; o bootstrap não cria operadores adicionais nem recupera contas.

## Desenvolvimento e documentação

O projeto evolui em pequenos ciclos de implementação, validação, revisão e aprovação.
A interface HTTP de Organization está implementada com autenticação e autorização.
As migrations foram aplicadas ao banco local em `a18d5320cf97 (head)` e o segredo
de autenticação foi configurado sem exibição. A API local teve health e recusas
de acesso validados. O primeiro operador foi criado e o desenvolvedor confirmou
login, logout e recusa de sessão revogada via Swagger em 31/10/2026.
As rotas de propriedade estão disponíveis, sem atribuição automática de Master.
O histórico de propriedade é transacional; auditoria das demais operações e outros
controles de produção seguem pendentes.

- [Documentação do backend](backend/README.md)
- [Planejamento do produto e evolução funcional](docs/planejamento.md)
- [Contrato HTTP e política de acesso de Organization](docs/api-organizations.md)
- [Autenticação e segurança](docs/autenticacao.md)
- [Onboarding e convites](docs/onboarding-e-convites.md)
- [Catálogo de permissões e gestão de perfis](docs/perfis-e-permissoes.md)
- [Ativação e desativação de vínculos](docs/ciclo-de-vida-de-vinculos.md)
- [Revisão e conversão das concessões antigas](docs/revisao-de-acessos.md)
- [Cadastro jurídico de empresas](docs/api-companies.md)
- [Permissões específicas por empresa](docs/acesso-por-empresa.md)
- [Backup local e ensaio de recuperação](docs/backup-e-recuperacao.md)
- [Erros, logs e segredos por ambiente](docs/erros-logs-e-segredos.md)
- [Prontidão operacional e primeiro fluxo do MVP](docs/prontidao-e-primeiro-mvp.md)
- [Fundação de contas a pagar](docs/persistencia-contas-a-pagar.md)
- [Permissões financeiras por empresa](docs/permissoes-financeiras.md)
- [API de títulos de contas a pagar](docs/api-contas-a-pagar.md)
- [Hierarquia, perfis e permissões por área e segmento](docs/hierarquia-e-permissoes.md)

## Licenciamento

O projeto tem intenção de distribuição comercial proprietária e não inclui uma
licença open source. Os termos de licenciamento serão definidos pelo proprietário.
