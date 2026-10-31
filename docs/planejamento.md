# Planejamento do SD Financeiro ERP

Atualizado em 31/10/2026.

## Direção do produto

### Público e identidade jurídica

O produto atende exclusivamente empresas, sem operação ou contratação para pessoa
física. `Company` representa empresa identificada por CNPJ; CPF não será aceito como
identificador alternativo. CNPJ numérico/alfanumérico e regras do cadastro jurídico
foram implementados na etapa de Company, com base nas fontes oficiais vigentes.

`User` identifica a pessoa autorizada a acessar o ERP, sem constituir cliente
pessoa física. `Organization` representa o espaço do cliente e agrupa uma ou mais
empresas, sem duplicar o identificador jurídico de Company. A pessoa que contrata
ou opera o sistema atua em nome da empresa, conforme os vínculos e permissões.

ERP empresarial generalista, desenvolvido como monólito modular em Python 3.14,
FastAPI, SQLAlchemy Async e Psycopg, com PostgreSQL. Manter a stack e introduzir
camadas e módulos somente quando houver responsabilidade concreta.

### Visão aprovada: parceiro virtual da empresa

Além de organizar e gerir os processos empresariais cobertos pelo produto, o SD
Financeiro deverá apoiar decisões para aumentar receita, lucro e geração de caixa,
reduzir desperdícios e identificar oportunidades tributárias legalmente aplicáveis.
A cobertura será ampliada conforme os módulos e dados disponíveis; não representa
gestão automática de toda a empresa nem garantia de resultado econômico.

O sistema deverá transformar registros, cálculos, sinais operacionais e previsões
em oportunidades explicáveis e acionáveis. Essa capacidade integra as análises de
desperdícios e inovação já previstas, sem mudar a arquitetura ou antecipar módulos.

| Objetivo | Exemplos de oportunidades futuras |
| --- | --- |
| Aumentar faturamento | Demanda não atendida, clientes sem recompra e oportunidades de venda, quando houver histórico suficiente |
| Melhorar lucro e margem | Preços, descontos, custos e combinação de produtos ou serviços, considerando restrições do negócio |
| Gerar e preservar caixa | Recebimentos em atraso, prazos de compra e venda e capital comprometido em estoque |
| Reduzir gastos | Duplicidades, encargos evitáveis, desperdícios e contratos a revisar |
| Melhorar eficiência tributária | Possíveis créditos, pagamentos em excesso e incentivos sujeitos a enquadramento e validação |
| Viabilizar inovação | Gargalos que justifiquem projetos tecnológicos e análise de seu retorno e de incentivos aplicáveis |

### Funcionamento e limites das recomendações

- Identificar sinais a partir de eventos e revisões periódicas quando houver
  necessidade concreta. Agendamentos, infraestrutura e frequência serão definidos
  na implementação; não há monitoramento contínuo implementado nesta fase.
- Começar por regras e cálculos verificáveis. Introduzir previsões somente com
  histórico suficiente, validação contra resultados observados e comparação com
  uma referência simples; indicar horizonte, premissas e incerteza.
- Distinguir fato observado, hipótese, previsão e recomendação. Se faltarem dados,
  sinalizar a limitação e solicitar os insumos necessários em vez de inventar valores.
- Cada oportunidade deverá indicar origem dos dados, empresa, período, motivo,
  impacto estimado, esforço e custos da ação, prazo, riscos, responsável e próximo
  passo. Priorizar por impacto, urgência, qualidade das evidências e viabilidade.
- Mostrar efeitos separados sobre faturamento, margem, lucro, tributos e caixa.
  Mais vendas não implica necessariamente mais lucro ou caixa; uma redução de
  custo pode afetar qualidade, capacidade e receita. Explicitar esses efeitos.
- Evitar alertas repetidos e excesso de notificações; permitir configurar limites,
  destinatários, frequência e tratamento de oportunidades já avaliadas.
- Recomendações exigem revisão por pessoa autorizada. Não executar automaticamente
  alterações em preços, pagamentos, contratos ou apurações tributárias.
- Acompanhar oportunidade identificada, avaliação, decisão, execução e resultado;
  separar benefício potencial de benefício realizado e evitar dupla contagem entre
  análises de receita, custos e tributos. Registrar referência de comparação e não
  atribuir toda variação posterior ao efeito da recomendação.
- Aplicar isolamento por tenant e permissões por empresa também às previsões,
  agregações, históricos, exportações e notificações. Minimizar dados sensíveis e
  não compartilhar informações entre clientes ou com serviços externos sem os
  controles e autorizações correspondentes.

Essa visão orientará entregas futuras, com escopo e critérios de aceite próprios.
Não introduzir agora chatbot, agentes autônomos, modelos preditivos, jobs ou novos
módulos. A entrega atual é a integração HTTP de autenticação e proteção de Organization.

### Área executiva aprovada: painel de desempenho e oportunidades

Criar futuramente uma área dedicada à visão de parceiro virtual, com gráficos e
indicadores baseados nos dados reais da empresa e recomendações de melhoria.
O nome comercial será definido posteriormente; `SDF Organization` é apenas uma
ideia de nome, sem alterar o significado técnico de Organization como tenant.

O painel reunirá progressivamente as áreas disponíveis no ERP: financeiro,
comercial, compras, estoque, fiscal e operação. Novas áreas só serão apresentadas
quando houver dados e indicadores confiáveis; ausência de informação não equivale
a resultado zero e não deve ser preenchida com números fictícios.

#### Organização funcional proposta

- Visão geral: indicadores prioritários de receita, margem, resultado, caixa,
  despesas e capital em estoque, conforme os dados existentes. Explicitar a
  definição e o período de cada indicador, inclusive regime de caixa ou competência.
- Visões por área: gráficos de evolução, composição, metas e comparações entre
  períodos equivalentes, com acesso aos registros que explicam cada resultado.
- Oportunidades: lista priorizada do que pode melhorar, onde economizar e onde
  ampliar receita ou margem, vinculando cada recomendação aos indicadores e
  evidências correspondentes. Informar impacto estimado, responsável e próximo passo.
- Projeções e cenários: apresentar previsões e simulações claramente separadas
  dos resultados realizados; mostrar premissas, horizonte e incerteza.
- Acompanhamento: registrar decisões e ações e acompanhar benefícios realizados,
  sem contar o mesmo resultado em mais de uma oportunidade.

#### Requisitos dos dados e da experiência

- Filtrar por empresa, período e demais dimensões existentes e autorizadas, como
  centro de custo ou unidade. Consolidar empresas somente com permissão explícita,
  regras de consolidação definidas e identificação das empresas incluídas.
- Mostrar origem, data da última atualização, cobertura e eventuais pendências
  de conciliação dos dados. Não prometer atualização em tempo real antes de definir
  a arquitetura e a frequência necessárias.
- Permitir detalhamento dos gráficos até documentos e lançamentos de origem,
  respeitando as mesmas permissões dos módulos responsáveis.
- Distinguir medição observada, meta, referência comparativa, estimativa e previsão.
  Comparações devem respeitar moedas, unidades, sazonalidade e volume de atividade.
- Definir fórmulas e fontes únicas para os indicadores, reconciliáveis com os
  relatórios de cada módulo. Não inferir lucro apenas pela diferença de entradas
  e saídas de caixa.
- Validar autorização no servidor também para agregações, filtros, caches,
  exportações e detalhamentos; ocultar um componente na interface não protege dados.
- Priorizar legibilidade, navegação simples e gráficos com identificação textual,
  sem depender apenas de cores para comunicar situação ou prioridade.

#### Evolução incremental

Após os controles de acesso e os primeiros fluxos financeiros estarem validados,
definir a primeira versão do painel com poucos indicadores confiáveis e acesso às
evidências. Acrescentar as demais áreas e recomendações conforme seus módulos forem
entregues. Prototipar e aprovar a interface quando essa etapa iniciar, sem escolher
agora stack de frontend, criar telas ou implementar consultas analíticas.

O desenvolvimento avança por etapas: definir, implementar, validar, revisar e
obter aprovação antes de iniciar a próxima. As etapas futuras abaixo são direção
de planejamento; seus contratos e critérios de aceite serão detalhados no momento
apropriado.

## Sequência de desenvolvimento

1. Fundação técnica: ambiente reconstruído, seis testes aprovados, PostgreSQL e
   Redis saudáveis, migration `ed92b41e1e71` aplicada e health check validado com
   conexão disponível e indisponível via cliente de testes.
2. Schemas `OrganizationCreate` e `OrganizationResponse` implementados: validação
   de entrada, rejeição de campos extras e serialização ORM com timestamps com
   fuso horário. Nove testes novos e seis anteriores passaram (15 no total).
   Entrega aprovada pelo desenvolvedor; sem service, rotas ou schemas de Company.
3. Aplicação de Organization: repository implementado com criação por `flush` e
   busca por UUID, sem `commit`. Cinco testes de integração passaram em banco
   temporário exclusivo no PostgreSQL local, com migrations aplicadas e remoção
   ao final. Repository aprovado pelo desenvolvedor. Service implementado com
   criação transacional, conversão para resposta e consulta opcional por UUID;
   falhas revertem a criação. Suíte completa com 24 testes aprovados, incluindo
   quatro novos testes do service no banco temporário exclusivo. Service aprovado
   pelo desenvolvedor. Contratos HTTP e política de acesso especificados em
   `docs/api-organizations.md`. A base de identidade possui `User` e
   `OrganizationMembership`, defaults restritivos e migration `4db0f645bda1`
   validada apenas em banco temporário. Oito testes novos passaram, totalizando
   32 testes. Política `OrganizationAccessPolicy` implementada com verificações
   SQL de usuário ativo e concessões no tenant, sem leitura global implícita.
   Onze testes novos validam matriz de permissões, separação entre tenants,
   revogação confirmada e falhas; suíte completa com 43 testes aprovados.
   Proteção de senhas implementada com `pwdlib[argon2]`, funções assíncronas e
   armazenamento separado `UserPasswordCredential`. Migration `9e3d7a51c286`
   validada somente em banco temporário. Oito testes de hash e quatro de persistência
   passaram; suíte completa com 55 testes aprovados.
   Fluxo de autenticação, bootstrap e publicação HTTP continuam pendentes.
   Sessões internas implementadas com tokens opacos, hash persistido, expiração
   somente por inatividade e revogação. Atividade válida renova o prazo; não há
   duração máxima absoluta enquanto o usuário trabalha. Consultas automáticas
   não renovam a sessão. Migration `ba72c81409ef` validada somente em banco
   temporário. Dois testes de configuração e 20 de integração de sessões;
   suíte validada nessa etapa com 77 testes. Rate limit interno implementado com
   `redis-py`, Lua atômico, limites por conta/origem/geral e HMAC para chaves.
   Oito testes unitários e oito testes Redis adicionados; suíte completa com 93
   testes aprovados nessa etapa. Bootstrap administrativo implementado com comando
   interativo, senha oculta, criação transacional, advisory lock e marcador único.
   Migration `c418d69a02be` validada somente em banco temporário; nenhuma conta
   real criada. Nove testes de entrada/CLI e nove de integração adicionados,
   totalizando 111 testes nessa etapa. Login e logout HTTP implementados com rate
   limit, revalidação de credencial na emissão, respostas seguras e limite de hash.
   Rotas de Organization exigem sessão e permissão no servidor, com resposta 404
   uniforme para tenants sem acesso. Dezesseis testes HTTP adicionados; total de
   127 testes validados. Após revisão, migrations aplicadas ao banco local na
   revisão `c418d69a02be (head)` e segredo gerado no `.env`, sem exibição.
   API local validada: health 200 e acesso sem sessão/login inexistente com 401.
   Primeiro operador criado pelo desenvolvedor. Validação manual confirmada em
   31/10/2026: login 200, logout 204 e acesso protegido com token revogado 401.
   Etapa de autenticação local aprovada; próxima etapa é definir gestão de usuários
   e vínculos organizacionais, sem cadastro público ou concessão automática de privilégios.
   Desenho da hierarquia e delegação registrado em `docs/hierarquia-e-permissoes.md`:
   proprietário/Master do tenant separado do operador da plataforma; cargos não
   geram herança automática; perfis por ação e escopo. Inclui base comum e as
   verticais previstas de Saúde, Varejo, Indústria e Serviços. Ainda sem alteração
   dos privilégios existentes ou implementação antecipada desses módulos.
   Primeira etapa de persistência implementada em `identity/access_models.py`:
   proprietário por organização, perfis e atribuições com FKs compostas que impedem
   referências entre tenants. Categorias sem herança e defaults inativos.
   Migration `d2a6f09b84c1` validada em banco temporário, sem aplicação local nesta
   etapa. Doze testes novos e suíte completa com 142 testes nessa primeira entrega.
   Incremento seguinte: serviço interno de designação inicial pelo provisionador
   e transferência exclusiva pelo proprietário, ambos com sessão e senha válidas,
   vínculos ativos, locks e histórico na mesma transação. Migration de histórico
   `e7b1c90a42d3`, sem aplicação local. Quatorze testes adicionais de segurança,
   concorrência, atomicidade e migrations; suíte completa com 156 testes aprovada.
   Contratos e rotas de propriedade implementados com respostas mínimas, rate limit
   por ator/origem/geral separado do login e vagas de hash compartilhadas. Sucesso
   renova inatividade na mesma transação; recusas não renovam. Próximo passo:
   onboarding e convites/vínculos seguros, antes da gestão e do catálogo.
   Suíte completa atual: 173 testes aprovados. Após revisão, migrations aplicadas
   ao PostgreSQL local do ERP na porta 5433, revisão `e7b1c90a42d3 (head)`.
   Alembic check sem diferenças; contagens anteriores preservadas, nenhum Master
   atribuído e nenhum banco temporário restante. Health 200 e novas rotas no OpenAPI,
   com recusa 401 sem sessão. Fluxo de sucesso validado em infraestrutura isolada.
   Onboarding e convites implementados: operador provisiona e convida primeiro
   Master; Master convida colaboradores. Aceite cria conta ou confirma senha da
   conta existente sem substituir credenciais. Tokens de uso único, validade de
   24 horas, hash, revogação, reemissão e autoridade revalidada; nenhuma sessão ou
   perfil automático. Leitura do tenant inicial explícita para Master; colaborador
   sem leitura por padrão. Entrega do token manual, sem envio de e-mail nesta etapa.
   Migration `f3a82c17d905`; contrato em `docs/onboarding-e-convites.md`.
   Validação atual: 208 testes aprovados, 35 novos para convites. Migration aplicada
   à porta 5433 em `f3a82c17d905 (head)`, sem alteração das contagens anteriores ou
   criação de convites reais. Schema alinhado e bancos temporários removidos.
   API local atualizada: health 200, cinco contratos no OpenAPI, gestão sem sessão
   401 e aceite de token inexistente 400. Entrega e verificação de e-mail precisam
   de integração antes de produção; token manual depende da confiança no emissor.
   Catálogo fechado e gestão de perfis implementados em `identity/permissions.py`,
   `permission_models.py`, `roles.py` e `api/v1/roles.py`. Concessões iniciais de
   `organizations.read` e `identity.roles.read`; ações administrativas reservadas
   ao Master ou à delegação explícita de atribuições. Tetos, origem, revisões,
   auditoria transacional e invalidação por transferência/revogação implementados.
   Flags antigas preservadas, sem conversão automática. Diretório mínimo somente
   para Master, listas paginadas e dados de credenciais fora das respostas.
   Validação atual: 248 testes aprovados, 40 novos de perfis. Migration
   `a81e73c405bf` aplicada à porta 5433 com schema alinhado, flags/status/contagens
   preservados, sem novas concessões ou delegações reais e sem bancos temporários
   restantes. API local atualizada: health 200, novos contratos no OpenAPI e
   recusa 401 sem sessão. Detalhes em `docs/perfis-e-permissoes.md`.
   Ciclo de vínculos implementado: GET/PUT de status somente para Master, confirmação
   de senha, revisão e propriedade atual protegida. Desativação limpa leitura antiga,
   perfis, delegação/concessões originadas e convites pendentes no tenant; reativação
   não restaura acesso. Conta global, sessões e outros tenants são preservados.
   Validação atual: 274 testes aprovados, 26 novos. Migration `b92f8d06e4a1` aplicada
   à porta 5433, schema alinhado e flags/status/contagens anteriores preservados.
   Nenhum vínculo real alterado e nenhum banco temporário restante. API local com
   health 200, GET/PUT de status no OpenAPI e recusa 401 sem sessão. Documentação em
   `docs/ciclo-de-vida-de-vinculos.md`. Downgrade bloqueia perda do histórico de status.
   Revisão de leitura antiga implementada: Master consulta a origem efetiva da
   leitura, converte explicitamente a flag em perfil ativo com somente
   `organizations.read`, ou revoga apenas essa flag. Senha, revisões de vínculo/
   perfil/atribuição, escopo e auditoria são validados na mesma transação. Não há
   conversão automática, retirada da coluna ou alteração dos contratos de convite.
   Validação atual: 302 testes aprovados, 28 novos. Migration `c74e901a6bd2` aplicada
   à porta 5433 com flags/status/revisões/contagens preservados, schema alinhado e
   nenhum acesso real convertido/revogado. Sem bancos temporários restantes. Health
   local 200, três contratos no OpenAPI e recusa 401 sem sessão. Documento essencial:
   `docs/revisao-de-acessos.md`. Próximo incremento: contratos de Company/CNPJ.
   Documentação essencial em `docs/autenticacao.md` e `docs/api-organizations.md`,
   em nível intermediário de detalhe (5/10), conforme preferência do desenvolvedor.
   Mensagens de validação do bootstrap ajustadas para indicar campo e regra sem
   refletir dados; três testes novos validados, totalizando 130 testes no projeto.
   Por decisão do desenvolvedor, novas senhas aceitam de 8 a 128 caracteres,
   com mensagens e validações alinhadas no cadastro e na geração do hash.
   Rate limit é requisito aprovado para o login: limites combinados por origem e
   conta, resposta 429 com espera informada e validação de concorrência, proxies
   e indisponibilidade do armazenamento antes de disponibilizar autenticação.
   Endpoints não serão expostos sem controles
   mínimos de identidade, vínculos e permissões, que precederão sua publicação.
4. Aplicação de Company: cadastro jurídico implementado com contratos, repository,
   service e rotas. Master cria/consulta/edita nomes e status interno, com senha,
   revisão e auditoria transacional. CNPJ numérico/alfanumérico validado em Python
   e PostgreSQL conforme manual oficial, canônico e imutável na edição. Unicidade
   revisada para `(organization_id, tax_id)`, sem descoberta ou compartilhamento
   entre tenants. Migration `d85fa1049ce3` valida legado sem correção automática e
   protege downgrade incompatível. Contrato em `docs/api-companies.md`. Leitura de
   colaboradores por empresa foi acrescentada no incremento de isolamento abaixo;
   operações fiscais/financeiras específicas continuam pendentes.
   Validação atual: 332 testes aprovados, 30 novos, incluindo regressões da extração
   da autorização transacional compartilhada. Migration aplicada em `d85fa1049ce3`
   na porta 5433, schema alinhado e dados/flags/status/revisões/contagens anteriores
   preservados. Nenhuma empresa real criada/alterada e nenhum banco temporário
   restante. API local: health 200, quatro operações empresariais no OpenAPI e
   recusa 401 sem sessão. Vetores oficiais e lógica Python/SQL validados em banco
   temporário, sem consultas externas ou credenciais reais nos testes.
5. Identidade e isolamento: estratégia de tenancy, autenticação, autorização,
   vínculos e permissões por empresa; validar acessos indevidos entre tenants.
   Esses controles são necessários antes de operar com dados reais multi-tenant.
   Leitura de cadastros por empresa implementada: concessão direta `companies.read`
   pelo Master, com revisão da empresa, vínculo e concessão. Sem wildcard ou acesso
   a empresas futuras. Listagem filtra a autorização antes da paginação; consulta
   por UUID exige o mesmo escopo. Vínculo/empresa inativos negam acesso; inativar e
   reativar limpa concessões sem restaurá-las. Transferência preserva concessões
   diretas e muda o administrador. Migração `e96b2130ad74`, sem semear acesso.
   Auditoria transacional e constraints compostas protegem escopo e integridade.
   Contrato em `docs/acesso-por-empresa.md`. Não inclui ações fiscais/financeiras.
   Validação: 363 testes aprovados, incluindo 31 novos. Migration aplicada no
   PostgreSQL local, porta 5433, preservando dados anteriores e sem criar concessões
   reais. Health 200 e rotas protegidas com resposta 401 sem sessão.
6. Base operacional: auditoria, erros e logs seguros, segredos por ambiente,
   backup e restauração, validações automatizadas.
7. Definição e entrega do MVP: selecionar os fluxos necessários de cadastros,
   financeiro, comercial, estoque, compras, fiscal e relatórios. Cada módulo terá
   escopo e aprovação próprios.
8. Integrações concretas exigidas pelo MVP, com contratos e adapters próprios.
9. Homologação e produção: fluxos completos, segurança, recuperação de falhas,
   implantação e monitoramento.
10. Evolução: gestão da inovação, incentivos fiscais e identificação de desperdícios
    conforme as dependências abaixo; novas integrações e verticais somente mediante
    demanda concreta.

A primeira versão será considerada concluída com escopo aprovado, homologado e
operando com segurança. As capacidades futuras abaixo não ampliam automaticamente o MVP.

## Capacidade futura aprovada: inovação e oportunidades tributárias

O ERP deverá ajudar a identificar áreas da empresa que podem melhorar com
tecnologia, estruturar projetos e avaliar oportunidades tributárias que possam
reduzir seu custo e favorecer o caixa. A Lei do Bem é a referência inicial para
estudo, sem restringir a evolução a um único incentivo.

### Fluxo desejado

1. Evidenciar gargalos, perdas e oportunidades a partir de dados operacionais e
   financeiros autorizados; permitir registro de ideias pelos responsáveis.
2. Estruturar projetos com objetivos, desafios tecnológicos, atividades,
   responsáveis, orçamento, cronograma e resultados esperados.
3. Fazer triagem de possíveis incentivos considerando empresa, regime tributário,
   período, atividades, dispêndios, requisitos e documentação disponível.
4. Projetar investimento e eventual economia tributária separadamente, incluindo
   premissas, incertezas e momento esperado de efeito no caixa.
5. Acompanhar execução, custos e evidências técnicas e contábeis por projeto.
6. Apoiar revisão técnica e tributária, decisão de aproveitamento e acompanhamento
   do resultado efetivamente realizado.

### Limites e requisitos

- Distinguir recuperação de pagamento indevido, créditos não aproveitados e
  incentivos à inovação: cada oportunidade exige regras e evidências próprias.
- Melhoria tecnológica ou compra de software não comprova, por si só,
  enquadramento em incentivo. A triagem deverá registrar pendências e justificativas.
- Não tratar incentivo como financiamento antecipado, nem como autorização para
  deixar de recolher tributos. Separar estimativa, validação, aproveitamento e
  efeito realizado no caixa; não gerar saldo disponível com base em mera projeção.
- O enquadramento e os cálculos dependerão de fontes oficiais vigentes e revisão
  pelos responsáveis técnicos e tributários antes do aproveitamento.
- Registrar fonte normativa, vigência, versão das regras, premissas e evidências
  de cada análise. A referência inicial não congela regras ou percentuais.
- Manter regras tributárias no domínio fiscal; informações financeiras e de
  projetos devem integrar-se por contratos explícitos, preservando responsabilidades.
- Isolar dados e documentos por tenant e empresa, aplicar permissões e auditoria,
  minimizar dados sensíveis e impedir sua exposição em logs ou análises de outros
  clientes. Qualquer envio a serviços externos deverá ter finalidade e autorização
  definidas, com os controles de proteção correspondentes.
- Não implementar agora motor de incentivos, cálculos, tabelas ou endpoints.

### Condições para iniciar essa entrega

Base de acesso e isolamento validada; dados fiscais e financeiros confiáveis;
definição do perfil de empresas e do primeiro incentivo; regras vigentes revisadas;
critérios de aceite e responsáveis pela validação definidos. A posição exata dessa
entrega será revista conforme essas condições, sem antecipar módulos especulativos.

### Referências oficiais para aprofundamento

- [Lei nº 11.196/2005, capítulo III](https://www2.camara.leg.br/legin/fed/lei/2005/lei-11196-21-novembro-2005-539221-normaatualizada-pl.html).
- [Legislação da Lei do Bem — MCTI](https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/lei-do-bem/paginas/legislacao).

Revalidar as fontes e os atos aplicáveis ao período antes de especificar ou aplicar
regras de elegibilidade e cálculo.

## Capacidade futura aprovada: identificação de desperdícios e gastos evitáveis

Analisar os dados disponíveis nos módulos do ERP para apontar oportunidades de
redução de custos, com evidências verificáveis e contexto operacional. Um gasto
fora do padrão é um indício a investigar; não comprova desperdício ou irregularidade.

### Cobertura progressiva

| Área | Exemplos de indícios a analisar |
| --- | --- |
| Financeiro | Possíveis pagamentos duplicados, juros e multas recorrentes, tarifas e cobranças acima do contratado |
| Compras | Divergências entre pedido e cobrança, compras emergenciais recorrentes, variações de preço para itens e condições equivalentes |
| Estoque | Excesso de cobertura, itens sem movimentação, perdas, vencimentos e rupturas que geram compras emergenciais |
| Comercial | Descontos fora da política, devoluções recorrentes e operações com margem inferior à meta definida |
| Contratos e serviços | Renovações próximas, serviços sobrepostos e capacidade contratada pouco utilizada, quando houver dados de uso |
| Operação | Retrabalho, consumo de materiais e custos por unidade fora das referências internas, quando houver medições confiáveis |
| Fiscal | Encaminhamento de possíveis pagamentos em excesso e créditos à análise tributária específica |

A cobertura depende dos módulos e integrações efetivamente existentes. Não afirmar
detecção de consumo, produtividade ou uso de licenças sem os dados correspondentes.

### Abordagem de implementação

1. Preparar dados: categorizar despesas, identificar fornecedores e documentos,
   separar previsto, comprometido, pago e estornado, vincular contratos, empresas
   e centros de custo quando esses conceitos forem introduzidos no domínio.
2. Começar com regras explícitas e configuráveis: possível duplicidade, cobrança
   acima do contrato e recorrência de encargos. Não depender de IA para a primeira
   entrega; registrar os critérios utilizados.
3. Acrescentar comparações históricas e orçamentárias quando houver dados suficientes,
   considerando sazonalidade, volume de atividade, unidade, moeda e condições de
   compra. Uma alta absoluta de despesa não implica perda de eficiência.
4. Emitir alertas com empresa, período, registros de origem, regra e versão,
   justificativa, qualidade dos dados, valor potencial e premissas. Indicar quando
   não houver informação suficiente para estimar economia.
5. Permitir investigação pelo responsável: confirmar, descartar com justificativa,
   planejar uma ação e acompanhar o resultado, mantendo histórico de decisões.
6. Medir economia efetiva contra uma referência documentada, com janela temporal
   e custos da ação. Separar redução recorrente, custo futuro evitado e recuperação
   pontual; impedir dupla contagem entre alertas e oportunidades tributárias.
7. Avaliar detecção estatística e IA somente após validar a qualidade dos dados e
   das regras iniciais. Explicações geradas não substituem evidências nem aprovação.

### Controles e critérios de aceite

- Alertas são recomendações; não cancelar pagamentos, contratos, compras ou alterar
  tributos automaticamente. Decisões devem considerar impacto operacional e
  obrigações assumidas, com aprovação conforme as permissões.
- Distinguir parcelas, rateios, recorrências legítimas, estornos e documentos
  cancelados de duplicidades. Deduplicar alertas reprocessados.
- Garantir isolamento por tenant e autorização por empresa também nas consultas
  analíticas, tarefas em segundo plano, exportações e notificações. Comparações
  entre empresas exigem autorização explícita; não comparar clientes distintos.
- Minimizar dados em alertas e logs. Não enviar dados a serviços externos de IA
  sem finalidade, autorização e controles definidos.
- Exibir economia potencial separada de saldo disponível e economia realizada.
- Validar com casos confirmados e casos legítimos semelhantes, acompanhar falsos
  positivos e desempenho das consultas; ajustar limiares conforme o contexto.
- Manter regras de negócio nos módulos responsáveis; introduzir análise transversal
  por contratos explícitos, sem espalhar regras de custos em controllers ou criar
  dependências circulares.

### Primeira entrega proposta e dependências

Após financeiro, cadastros e controles de acesso estarem validados, detalhar uma
primeira entrega de possíveis pagamentos duplicados e juros/multas recorrentes.
Os critérios de aceite incluirão rastreabilidade, revisão humana, ausência de
alertas repetidos e testes de isolamento. As demais áreas entram conforme seus
dados estiverem disponíveis e forem aprovadas individualmente.

Esta etapa registra direção de produto; não cria agora tabelas, rotas, tarefas
agendadas, modelos de IA ou módulos adicionais. A entrega atual é a base de
persistência de proprietários, perfis e atribuições e o serviço interno de designação
e transferência com reautenticação e histórico, validados em banco temporário.
As rotas de propriedade já incluem limites de reautenticação e respostas mínimas.
Onboarding e convites/vínculos mínimos estão implementados com aceite e revogação.
O catálogo de permissões e a gestão de perfis/atribuições com teto de delegação estão
implementados. Ativação/desativação de vínculos e proteção do Master também estão
implementadas. A revisão explícita das concessões antigas também está implementada,
com conversão restrita e revogação auditadas. O cadastro básico de Company/CNPJ
está implementado. A leitura de cadastros por colaboradores já exige concessão
explícita por empresa. O próximo incremento é a base operacional, começando por
backup/restauração e validação da recuperação, antes dos módulos empresariais.
