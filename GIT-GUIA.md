# Guia de Git (projeto em desenvolvimento)

## A ideia
- **`main`** = a versão que está online. Tem de funcionar sempre.
- Cada novidade faz-se num **ramo à parte** (ex.: `campo-garantia`), testada no PC. Só se junta ao `main` quando funciona.
- Os dados (`inventario.db`) e a configuração do servidor (`endereco.txt`) **nunca** vão para o Git (estão no `.gitignore`).

## Preparar (uma só vez)
1. Instala o Git (git-scm.com) e cria uma conta em github.com.
2. No GitHub, cria um repositório vazio chamado `inventario` (sem README).
3. No terminal do VS Code, dentro da pasta do projeto:
   ```
   git init
   git add .
   git commit -m "Primeira versão"
   git branch -M main
   git remote add origin https://github.com/O_TEU_UTILIZADOR/inventario.git
   git push -u origin main
   ```
   Confirma que o `inventario.db` NÃO aparece no repositório do GitHub.
4. No PythonAnywhere, numa consola Bash (os ficheiros `inventario.db` e `endereco.txt` mantêm-se, porque não estão no Git):
   ```
   cd ~/Inventario
   git init
   git remote add origin https://github.com/O_TEU_UTILIZADOR/inventario.git
   git fetch origin
   git checkout -f -B main origin/main
   ```
   Depois, separador **Web → Reload**.

## Rotina para cada novidade
1. Cria um ramo: `git switch -c nome-da-novidade`
2. Edita o `app.py` e testa no PC (▶ no VS Code).
3. Guarda uma versão: `git add .` e `git commit -m "o que mudou"` (podes fazer vários).
4. Quando funcionar: `git switch main`, `git merge nome-da-novidade`, `git push`.
5. **Cópia de segurança:** descarrega o `inventario.db` do servidor (separador Files).
6. No PythonAnywhere: `cd ~/Inventario && git pull`, depois **Reload**.

## Se uma atualização correr mal
No PC: `git revert HEAD` (cria uma versão que desfaz a última), depois `git push`; no servidor `git pull` e Reload. Isto só mexe no código, nunca nos dados.

## Mudar a base de dados (importante)
A base do servidor já tem dados reais, e o programa não altera tabelas existentes sozinho. Para acrescentar um campo, junta uma linha **no fim** da lista `MIGRACOES` do `app.py`, por exemplo:
```python
MIGRACOES = [
    "ALTER TABLE equipamento ADD COLUMN garantia_ate TEXT",
]
```
É aplicada uma só vez, automaticamente, quando a aplicação arranca com o código novo. **Nunca edites nem apagues linhas antigas.** Remover ou renomear campos é mais delicado: pede ajuda antes.

## Notas
- O repositório pode ser público sem expor dados nem palavras-passe (ficam na base de dados). Atenção: o administrador inicial é `admin` / `1234`, visível no código, por isso muda a palavra-passe no primeiro acesso. Repositório privado também funciona, mas exige um token de acesso no servidor.
- Se o `git fetch`/`git pull` falhar com erro de rede no PythonAnywhere gratuito, usa o upload manual do `app.py` e Reload. Não verifiquei se o plano gratuito consegue aceder ao GitHub.
