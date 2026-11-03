# Segmentos, contratação e governança

Decisão de produto: o primeiro segmento comercial será **Empresarial: financeiro e gestão de empresas
de serviços**. Saúde, Varejo e outros segmentos seguirão o mesmo modelo, individualmente, depois de
seus fluxos, regras e controles serem implementados e validados. Não oferecer todos os segmentos no MVP.
Este documento define a arquitetura pretendida; licenciamento e cobrança ainda não estão implementados.

A primeira matriz detalhada de funcionalidades, limites propostos e critérios de autorização está em
[Planos Empresarial/Serviços](planos-empresarial-servicos.md). É uma especificação de produto, ainda sem oferta comercial ativa.

## Contratação em duas dimensões

O cliente escolhe um segmento e um plano dentro dele: Essential, Professional ou Enterprise.
Exemplos futuros: Empresarial Professional, Saúde Essential e Varejo Enterprise.
Enterprise amplia os recursos contratados daquele segmento; não libera automaticamente outros segmentos.
O mesmo nome de plano pode oferecer funcionalidades distintas em cada segmento, descritas em sua matriz.
Preço, cotas e recursos só serão publicados após validação comercial e disponibilidade da implementação.

A contratação pertence à organização. A ativação em cada empresa/unidade precisa ser explícita e respeitar
o contrato. Uma organização poderá contratar segmentos adicionais futuramente, com vínculos e escopos
independentes. O usuário escolhe somente contextos já autorizados; não pode habilitar recursos pelo seletor.

## Verificação de acesso no servidor

Acesso exige simultaneamente:

1. Usuário e sessão válidos, com vínculo ativo na organização.
2. Empresa autorizada e contexto de operação válido.
3. Segmento contratado e habilitado para aquele contexto.
4. Recurso incluído no plano e dentro dos limites aplicáveis.
5. Permissão específica do usuário para executar a operação.

Master administra a organização dentro dos recursos contratados. Nem Master nem CEO podem liberar uma
funcionalidade paga por alteração de cargo ou permissão. Concessão interna não substitui contratação.
Menus refletem os direitos de uso; APIs aplicam a decisão mesmo diante de URL direta ou requisição manual.
Importações, relatórios, exports, jobs, integrações e IA seguem as mesmas fronteiras.

Catálogo conceitual a implementar: segmentos, módulos/funcionalidades, versões de planos, itens contratados,
habilitação por empresa e decisões de uso. Identificadores são estáveis; detalhes comerciais são versionados.
Mudanças de assinatura e concessões precisam invalidar caches, com revalidação nas escritas e controle de
concorrência nas cotas. Não confiar em plano informado pelo navegador ou congelado em token de longa duração.
Confirmações de cobrança futuras vêm de integração de servidor autenticada, com idempotência e auditoria.

Suspensão e downgrade terão política explícita: preservar dados, impedir novas operações incompatíveis e
definir consulta/exportação e prazos contratualmente. Login, logout, proteção da conta e canais de privacidade
não dependem de uma funcionalidade comercial premium. Segurança fundamental se mantém em todos os planos.

## Separação dos motores

Manter núcleo compartilhado de identidade, organizações, autorização, auditoria e infraestrutura.
Financeiro comum expõe contratos explícitos de títulos, movimentos e conciliação. Cada segmento possui
serviços de domínio próprios, validações, modelos quando necessários, APIs e testes de isolamento.
Estratégias e dados de domínio não circulam livremente entre módulos nem ficam em variáveis globais.

Exemplos de domínios futuros:

- Empresarial/Serviços: prestação de serviços, contratos, obrigações e indicadores financeiros.
- Saúde: operação assistencial e seus controles específicos, quando implementados e validados.
- Varejo: catálogo, vendas, estoque e operação comercial, quando implementados e validados.

Integrações carregam apenas os dados necessários. Um lançamento originado em Saúde pode indicar valor e
referência autorizada sem revelar conteúdo clínico ao financeiro. Uma tela de Varejo não recebe dados de Saúde.
Consultas consolidadas entre contextos exigem permissão própria e escopo explícito. Separação de pacotes ou
de processos, sozinha, não substitui autorização e testes. Começar como aplicação modular e avaliar isolamento
de infraestrutura conforme necessidade real, sem prometer bancos ou microserviços separados já existentes.

## Regras fiscais e estratégias

Cada segmento terá seu contexto e suas estratégias de análise. O segmento é uma dimensão de seleção;
o enquadramento fiscal também considera país, jurisdição, regime da empresa, atividade, operação e vigência.
Não atribuir um imposto único a toda empresa de Saúde ou Varejo apenas por ter escolhido aquele modo.
Regras compartilhadas podem ser reutilizadas por contratos, mantendo contexto e configuração explícitos.
Toda simulação futura precisa registrar versão, entradas, premissas e origem da regra, com validação especializada.
Trocar de modo visual não altera o regime fiscal, o histórico ou a configuração da empresa.
Benefícios e economia estimada exigem evidências e revisão; não garantir redução de tributos por assinatura.

## Termos, privacidade e contratos

Preparar para revisão jurídica, antes da oferta comercial:

- Termos de uso: condições de acesso, responsabilidades, funcionalidades, limites e uso permitido.
- Aviso de privacidade: finalidades, dados tratados, compartilhamentos, retenção e canais de atendimento.
- Contrato de assinatura: segmento, versão do plano, módulos, cotas, cobrança, suporte, suspensão e encerramento.
- Instrumento de tratamento de dados: papéis e instruções conforme a operação efetiva, subprocessadores e segurança.
- Condições de migração e saída: escopo, aprovação, responsabilidades, exportação e destino dos dados.
- Anexos próprios de cada segmento quando necessários, sem estender condições de um segmento a outro implicitamente.

Não publicar documentos fictícios como termos definitivos. O fluxo técnico deverá registrar documento,
versão, hash do conteúdo, autor e momento do aceite, com acesso ao texto aceito e política para novas versões.
Aceite de termos e eventuais consentimentos têm finalidades diferentes e precisam ser tratados separadamente;
uma caixa de seleção não legitima qualquer coleta. Documentos pessoais e biometria continuam fora deste incremento.

Referência para revisão dos papéis de tratamento: [Guia da ANPD sobre agentes de tratamento e encarregado](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-para-definicoes-dos-agentes-de-tratamento-de-dados-pessoais-e-do-encarregado).
Os papéis dependem das atividades efetivas; a redação contratual deve refletir a operação.

## Ordem para implementação

1. Delimitar o MVP Empresarial/Serviços e a matriz de recursos dos seus três planos.
2. Modelar direitos de uso, habilitação de módulos e política central de autorização comercial.
3. Testar bloqueios por assinatura, empresa, segmento e permissão também fora da interface.
4. Integrar a abertura da organização, a contratação e os aceites versionados dos documentos revisados.
5. Entregar e homologar os fluxos do segmento inicial, incluindo migração de clientes.
6. Construir cada segmento adicional com matriz comercial, regras, documentação e homologação próprias.

Critérios de aceite incluem: plano superior não libera outro segmento; Master não burla contratação;
alteração manual de contexto não expõe dados; revogação bloqueia operações e jobs; downgrade preserva
histórico; o motor recebe configuração fiscal explícita; integrações e IA não atravessam fronteiras de dados.
