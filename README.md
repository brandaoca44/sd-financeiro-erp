# SD Financeiro ERP

Sistema de gestão empresarial brasileiro em desenvolvimento, projetado para
integrar processos administrativos, financeiros, comerciais, operacionais e fiscais
em uma base modular e extensível.

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
| PostgreSQL e Redis | Infraestrutura local via Docker Compose; Redis sem uso de negócio |
| Health check | Verificação real de conexão com PostgreSQL |
| Organizations e Companies | Models ORM, relacionamento, UUIDs, status e timestamps com fuso horário |
| Alembic | Migration inicial `ed92b41e1e71` e execução assíncrona |
| Contratos de Organization | Schemas de criação e resposta com Pydantic |
| Persistência de Organization | Repository com criação por `flush` e busca por UUID |
| Aplicação de Organization | Service com criação transacional e consulta |
| Testes | 24 testes validados com `unittest`, incluindo integração com PostgreSQL |

Endpoints de Organization, autenticação, autorização, isolamento de acesso entre
tenants, módulos empresariais e painel executivo ainda não estão implementados.
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
| SQLAlchemy 2 Async | ORM e acesso assíncrono |
| Psycopg 3 | Driver PostgreSQL |
| PostgreSQL 18 | Banco relacional |
| Alembic | Versionamento do schema |
| Redis 8 | Infraestrutura disponível para uso futuro |
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
uv run fastapi dev
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

Os nove testes de integração de repository e service são ignorados por padrão.
Para executar a suíte completa, com PostgreSQL local ativo na porta 5433:

```powershell
$env:SD_RUN_DATABASE_TESTS = '1'
try {
    uv run python -m unittest discover -s tests -v
} finally {
    Remove-Item Env:SD_RUN_DATABASE_TESTS
}
```

A integração cria um banco exclusivo `sd_repository_test_<uuid>` no servidor local,
aplica as migrations e o remove ao concluir. O usuário local precisa de permissão
para criar bancos. Os testes não utilizam o banco de negócio do ERP. Uma interrupção
forçada pode deixar o banco temporário para limpeza posterior. Execute apenas em
ambiente de desenvolvimento.

## Segurança

- Credenciais, arquivos `.env`, dumps e dados reais não devem ser versionados.
- Não registre a URL de conexão: ela contém a senha do banco.
- UUIDs não concedem acesso; autorização deverá ser aplicada no servidor.
- Isolamento entre tenants, permissões por empresa e auditoria são requisitos
  para as entregas futuras, inclusive gráficos, exportações e recomendações.
- TLS, proteção dos dados armazenados, gestão de chaves e procedimentos de
  backup e recuperação deverão ser definidos e validados antes da produção.

## Desenvolvimento e documentação

O projeto evolui em pequenos ciclos de implementação, validação, revisão e aprovação.
A próxima entrega prevista é a interface HTTP de Organization, após revisão do service.

- [Documentação do backend](backend/README.md)
- [Planejamento do produto e evolução funcional](docs/planejamento.md)

## Licenciamento

O projeto tem intenção de distribuição comercial proprietária e não inclui uma
licença open source. Os termos de licenciamento serão definidos pelo proprietário.
