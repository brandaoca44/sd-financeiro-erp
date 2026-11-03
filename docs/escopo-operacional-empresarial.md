# Escopo operacional — Empresarial/Serviços

Requisitos de produto definidos para implementação gradual. A base atual de contas a pagar permite
títulos, baixas manuais, estornos e resumo por empresa; os cadastros e fluxos adicionais deste documento
estão planejados. A distribuição comercial está em [Planos Empresarial/Serviços](planos-empresarial-servicos.md).

## Organização da interface

Cada área terá nome explícito, navegação própria e permissões específicas. Clientes, fornecedores,
produtos, serviços, funcionários, documentos fiscais e movimentos financeiros são entidades distintas.
O usuário só verá áreas contratadas e autorizadas. A proposta de navegação é:

| Área | Páginas e finalidade |
| --- | --- |
| Visão geral | Indicadores, pendências, alertas e atalhos autorizados |
| Cadastros | Clientes, fornecedores, produtos, serviços, categorias e centros de custo |
| Financeiro | Contas a pagar, contas a receber, pagamentos, recebimentos e fluxo de caixa |
| Despesas | Gastos organizados por natureza, fornecedor, competência, vencimento e centro de custo |
| Comercial e serviços | Vendas, prestação de serviços, contratos, recorrências e faturamento |
| Fiscal | Notas de entrada/saída, documentos, enquadramento, obrigações e conferências |
| Pessoas e custos | Funcionários, vínculos, remuneração informada, benefícios e despesas de pessoal |
| Gestão e resultados | Receitas, despesas, resultado gerencial, orçamento e oportunidades |
| Administração | Empresas, usuários, acessos, assinatura, importações e configurações |

Uma página pode apresentar uma visão filtrada de registros de outra área sem duplicá-los. Exemplo:
"Despesas de internet" consulta os mesmos lançamentos financeiros da empresa, sem criar outro livro de gastos.

## Despesas facilmente identificáveis

Categorias iniciais sugeridas, adaptáveis pela empresa e com códigos estáveis. Não impor uma classificação
contábil universal: relacionamentos contábeis e fiscais serão configurados e validados no contexto aplicável.

| Grupo | Categorias visíveis |
| --- | --- |
| Imóvel e ocupação | Aluguel, condomínio, IPTU, seguros do imóvel e manutenção predial |
| Água e saneamento | Água, esgoto e serviços relacionados |
| Energia | Energia elétrica e outras fontes de energia utilizadas pela operação |
| Comunicação | Internet, telefonia fixa, telefonia móvel e comunicação corporativa |
| Tecnologia | Software, assinaturas, hospedagem, nuvem, equipamentos e suporte técnico |
| Pessoal | Salários, pró-labore separado de empregados, benefícios, encargos informados, horas extras, férias, 13º, rescisões e reembolsos |
| Serviços contratados | Contabilidade, jurídico, consultorias, terceirizados, limpeza, segurança e outros prestadores |
| Operação | Materiais de consumo, insumos, manutenção de equipamentos e despesas administrativas |
| Transporte e viagens | Combustível, frete, transporte, estacionamento, hospedagem e deslocamentos |
| Comercial | Publicidade, marketing, comissões e despesas de vendas |
| Financeiras | Tarifas, juros, multas e custos financeiros identificados separadamente |
| Tributos e obrigações | Impostos, taxas e contribuições informados e vinculados à obrigação correspondente |
| Outras despesas | Categorias adicionais configuráveis, sem agrupar toda a operação em "Outros" |

Em cada despesa, prever descrição, empresa, categoria, contraparte, valor, moeda, competência, vencimento,
situação, centro de custo quando aplicável e vínculos documentais. Campos variam conforme o tipo de registro;
não exigir documento fiscal onde ele não se aplica. Separar valor original, juros, multa, desconto e valor pago.
Despesas previstas, obrigações assumidas e pagamentos efetuados precisam de identificação visual distinta.

Aluguel, água, luz, internet e demais despesas podem ser lançados manualmente no Essential. No Professional,
recorrências configuradas poderão gerar propostas de lançamentos, com conferência; contas de consumo
variável não devem repetir silenciosamente o valor anterior como se fosse confirmado. Orçamento e variação
de consumo/preço devem ficar separados do valor efetivamente documentado. Nenhuma recorrência paga contas.

## Boletos, notas e títulos

- **Nota fiscal:** documento vinculado à compra ou prestação, com emitente, destinatário, identificação,
  datas, itens/serviços, valores e estado documental apropriados. Distinguir entrada de fornecedor e saída
  para cliente. Cadastro e anexação não significam emissão, autorização fiscal ou validação de autenticidade.
- **Conta a pagar/receber:** obrigação financeira, possivelmente parcelada, com saldo derivado de movimentos.
- **Boleto a pagar:** instrumento associado a uma obrigação, com beneficiário, vencimento, valor e referência;
  tratar linha digitável/código como dados restritos. Validação sintática não confirma legitimidade do beneficiário.
- **Pagamento/recebimento:** movimento financeiro efetivo informado ou conciliado por integração futura.

Uma nota pode originar várias parcelas; uma parcela pode receber um instrumento de cobrança substituto.
Nota, boleto e parcela não são três gastos. Impedir duplicação por reimportação, associação e retentativa.
Anexos precisam de armazenamento privado, validação/inspeção e autorização por objeto antes de serem aceitos.
Emissão de boletos para clientes e pagamento bancário são integrações futuras, distintas de cadastrar um boleto.

## Alertas de vencimento

Prever central de alertas no sistema para boletos/títulos próximos do vencimento, vencendo hoje e vencidos,
com antecedências configuráveis. Começar pela exibição interna; e-mail e outros canais só após configuração
e implementação próprias. Não alegar que mensagem foi enviada quando o canal estiver desativado.

Recalcular a situação a partir do saldo e do estado atual: pago, cancelado ou substituído deixa de gerar
alerta indevido; estorno pode reabrir a obrigação. Tratar pagamentos parciais, fuso/data da empresa, deduplicação
e preferências do destinatário. Revalidar acesso na geração e entrega, sem expor dados na prévia de mensagens.
Marcar alerta como lido não baixa uma dívida. Notificação não executa pagamento.

## Clientes, fornecedores, produtos e serviços

Manter páginas separadas, com busca, filtros, situação ativa/inativa e histórico relevante. Cliente pode
também ser fornecedor, com papéis vinculados sem misturar contas a pagar e receber. Definir no cadastro
de clientes os tipos de destinatário permitidos pela operação; o contratante do ERP continua sendo pessoa jurídica.

Produto é item material; serviço é uma prestação. Catálogo de produtos acessórios não habilita automaticamente
estoque, PDV, fabricação ou o segmento Varejo. Estes exigem seus próprios módulos e contratos. Referências
utilizadas em documentos históricos não podem mudar retroativamente ao editar preços ou descrições do catálogo.

## Faturamento, receita e resultado

Faturamento, receita reconhecida, recebimentos, despesas, custos e caixa precisam de indicadores e fontes
distintos. Emitir um documento não significa receber seu valor. Apuração de resultado gerencial precisa
de critério documentado, competência, tratamento de cancelamentos/devoluções e integração dos custos,
inclusive pessoal e despesas operacionais, sem dupla contagem. Não chamar o resumo de contas a pagar de lucro.

Planejar resumo básico no Essential; Professional acrescenta orçamento, projeções, comparação de períodos,
centros de custo e oportunidades; Enterprise amplia consolidação e governança contratadas. Identificar
dados incompletos e projeções. Resultado gerencial não substitui demonstração contábil formal validada.

## Funcionários e despesas de pessoal

Funcionário é cadastro de pessoa/vínculo de trabalho, diferente de usuário do ERP: não precisa consumir
uma licença de acesso apenas por estar cadastrado. A contagem de colaboradores e a de usuários autorizados
serão dimensões distintas. O cadastro não concede login nem permissões automaticamente.

Prever dados mínimos do vínculo, departamento, centro de custo e custos informados: remuneração,
benefícios, encargos, reembolsos e demais rubricas relevantes, distinguindo previsto e realizado.
Somente usuários com permissão específica acessam dados e valores de pessoal; acesso genérico ao financeiro
não libera ficha individual ou documento do funcionário. Relatórios agregados também precisam de escopo adequado.

Primeiro incremento: registro gerencial de custos informados. Cálculo de folha, encargos, férias, rescisões,
obrigações trabalhistas e integrações de folha dependem de módulos específicos, regras versionadas e validação
especializada. Não oferecer cálculo legal completo a partir de somas genéricas de salários.

## Sequência funcional após a base comercial

1. Clientes/fornecedores, categorias e centros de custo com autorização por empresa.
2. Despesas identificadas por categoria, boletos vinculados a títulos e alertas internos de vencimento.
3. Notas de fornecedor e seus vínculos financeiros, com ingestão segura de documentos quando habilitada.
4. Produtos/serviços, contas a receber, documentos de cliente e faturamento.
5. Receitas, custos, caixa e resultado gerencial com conciliação das fontes.
6. Funcionários e custos informados de pessoal, com permissões específicas.
7. Recorrências, aprovações, projeções, oportunidades e integrações conforme os planos contratados.

Reavaliar prioridades por dependências sem misturar este escopo com implementação concluída. Cada entrega
deve testar isolamento, permissões, recursos contratados, integridade e ausência de duplicação financeira.
