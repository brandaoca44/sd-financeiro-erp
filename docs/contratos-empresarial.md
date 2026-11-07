# Contratos Empresarial

A migration e81b346c9a10 cria um contrato Empresarial por organização e uma
lista de empresas habilitadas. A chave estrangeira composta impede vincular
empresas de outro tenant. Configure o contrato pelo terminal com credenciais administrativas do banco.
Após aplicar a migração, execute na pasta backend:

```powershell
.venv/Scripts/python.exe -m ops.configure_business_contract --organization UUID_DA_ORGANIZACAO --plan ESSENTIAL --valid-from 2026-11-02T00:00:00-03:00 --valid-until 2027-11-02T00:00:00-03:00 --company UUID_DA_EMPRESA
```

O comando grava o contrato como ACTIVE e substitui a lista de empresas
habilitadas. Repita --company para cada empresa que deve permanecer habilitada.
Para Enterprise, informe --enterprise-company-limit com o limite negociado.
A vigência inclui o início e exclui o fim. Para suspender o acesso financeiro,
altere o estado para SUSPENDED em uma transação administrativa.
A migration não atribui contratos
a empresas existentes.

Contas a pagar e a lista de empresas do financeiro exigem contrato ativo e
vigente, habilitação da empresa e permissão do usuário para a operação.
As escritas bloqueiam o contrato e a habilitação durante a transação.
A gestão por interface, cobrança e reserva de cotas seguem como etapas próprias.

## Fornecedores e despesas

Em **Financeiro → Despesas**, quem pode gerenciar títulos pode cadastrar um fornecedor
pelo nome e selecioná-lo em novas despesas. O vínculo é restrito à empresa selecionada.
As despesas antigas continuam exibindo o nome registrado originalmente.

## Clientes vinculados ao faturamento

Em Financeiro → Faturamento → Clientes, o Master cadastra o nome ou a razão social
do cliente na empresa selecionada. Novos faturamentos usam esse cadastro. O nome
no faturamento representa o cliente no momento do registro.

O vínculo usa uma chave composta por organização, empresa e cliente. O backend
bloqueia referências a clientes de outra empresa. Os lançamentos anteriores
continuam disponíveis com o nome informado originalmente, sem vínculo inferido.
O reenvio do mesmo cadastro ou faturamento reutiliza a chave de idempotência.

O cadastro inicial contém o nome. Documentos, contatos e endereço do cliente
ainda não fazem parte deste fluxo.

## Resultado por competência

A Visão financeira apresenta um resumo mensal disponível ao Master da organização.
O faturamento usa a competência do serviço. Despesas novas informam uma competência
própria, independente de emissão, vencimento e pagamento.

O resultado gerencial parcial corresponde ao faturamento bruto menos as despesas
da competência. Valores positivos aparecem como lucro parcial e valores negativos,
como prejuízo parcial. Sem registros, a tela indica ausência de movimento.

Despesas com títulos cancelados são excluídas. Para títulos ativos vinculados,
o cálculo usa o valor vigente do título. Baixas e recebimentos não mudam o mês
de competência e não são somados novamente ao resultado.

As despesas anteriores continuam sem competência quando essa informação não foi
registrada. Não se presume a competência pela emissão. O painel conta essas
pendências e os títulos ativos sem despesa vinculada em toda a empresa, separadamente
dos valores do mês. Esses registros ficam fora da apuração.

A apuração permanece parcial enquanto folha, tributos, deduções e custos não
estiverem integrados e conferidos. O indicador não representa fechamento contábil.
As agregações usam valores decimais e um único snapshot SQL autorizado por empresa.

## Minha conta e chave Pix

Em Configurações → Minha conta, cada usuário consulta e completa o próprio perfil.
A página reúne identificação, documentos, endereço, celular, dados bancários e
chave Pix. O e-mail de acesso é exibido para consulta. O CPF já registrado fica
protegido contra alteração por esse formulário. O primeiro registro usa a mesma
validação e unicidade da identidade da conta.

Salvar exige a senha atual e a revisão carregada do perfil. Alterações concorrentes
exigem recarregamento. Os dados complementares são criptografados no armazenamento,
com vínculo ao identificador do usuário. As respostas usam Cache-Control: no-store.

No cadastro e edição de colaboradores, o bloco Chave Pix aceita CPF, CNPJ, e-mail,
telefone internacional com + e chave aleatória. Tipo e chave devem ser informados
juntos. Os dados são armazenados no bloco privado criptografado do colaborador,
sob as permissões já aplicadas ao módulo Pessoas.

## Seletor de bancos e passaporte

Minha conta e Colaboradores usam um seletor de instituições com busca por nome ou
código. O catálogo local deriva da lista pública de participantes do STR do Banco
Central. Inclui as instituições dessa lista, inclusive instituições de origem
estrangeira participantes do sistema brasileiro. A opção de banco internacional
ou não listado permite registrar nome e país e preserva valores antigos.

Fonte e atribuição: Banco Central do Brasil, Lista de Participantes do STR.
https://dadosabertos.bcb.gov.br/dataset/lista-de-participantes-do-str
Catálogo derivado disponibilizado sob ODbL 1.0, conforme a licença da fonte.
https://opendatacommons.org/licenses/odbl/1-0/

A atualização é feita por backend/ops/update_bank_catalog.py, que valida o arquivo
público antes de substituir frontend/public/catalog/banks.json. A data da cópia
é apresentada no seletor. A busca ocorre localmente, sem enviar dados pessoais
à instituição de origem. A lista não constitui um cadastro mundial de bancos.

Passaporte permanece opcional e aceita numeração alfanumérica, convertida para
maiúsculas no novo cadastro ou edição. Símbolos e valores contendo somente letras
são rejeitados. O formato brasileiro contém duas letras e seis números, conforme
a orientação da Polícia Federal.
https://www.gov.br/pf/pt-br/assuntos/passaporte/ajuda/duvidas_/caderneta/caderneta-numero-onde-fica-e


A geração mensal das regras e a revisão das cobranças variáveis estão descritas em
[Despesas recorrentes](despesas-recorrentes.md).


A correção dos lançamentos e as restrições para despesas pagas estão em
[Edição e cancelamento de despesas](edicao-despesas.md).

As concessões de Faturamento e Pessoas são independentes das de Contas a pagar. Consulte [Permissões operacionais por empresa](permissoes-operacionais.md) para as ações disponíveis e a proteção de documentos, remuneração e dados bancários.

O [Fluxo de caixa consolidado](fluxo-caixa.md) está disponível no catálogo Empresarial e exige leitura das duas áreas financeiras na mesma empresa.
