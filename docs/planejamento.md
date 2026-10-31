# Planejamento do SD Financeiro ERP

Atualizado em 30/10/2026.

## Direção do produto

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
módulos. A entrega atual é o service de Organization, aguardando aprovação.

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
   quatro novos testes do service no banco temporário exclusivo. Service aguarda
   revisão e aprovação; endpoints serão uma etapa posterior separada.
4. Aplicação de Company: contratos, validações, persistência e endpoints, em etapas
   separadas, revisando a regra de unicidade do identificador fiscal.
5. Identidade e isolamento: estratégia de tenancy, autenticação, autorização,
   vínculos e permissões por empresa; validar acessos indevidos entre tenants.
   Esses controles são necessários antes de operar com dados reais multi-tenant.
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
agendadas, modelos de IA ou módulos adicionais. A entrega atual é o service
de Organization, aguardando aprovação.
