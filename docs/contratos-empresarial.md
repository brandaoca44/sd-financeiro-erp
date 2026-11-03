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
