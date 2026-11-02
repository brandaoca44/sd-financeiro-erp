# Autenticação e segurança

## O que foi implementado

Login por e-mail e senha, sessões opacas, logout e proteção das rotas de Organization.
O token identifica uma sessão; permissões de usuário e tenant são verificadas no
servidor. Não usamos JWT ou cookies nesta entrega.

## Fluxo de login

`POST /api/v1/auth/login`, com JSON contendo somente `email` e `password`:

1. Limitar o corpo a 4096 bytes e validar a entrada sem refletir valores nos erros.
2. Aplicar os limites por conta, origem da conexão e geral antes do trabalho de hash.
3. Consultar a credencial e verificar Argon2id. Conta inexistente, inativa ou sem
   senha passa por verificação fictícia para reduzir diferenças de tempo.
4. Revalidar usuário ativo e hash sob lock na transação de emissão. Se a senha
   mudou durante a verificação, negar o login; atualizar parâmetros do hash quando necessário.
5. Confirmar a sessão e retornar somente `access_token`, `token_type` e `expires_at`.

O token original é entregue somente nessa resposta. O banco guarda apenas seu
hash SHA-256. A senha usa Argon2id com salt aleatório, em tabela separada. O uso de
SecretStr reduz exposição acidental em representações; não torna seguro imprimir
valores desembrulhados. Os logs SQL da conexão oficial ocultam parâmetros.

| HTTP | Resposta |
| --- | --- |
| 200 | Sessão emitida |
| 401 | `E-mail ou senha inválidos.`, sem distinguir existência ou status da conta |
| 429 | Excesso de tentativas, com `Retry-After` |
| 413 / 415 / 422 | Entrada excessiva, formato incorreto ou dados inválidos |
| 503 | Falta de configuração, limite de processamento ou falha de Redis/PostgreSQL |
| 500 | Erro inesperado sem detalhes internos |

O hash tem concorrência limitada por worker, com espera de até 250 ms por vaga.
A verificação fictícia reduz enumeração por tempo, mas não promete tempos idênticos
em todas as situações. Essas proteções complementam rate limit e TLS.

## Sessão, atividade e logout

Rotas protegidas exigem `Authorization: Bearer <token>`. Tokens em URL, cookies ou
headers de identidade não autenticam o usuário. O token não concede acesso a outro
tenant nem incorpora permissões fornecidas pelo cliente.

O prazo padrão é de 30 minutos de inatividade. Ações autenticadas e autorizadas de
Organization renovam o prazo, sem duração máxima absoluta enquanto houver atividade.
Polling e tarefas automáticas não devem manter sessões vivas. A tela futura deverá
contemplar edição prolongada sem transmitir conteúdo digitado como sinal de atividade.

`POST /api/v1/auth/logout` revoga a sessão apresentada e retorna 204, inclusive em
repetições ou tokens já inválidos. Exige header Bearer, mas não depende do Redis,
da chave de rate limit ou de a sessão ainda estar ativa. Não revoga outras sessões.

Respostas de autenticação e Organization usam `Cache-Control: no-store`. O frontend
deverá manter o token protegido em memória e descartá-lo no logout; não gravar em
URLs, logs ou armazenamento persistente do navegador. TLS é obrigatório na implantação.
O código rejeita HTTP em staging/production. Não há CORS liberado indiscriminadamente.

O [aceite de convite](onboarding-e-convites.md) permite criar conta com nome e senha
ou confirmar a senha de uma conta existente. Não há cadastro irrestrito, troca de
senha por convite ou emissão automática de sessão. Tokens de convite são separados
dos tokens de sessão e não autenticam as rotas de negócio.

## Rate limit

| Dimensão | Valor inicial |
| --- | --- |
| Conta, identificada pelo e-mail | 5 admissões em 15 minutos |
| Origem da conexão | 30 admissões por minuto |
| Geral | 300 admissões por minuto |

Conta tentativas admitidas, com senha correta ou incorreta. Não altera sessões já
conectadas. Redis e Lua fazem a contagem atômica, com TTL; recusas não prolongam o
bloqueio. As chaves usam HMAC para não incluir e-mail ou IP em texto puro.
Redis indisponível impede novos logins, sem impedir logout. Todos os workers devem
compartilhar segredo, namespace e limites. Evitar eviction ou limpeza que reinicie contadores.

Usamos `request.client.host`, sem interpretar Forwarded/X-Forwarded-For na aplicação.
O servidor ASGI também deve ser configurado para não confiar em proxies arbitrários.
Na execução direta, usar `--no-proxy-headers`; atrás de proxy, definir explicitamente
os proxies confiáveis e impedir acesso direto ao backend. Os testes ASGI não substituem
a validação dessa configuração de implantação.

## Configuração local

As variáveis estão documentadas em [backend/.env.example](../backend/.env.example).

- `AUTH_RATE_LIMIT_KEY`: segredo aleatório com pelo menos 32 bytes, igual entre
  workers. Não há valor padrão; sem ele o login e o acesso protegido retornam 503.
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`: conexão dos contadores. Credenciais opcionais:
  `REDIS_USERNAME` e `REDIS_PASSWORD`; não versionar valores reais.
- `AUTH_IDLE_TIMEOUT_SECONDS`: inatividade, padrão 1800.
- `AUTH_HASH_CONCURRENCY`: vagas compartilhadas de login, propriedade, convites e perfis por worker, padrão 2.
- `AUTH_ACCOUNT_*`, `AUTH_ORIGIN_*`, `AUTH_GLOBAL_*`: limites e janelas do login em segundos.

Designação e transferência de proprietário exigem confirmação da senha, com
contadores separados do login, compartilhados entre as duas operações: 5 por ator
em 15 minutos, 30 por origem/minuto e 300 gerais/minuto. O ator é identificado pela
sessão. As operações não revelam dados de usuários e retornam 204 sem corpo quando
concluídas. Consulte o [contrato de propriedade](hierarquia-e-permissoes.md#contrato-http).

Antes de usar uma conta real: revisar/aplicar migrations, configurar os segredos e
executar, dentro de backend, `uv run python -m app.modules.identity.bootstrap_cli`.
O comando solicita confirmação, nome, e-mail e senha oculta; cria operador, hash e
marcador único na mesma transação. Advisory lock e marcador impedem repetições e
execuções concorrentes. Não promove contas existentes nem cria vínculo com tenant.
Se o cadastro for inválido, o comando identifica o campo e explica sua regra sem
mostrar o conteúdo digitado. A senha permite caracteres especiais e deve conter
entre 8 e 128 caracteres; falhas de configuração são indicadas separadamente.
O bloqueio local de senhas é mínimo; uma lista abrangente de senhas comuns/comprometidas
ainda precisa de política de manutenção antes da produção.

Após a validação em bancos temporários, as migrations foram aplicadas ao banco
local do ERP: autenticação inicialmente em `c418d69a02be`; hierarquia e histórico
posteriormente em `e7b1c90a42d3`, convites em `f3a82c17d905` e perfis/permissões em
`a81e73c405bf`, ciclo de vínculos em `b92f8d06e4a1` e revisão de leitura em
`c74e901a6bd2`, cadastro de empresas em `d85fa1049ce3` e concessões por empresa em
`e96b2130ad74`; a fundação financeira está em `f07c4219be86` e suas permissões em
`a18d5320cf97 (head)`, sem diferenças
pendentes de schema.
O segredo foi gerado diretamente em `backend/.env`, sem exibição ou versionamento.
O primeiro operador foi criado pelo desenvolvedor no comando interativo, sem
compartilhar senha ou token no chat.

Na validação local, a API respondeu 200 no health check, 401 para criação/consulta
sem sessão e 401 para credenciais inexistentes. Login autorizado e logout com sua
conta foram confirmados pelo desenvolvedor em 31/10/2026: login 200, logout 204 e
acesso protegido com token revogado 401. Essa confirmação foi manual via Swagger;
os testes automatizados também cobrem o fluxo em infraestrutura isolada.

O [catálogo e a gestão de perfis](perfis-e-permissoes.md) acrescentam concessões por
perfil sem remover as flags anteriores. Escritas administrativas confirmam senha,
usam rate limit próprio e registram auditoria; não emitem nova sessão nem incorporam
permissões ao token. Revisões e origem da autoridade são conferidas no servidor.

## Rotas públicas e pendências

`GET /api/v1/health` permanece público e retorna somente `status`, sem ambiente,
versão, credenciais ou descrição da infraestrutura. `/docs`, `/redoc` e OpenAPI ficam
desabilitados em staging/production. Isso não substitui autorização das rotas.

Permissões operacionais dos módulos futuros, auditoria completa, recuperação de conta, troca de senha,
revogação de todas as sessões e frontend ainda não foram entregues. A base não deve
ser tratada como pronta para produção somente porque o login está implementado.

Leitura de cadastros por empresa já exige concessão específica. A proteção global
de erros, o identificador de requisição e as regras de segredos estão descritos em
[erros, logs e segredos](erros-logs-e-segredos.md). Para execução local, usar o
launcher `uv run python -m ops.serve --reload`, que aplica o formato seguro de logs.

Referências: [autenticação da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
e [sessões da OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
