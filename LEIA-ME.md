# Inventário com QR codes

## Arrancar
1. `pip install flask segno` (só uma vez)
2. `python app.py` (ou ▶ no VS Code). O navegador abre sozinho.
3. Clica em **Entrar** e usa o utilizador **admin** com a palavra-passe **1234**. No primeiro acesso, o sistema obriga a mudá-la (mínimo 8 caracteres).

## Contas e perfis
- As contas são criadas pelo **administrador** (menu **Utilizadores**), não há registo livre. Ao criar, o sistema mostra uma palavra-passe temporária (só aparece uma vez) que a pessoa tem de mudar no primeiro acesso.
- **Consulta**: vê as fichas completas. **Técnico**: também atualiza estados, cria equipamentos e imprime etiquetas. **Administrador**: tudo, mais utilizadores e painel.
- O histórico regista automaticamente quem fez cada alteração.
- Quem lê um QR sem entrar vê só o tipo, o código e o estado.
- 5 tentativas falhadas bloqueiam o login durante 10 minutos.
- Esqueceste a palavra-passe do admin? Cria um ficheiro vazio `repor-admin.txt` ao lado do `app.py` e reinicia: fica admin / 1234 (será preciso mudar de novo).

## Estrutura do projeto
- `app.py`: lógica (rotas, base de dados, contas).
- `templates/`: uma página HTML por ecrã (`base.html` tem a barra lateral e a de baixo).
- `static/style.css` e `static/app.js`: aparência e o menu "Mais".
Para mudar o visual, mexe só em `templates/` e `static/style.css`. As três têm de seguir juntas para o servidor (com Git vai tudo no `git pull`).

## Usar
- **+ Novo**: adiciona equipamentos (o código EQ-00001, EQ-00002… é automático).
- **Etiquetas**: imprime os QR codes. Cada um abre a ficha do equipamento.
- Na ficha, o técnico (com PIN) muda estado, local e responsável e escreve notas. Fica tudo no histórico.
- **Painel**: totais por estado, manutenções em atraso, equipamentos mais antigos, os que mais avariam.

## Telemóveis
Têm de estar no mesmo Wi-Fi. O endereço aparece na janela ao arrancar. Se o IP do PC mudar, os QR já impressos deixam de funcionar: dá um IP fixo ao PC, ou cria `endereco.txt` com o endereço (ex.: `http://192.168.1.10:5000`).

## Programa de duplo clique (Windows)
Corre `criar_executavel.bat` uma vez. Fica `dist\Inventario.exe`, que não precisa de instalar nada.

## Dados
Tudo fica no ficheiro `inventario.db`, ao lado do programa. Para cópia de segurança, copia esse ficheiro.
