# Backup e recuperação do PostgreSQL local

## Escopo entregue

Ferramenta operacional em `backend/ops/postgres_backup.py`, sem endpoint HTTP.
Cria um backup lógico do banco configurado no contêiner `sd-financeiro-postgres`
e permite ensaiar sua restauração. Não substitui, apaga ou restaura sobre um banco
existente. A porta 5432, utilizada por outra aplicação, não é acessada.

O arquivo inclui dados de todos os tenants do banco, hashes de credenciais,
sessões e históricos de acesso. Seu uso é administrativo; não é uma exportação
que possa ser disponibilizada a colaboradores ou clientes do ERP.

## Criar e conferir um backup

Pré-requisitos: Docker Desktop ativo, PostgreSQL local saudável, Python do backend
com dependências sincronizadas e espaço disponível. Execute em PowerShell
interativo, a partir da raiz do repositório:

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
Set-Location backend
uv sync --locked
uv run python -m ops.postgres_backup create ../backups/erp-local-2026-10-31.sdfbackup
uv run python -m ops.postgres_backup verify ../backups/erp-local-2026-10-31.sdfbackup
```

Escolha um nome novo para cada arquivo. A sobrescrita é bloqueada. A senha é
solicitada sem exibição e precisa ter pelo menos 16 caracteres; é independente
da senha de login do ERP, que continua com mínimo de oito caracteres. A criação
exige confirmação da senha. Não passar a senha por argumento, variável de ambiente,
mensagem ou arquivo do projeto. Guardá-la em um gerenciador de senhas, separada
dos backups. Sem essa senha o arquivo não poderá ser recuperado.

`create` confirma a criação do arquivo, não a recuperabilidade. Somente considerar
o ensaio concluído após `verify` terminar com sucesso. O procedimento não agenda
execuções nem envia arquivos para serviços externos.

## Proteção do arquivo

- `pg_dump -Fc` produz o arquivo lógico. O conteúdo passa pela memória do processo
  e só chega ao disco cifrado, usando Fernet da biblioteca `cryptography`.
- A chave é derivada com PBKDF2-HMAC-SHA256, 1.200.000 iterações e salt aleatório
  de 16 bytes por arquivo. O formato versionado permite evolução posterior.
- A autenticação do conteúdo ocorre antes de iniciar o ensaio. Senha incorreta,
  alteração, truncamento e bytes anexados são recusados. Não há descriptografia
  de arquivo para disco pelo comando.
- Publicação por arquivo temporário cifrado e link atômico, sem sobrescrita.
  Sistemas de arquivos sem suporte a hard links recusam a publicação.
- Backups, dumps e arquivos parciais estão ignorados pelo Git. Isso não substitui
  controle de acesso à pasta nem proteção do disco e da máquina.
- Logs não incluem senha, conteúdo do dump, SQL externo ou stderr das ferramentas.
  O timestamp do Fernet e o tamanho do arquivo são metadados visíveis.

Esta primeira ferramenta limita o dump comprimido a **128 MiB**, pois o formato
Fernet é processado integralmente em memória. O consumo de RAM é maior que esse
tamanho durante cifragem e recuperação. Acima desse limite é necessário adotar
uma solução operacional de maior capacidade, sem aumentar o limite informalmente.
Python não garante eliminação imediata das cópias de segredos da memória.

## Como funciona o ensaio

Após autenticar o arquivo, `verify` inicia um contêiner exclusivo
`sd-restore-check-<uuid>`, com a imagem
`postgres:18.4-alpine`, sem rede, sem portas publicadas e sem diretórios do host
montados. O armazenamento de dados é temporário em RAM, limitado a 512 MiB; o
contêiner tem limites de memória, CPU e processos. Um dump pequeno mas muito
expansível pode exceder esse espaço e falhar com segurança.

O PostgreSQL descartável permite autenticação local sem senha somente dentro desse
contêiner isolado. Essa configuração não é aplicada ao PostgreSQL do ERP.

`pg_restore` executa com `--single-transaction --exit-on-error --no-owner
--no-privileges`. A ferramenta confere:

1. Migration restaurada igual ao head do código atual.
2. Presença das tabelas e colunas esperadas pelos models atuais.
3. Ausência de constraints não validadas e leitura de todas as tabelas públicas.
4. Remoção do contêiner e volumes ao terminar, inclusive em falha de restauração.

O ensaio não abre sessões no ERP restaurado nem publica a API. O sucesso confirma
essa verificação técnica; não é uma comparação integral de dados com o banco em
atividade nem uma validação de todos os fluxos de negócio.

Use somente backups de origem confiável: restauração de PostgreSQL executa código
presente no dump. A criptografia identifica adulteração por quem não possui a
senha; ela não torna confiável um arquivo produzido por outra pessoa com a senha.
O contêiner isolado reduz a exposição, mas não é um ambiente para analisar dumps
hostis. A imagem precisa estar disponível no Docker ou ser obtida do registro.

Em interrupção forçada ou falha do Docker, conferir contêineres cujo nome comece
com `sd-restore-check-`. Remover apenas o nome exclusivo informado pela ferramenta,
com `docker rm --force --volumes NOME_EXATO`. Não usar comandos globais de limpeza.

## Recuperação em incidente e pendências de produção

Esta entrega fornece criação e ensaio; não oferece um comando que substitua o banco
em uso. Em incidente, preservar os volumes e o backup original, preparar ambiente
novo e isolado, recuperar os segredos do ambiente por canal separado e validar a
versão de código correspondente ao backup. O `verify` atual exige o mesmo head;
backups históricos devem ser conferidos com a versão de código correspondente.

Antes de publicar uma instância recuperada, é necessário tratar sessões e convites
restaurados, conferir os acessos e aplicar as migrations necessárias em procedimento
revisado. O Redis de rate limit também precisa de política para retomada; este backup
cobre somente PostgreSQL. Arquivos externos, `.env`, papéis globais do cluster,
configuração Docker e segredos de infraestrutura não são incluídos no dump.

Ainda pendentes: destino externo cifrado com acesso restrito, retenção e expurgo,
agendamento com gestão de segredos, monitoramento de falhas, definição de RPO/RTO
e recuperação pontual com WAL quando exigida. Não remover cópias antigas
automaticamente nesta etapa. Backup apenas no mesmo computador não cobre sua perda.

## Validação

Suíte completa aprovada: **380 testes**, com PostgreSQL, Redis e Docker habilitados.
Esta entrega acrescentou 17 testes: 15 de formato, integridade, publicação e
tratamento de falhas; dois de recuperação real e limpeza em contêiner descartável.
O PostgreSQL local permaneceu saudável e nenhum contêiner de ensaio restou.
Não foi criado um backup dos dados reais nesta validação.

Os testes usam banco exclusivo `sd_repository_test_<uuid>` na porta 5433 e
contêineres descartáveis, sem ler dados reais do ERP. Incluem recuperação de um
registro sintético, preservação da origem, migration/schema, adulteração, senha
incorreta, publicação sem sobrescrita e limpeza após falha.

```powershell
# A partir de backend/, com PostgreSQL local e Docker ativos
$env:SD_RUN_DATABASE_TESTS = '1'
$env:SD_RUN_BACKUP_TESTS = '1'
try {
    uv run python -m unittest discover -s tests -p test_postgres_backup.py -v
} finally {
    Remove-Item Env:SD_RUN_DATABASE_TESTS
    Remove-Item Env:SD_RUN_BACKUP_TESTS
}
```

Referências técnicas: [Fernet](https://cryptography.io/en/stable/fernet/),
[pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) e
[pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html).
