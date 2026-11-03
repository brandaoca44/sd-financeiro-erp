# Evolução do produto e migração de clientes

Direção de produto registrada a partir dos requisitos do responsável pelo SDF.
As funcionalidades abaixo são planejadas; este documento não significa que já estejam disponíveis.

Foco confirmado: **Empresarial, financeiro e gestão de empresas de serviços**. Cada segmento futuro
terá contratação e matriz próprias de Essential, Professional e Enterprise; plano superior não libera
outros segmentos. Consulte [Segmentos, contratação e governança](segmentos-contratacao-e-governanca.md)
para direitos de uso, separação dos motores e preparação dos documentos contratuais.

## Situação atual e fronteiras dos módulos

O backend atual é uma aplicação modular, com identidade/acesso, organizações/empresas e financeiro.
Há autorização por organização, empresa e operação. Não existem ainda motores operacionais separados
para Saúde, Varejo e Indústria, nem assinaturas ativas ou importador de ERP legado. O catálogo de trabalho
e sua página de comparação estão descritos em [Catálogo e página de assinatura](catalogo-assinaturas.md).
O frontend utiliza textos em português, sem cobertura de internacionalização implementada.

A arquitetura pretendida mantém um núcleo comum (identidade, organizações, financeiro, auditoria e
infraestrutura) e módulos de domínio separados. Compartilhar infraestrutura não concede acesso aos dados.
Cada segmento terá contratos, regras, permissões, testes e dados específicos; um módulo não consulta
livremente as tabelas de outro. Integrações ocorrem por contratos explícitos, com autorização e dados mínimos.
Exemplo: atendimento de saúde pode gerar um lançamento financeiro sem enviar prontuário ao financeiro.

Uma organização poderá contratar mais de um segmento quando houver necessidade real. Cada usuário só
acessa os módulos e empresas autorizados. Trocar uma opção visual não muda permissões ou contexto no servidor.
"Empresarial" é o núcleo geral do ERP; Saúde, Varejo, Indústria e Serviços são especializações.
Não é necessário criar microserviços ou bancos separados por segmento para começar; nenhuma fronteira
de autorização pode depender apenas da separação de código ou da interface.

## Como uma empresa migra de outro ERP

Jornada pretendida: abertura validada da organização → escolha da origem → diagnóstico → importação
em área de preparação → mapeamento → simulação → conciliação → aprovação → entrada em operação.
Integrações específicas com cada fornecedor serão construídas conforme demanda. Não prometer leitura
universal de qualquer backup ou acesso automático ao sistema anterior.

### 1. Diagnóstico e escopo

Identificar ERP e versão, exportações ou API disponíveis, volume, período histórico e cadastros necessários.
O cliente define o responsável pela migração; dados fiscais e saldos são revisados com seu contador quando
pertinente. Definir data de corte, indisponibilidade aceitável e eventual carga incremental final.
Escolher entre histórico detalhado e saldos de abertura, evitando importar o mesmo efeito financeiro duas vezes.

Primeiro escopo proposto: fornecedores, contas a pagar em aberto e referências de origem.
Clientes, produtos, serviços, estoque, documentos fiscais e históricos liquidados entram quando seus módulos
de destino e suas regras existirem. Registros não suportados não serão descartados silenciosamente.

### 2. Extração e entrega segura

Preferir exportações documentadas CSV/XLSX e, posteriormente, conectores API com escopo mínimo.
Não solicitar senha pessoal do operador do ERP anterior. Não restaurar seu banco diretamente sobre o SDF:
estrutura, identificadores, regras e permissões são diferentes. Um dump proprietário exige diagnóstico próprio.
Credenciais, senhas e sessões antigas não são importadas; usuários recebem acesso por fluxo próprio.

Arquivos devem permanecer privados, vinculados à organização, com limites de tamanho/tipo, validação de
conteúdo, inspeção e retenção definida. Não executar macros, fórmulas ou scripts. Sanitizar exportações de
erros para evitar execução de fórmulas em planilhas. Não copiar valores sensíveis para logs.

### 3. Preparação, mapeamento e simulação

O cliente associa colunas da origem aos campos do SDF. Preservar identificador externo, lote, fonte e datas
de negócio, distinguindo-as da data de importação. Validar CNPJ/CPF quando aplicáveis, moedas, valores
decimais, datas, referências, vínculos e campos obrigatórios. Detectar duplicidades e conflitos sem fundir
entidades automaticamente. Exibir prévia, contagens e erros por linha, sem exposição entre empresas.

A carga de preparação não altera o financeiro oficial. Erros permanecem disponíveis para correção e nova
simulação. Toda informação importada é tratada como entrada não confiável, inclusive textos exibidos à IA.

### 4. Conciliação e aprovação

Comparar quantidades e totais por empresa, moeda, situação e data de corte: títulos abertos, vencidos,
valores originais, baixas, estornos e saldos. Informar exclusões e divergências, nunca somente o total de linhas.
Preservar a precisão decimal. Documentar como impostos, parcelas e saldos foram convertidos.
Exigir aprovação explícita do responsável autorizado antes da carga definitiva.

### 5. Gravação, corte e acompanhamento

Usar lotes versionados, idempotência, identificadores externos e transações para evitar duplicação em
retentativas. Importação não concede permissões nem executa pagamentos. Bloquear confirmação de lote
simulado sobre estado desatualizado. Fazer backup e validar recuperação antes do corte, com carga final
das alterações posteriores ao diagnóstico quando necessária. Conservar o legado para consulta pelo prazo definido.

Reverter somente lotes ainda reversíveis e sem dependências; movimentos consolidados exigem correção ou
compensação auditada. Nunca prometer um botão de desfazer que apague histórico financeiro utilizado.
Emitir relatório final com origem, responsável, datas, contagens, totais, diferenças e resultado da aprovação.

### Critérios do primeiro importador

- Só usuários autorizados importam para a organização e empresa efetivamente concedidas.
- Arquivo inválido não altera dados oficiais; erros são compreensíveis e rastreáveis.
- Reenvio de lote não duplica títulos e não muda permissões.
- Totais conciliados correspondem aos registros efetivamente gravados.
- Auditoria distingue origem, executor e aprovador; logs não contêm arquivos, documentos ou credenciais.
- Testes cobrem isolamento, duplicidade, precisão, falha parcial, retentativa e concorrência.

## Português e inglês

Preparar catálogos de tradução para navegação, formulários, validações, estados, ajuda, notificações e
relatórios; incluir mensagens vindas da API por códigos estáveis, sem expor exceções internas.
Persistir preferência do usuário de maneira apropriada. Testar expansão de textos e acessibilidade.
Idioma é independente de moeda, país, fuso e regime fiscal. Não traduzir nomes, documentos ou dados
originais da empresa automaticamente. Português continua sendo o idioma inicial; inglês será uma opção.

## Assinaturas propostas

Os nomes definidos são Essential, Professional e Enterprise. A distribuição abaixo é uma proposta de
escopo futuro; preços, cotas de usuários/empresas, armazenamento, IA e importação ainda serão definidos
com base em custos e uso. Funcionalidade planejada não pode ser vendida como implementada.

| Capacidade | Essential | Professional | Enterprise |
| --- | --- | --- | --- |
| Financeiro e cadastros do núcleo | Operação básica | Operação e análise ampliadas | Operação e análise ampliadas |
| Empresas e unidades | Escopo inicial | Gestão de múltiplas empresas/unidades | Limites e estrutura contratados |
| Importação | Modelos padronizados e conferência | Mapeamentos reutilizáveis e cargas recorrentes | Migração assistida e conectores contratados |
| Relatórios e oportunidades | Relatórios essenciais | Análises gerenciais e alertas de oportunidades | Consolidação e análises configuráveis |
| Processos | Fluxos padrão | Aprovações e automações configuráveis | Governança e integrações ampliadas |
| Tutorial e assistência | Tutorial e ajuda contextual | Assistente com consultas autorizadas | Assistente e fontes corporativas sob políticas contratadas |
| Atendimento | Padrão | Prioritário | Implantação assistida e condições contratadas |

Todos os planos mantêm isolamento, autorização, proteção de dados, MFA disponível, auditoria de segurança
e política básica de backup/recuperação. Segurança fundamental não é um adicional pago.
Segmentos são módulos habilitados explicitamente na organização; assinatura não libera dados ou permissões
por si só. Acesso exige simultaneamente recurso contratado, módulo habilitado e autorização do usuário.
Cobrança e limites precisam ser aplicados no backend, com contadores consistentes e tratamento de concorrência.
Downgrade não deve apagar dados nem permitir perda silenciosa de acesso a registros obrigatórios.

## Tutorial e assistente interno

Começar com ajuda contextual e jornadas orientadas por tarefa: primeiro acesso, empresa, usuários,
lançamento financeiro e migração. Respeitar permissões e permitir retomar ou dispensar o tutorial.

A IA virá depois, inicialmente para explicar o produto e consultar dados autorizados em modo de leitura.
Ela utiliza as mesmas verificações de tenant, empresa, módulo e operação do backend; não recebe credencial
de banco irrestrita. Conteúdo importado não pode alterar instruções ou autorizações do assistente.
Respostas sobre dados apontam fontes e período; recomendações não representam fatos confirmados nem
resultados financeiros garantidos. Não executar pagamentos, tributos, concessões ou mudanças de cadastro
automaticamente. Qualquer ferramenta de escrita futura exige escopo, confirmação e auditoria próprios.
Definir modelo/provedor, retenção, custos e condições de envio antes de transmitir dados a serviços externos.

## Fiscal por país: etapa posterior

Separar idioma da localização fiscal. Preparar fronteiras para regras por país, jurisdição, regime,
atividade e vigência, com versionamento e validação especializada. Regras de um país não substituem as de
outro nem são escolhidas somente pelo idioma ou pelo segmento. Nenhum pacote fiscal internacional está
implementado ou habilitado neste momento.

## Ordem de execução proposta

1. Fechar abertura validada da empresa e atribuição do primeiro Master; habilitar e-mail quando houver decisão de provedor.
2. Detalhar contrato de importação e implementar um lote piloto de fornecedores/contas a pagar, com simulação e conciliação.
3. Formalizar os limites do núcleo e dos segmentos, incluindo habilitação de módulos e permissões.
4. Introduzir internacionalização e entregar português/inglês nas telas existentes, antes de ampliar muito a interface.
5. Validar a matriz comercial e implementar direitos de uso de Essential, Professional e Enterprise.
6. Entregar tutorial contextual; depois integrar IA com escopo de leitura e dados autorizados.
7. Expandir módulos setoriais individualmente e, posteriormente, localização fiscal para outros países.

Cada etapa terá critérios de aceite próprios e testes de segurança. A ordem pode ser ajustada por dependências,
sem misturar migração técnica do banco (Alembic) com migração dos dados de clientes vindos de outro ERP.
