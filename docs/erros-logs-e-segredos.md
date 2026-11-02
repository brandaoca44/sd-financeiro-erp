# Erros, logs e segredos por ambiente

## Respostas HTTP

A proteção global envolve todas as rotas HTTP, inclusive health, caminhos
inexistentes e futuros módulos. Cada requisição recebe um `X-Request-ID` aleatório,
gerado pelo servidor e devolvido na resposta. O valor enviado pelo cliente é
ignorado. Esse identificador permite localizar um atendimento sem registrar
identidade, parâmetros ou conteúdo da requisição.

Erros inesperados retornam JSON mínimo com status 500. Falhas SQL não tratadas
retornam 503. Os contratos existentes de autenticação, autorização, conflito,
validação e rate limit permanecem, incluindo `WWW-Authenticate` e `Retry-After`.
Erros de validação continuam sem refletir os dados enviados. Todas as respostas
HTTP recebem `Cache-Control: no-store` e `Pragma: no-cache`.

Se uma resposta em streaming já enviou seus headers, não é possível trocar seu
status por 500. A interrupção é registrada e a exceção original é substituída por
uma mensagem fixa. Um 200 interrompido não deve ser interpretado como transferência
completa. Não há novos endpoints de streaming nesta entrega.

## Logs operacionais

Os registros da API são JSON, com lista fechada de campos:

| Campo | Conteúdo |
| --- | --- |
| `event` | `http_request` |
| `level` | Nível conhecido do logging |
| `request_id` | Identificador gerado pelo servidor |
| `method` | Método HTTP conhecido ou `OTHER` |
| `status` | Status HTTP |
| `outcome` | Concluído, erro interno, indisponível ou interrompido |
| `duration_ms` | Duração limitada em milissegundos |

Não são registrados caminho, query string, IP, headers, cookies, corpo, e-mail,
CNPJ, UUID de empresa/usuário, senha, token, parâmetros SQL ou mensagem/traceback
de exceções. Os campos extras passam por validação; não há serialização genérica
da requisição. Erros tratados pelas rotas aparecem pelo status HTTP; `outcome`
indica o resultado do processamento, não uma autorização concedida.

Isso é observabilidade operacional, não auditoria de negócio. Os históricos
transacionais de alterações de acesso continuam nas tabelas próprias.

## Inicialização recomendada

A partir de `backend/`:

```powershell
uv run python -m ops.serve --reload
```

Sem `--reload`, o mesmo comando inicia uma instância local. O launcher configura
logs seguros para o servidor, desliga access logs e proxy headers, mantém bind em
`127.0.0.1:8000` e seleciona o loop compatível com Psycopg no Windows. Reload é
recusado em staging/produção. Não configura proxy reverso, TLS ou implantação.

Mensagens livres dos loggers de runtime também são omitidas: aparece apenas
`runtime_message` e o nível. Isso reduz os detalhes disponíveis para diagnóstico;
investigações devem ser reproduzidas com dados sintéticos. Não ativar SQL echo
ou logging de corpos para investigar incidentes com dados reais.

Executar Uvicorn por outro comando pode reintroduzir seu formato padrão de logs.
A configuração de proxy, hospedagem e agregação de logs também precisa impedir
captura de URLs sensíveis, corpos e credenciais; o aplicativo não controla esses
sistemas externos. Não adicionar handlers que imprimam mensagens livres.

## Configuração e segredos

Em desenvolvimento/testes, `backend/.env` continua permitido e as variáveis do
processo têm precedência. SQL echo é recusado em todos os ambientes e credencial
de banco vazia não é aceita. Nenhum segredo local foi trocado nesta entrega.

Em staging/produção, a API e o bootstrap administrativo usam o carregador comum:

- `APP_ENVIRONMENT` precisa ser definido externamente. O carregador não usa `.env`
  nesses ambientes; segredos devem ser injetados pelo mecanismo de implantação.
- `APP_DEBUG=false` e `DATABASE_ECHO=false` são obrigatórios.
- `DATABASE_PASSWORD`, `REDIS_PASSWORD` e `AUTH_RATE_LIMIT_KEY` são obrigatórios,
  distintos, com pelo menos 32 bytes UTF-8. Valores uniformes e alguns placeholders
  conhecidos são recusados. Essas verificações não provam aleatoriedade; gerar os
  segredos com fonte criptograficamente segura e guardá-los em gestor de segredos.
- Banco e Redis precisam estar configurados com as mesmas credenciais injetadas.
  O Compose atual é local e não se torna uma infraestrutura de produção por mudar
  somente `APP_ENVIRONMENT`.
- Não imprimir `Settings`, URLs de conexão ou exceções para conferir valores.
  O launcher informa falha de configuração sem detalhar entradas sensíveis.

O mínimo da senha de login continua em oito caracteres. As exigências acima são
para segredos de infraestrutura; a senha do backup segue sua política independente.
Nenhuma migration é necessária para este incremento.

Ainda pendentes: integração com gestor de segredos da implantação, rotação
coordenada, configuração de transporte seguro para banco/Redis, coleta e retenção
restritas dos logs, monitoramento e procedimento de recuperação operacional.
Alterar a chave de rate limit muda a identificação de seus contadores e requer
planejamento; esta entrega não faz rotação automática.

## Validação

Suíte completa aprovada: **399 testes**, com PostgreSQL, Redis e Docker ativos.
Foram acrescentados 19 testes operacionais. O launcher também foi iniciado no
Windows e a API local retornou health 200 e organização sem sessão 401, com
`X-Request-ID` e `no-store`. Nenhum segredo local foi alterado.

Os testes novos cobrem exceções privadas com debug ligado, validação, rotas
inexistentes, limite de corpo, streaming interrompido, IDs concorrentes, omissão
de dados dos logs e regras de configuração. Os testes completos de HTTP, acesso,
PostgreSQL, Redis e recuperação continuam usando infraestrutura isolada.
