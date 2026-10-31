# SD Financeiro ERP — Backend

API em Python 3.14, FastAPI, SQLAlchemy Async e Psycopg 3. A arquitetura
é um monólito modular; o domínio inicial contém organizações e empresas.

## Ambiente local

Na raiz do repositório, crie `.env` a partir de `.env.example`. Em `backend`,
crie outro `.env` a partir de `backend/.env.example`. Configure senhas locais
fortes e mantenha as credenciais do PostgreSQL consistentes nos dois arquivos.
Os arquivos de exemplo contêm apenas valores ilustrativos.

Execute na raiz:

```console
docker compose up -d
```

Execute os comandos do backend dentro de `backend`:

```console
uv sync --locked
uv run alembic upgrade head
uv run fastapi dev
```

Antes de executar migrations, confira o ambiente e o banco de destino.
O PostgreSQL local usa `127.0.0.1:5433`, mapeado para a porta interna `5432`.
Verifique a disponibilidade das portas antes de iniciar os serviços.
As portas publicadas pelo Compose ficam restritas a `127.0.0.1`, para uso local.

A aplicação lê especificamente `backend/.env`, independentemente do diretório
de execução. Variáveis de ambiente do processo têm precedência sobre esse arquivo.

## Segurança e estado atual

- Nunca versione `.env`, credenciais ou dumps com dados reais.
- Mantenha `APP_DEBUG=false` e `DATABASE_ECHO=false` em ambientes com dados sensíveis.
- Não registre a propriedade `database_url`: ela contém a senha de conexão.
- O endpoint `GET /api/v1/health` verifica o PostgreSQL e retorna 503 quando
  indisponível, sem incluir detalhes da exceção na resposta.
- As tentativas de conexão com PostgreSQL possuem timeout de cinco segundos.
- A unicidade de CNPJ é global na modelagem atual.
- Autenticação, autorização e isolamento de acesso entre tenants ainda não estão
  implementados. A base atual não está pronta para uso multi-tenant em produção.

Os schemas `OrganizationCreate` e `OrganizationResponse` estão implementados em
`app/modules/organizations/schemas.py`, com validação e testes sem acesso ao banco.
A criação aceita somente nome (1 a 150 caracteres após remover espaços nas
extremidades) e rejeita campos extras. A resposta utiliza atributos ORM e inclui
UUID, nome, status e timestamps com fuso horário, sem relacionamentos.
O `OrganizationRepository` recebe uma `AsyncSession`, cria organizações com
`create(name=...)` e busca por UUID com `get_by_id(...)`. A criação executa `flush`
para obter os campos gerados, sem `commit` ou `rollback`: a transação pertence ao
chamador. A busca retorna `None` quando o registro não existe. Validação de entrada
e autorização são responsabilidades das camadas de aplicação; conhecer um UUID
não concede acesso a uma organização.

O `OrganizationService` coordena criação e consulta. Recebe `OrganizationCreate`,
retorna `OrganizationResponse` e controla a transação da criação: confirma apenas
após montar a resposta e reverte em caso de falha. Sua operação de criação exige
sessão sem transação anterior. A consulta retorna `None` quando ausente e não
implementa autorização; o chamador deverá validar o contexto antes de utilizá-la.
Não existem endpoints de Organization nesta etapa.

O service está implementado e aguarda revisão e aprovação antes das rotas HTTP.

O [planejamento do produto](../docs/planejamento.md) registra a sequência de
entregas e as capacidades futuras de gestão da inovação, oportunidades tributárias
e identificação de desperdícios e gastos evitáveis em todos os módulos aplicáveis,
incluindo o estudo de incentivos como a Lei do Bem.

## Validação das correções

```console
uv run python -m unittest discover -s tests -v
```

Por padrão, os testes de integração do repository e service são ignorados. Para executá-los
no PowerShell, com PostgreSQL do ERP ativo em `127.0.0.1:5433`:

```powershell
$env:SD_RUN_DATABASE_TESTS = '1'
try {
    uv run python -m unittest discover -s tests -v
} finally {
    Remove-Item Env:SD_RUN_DATABASE_TESTS
}
```

Essa execução cria um banco com nome aleatório `sd_repository_test_<uuid>` no mesmo
servidor PostgreSQL do ERP, aplica migrations e remove somente esse banco ao final.
As credenciais são lidas das configurações locais e precisam permitir criação de
bancos nesse ambiente de desenvolvimento. As operações de teste não usam o banco
de negócio do ERP nem a porta 5432 do PostgreSQL do Moment. Não execute em produção.
Uma interrupção forçada pode deixar o banco temporário para limpeza posterior.
