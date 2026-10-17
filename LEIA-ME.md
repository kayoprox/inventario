# Inventário com QR codes

## Arrancar
1. `pip install flask segno` (só uma vez)
2. `python app.py` (ou ▶ no VS Code). O navegador abre sozinho.
3. Clica em **Entrar** e usa o PIN **1234**.

## PIN
- PIN inicial: **1234**.
- Para mudar: **Entrar → Mudar PIN** (pede o PIN atual e o novo duas vezes).
- Esqueceste o PIN? Cria um ficheiro vazio chamado `repor-pin.txt` ao lado do `app.py` e reinicia: o PIN volta a 1234.

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
