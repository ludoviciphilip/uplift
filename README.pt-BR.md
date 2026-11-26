# Uplift

**Gerenciador open-source de upscaling e geração de quadros para jogos da Steam no Linux: escolhido por jogo, aplicado e desfeito com um clique.**

[![Licença: MIT](https://img.shields.io/github/license/ludoviciphilip/uplift)](LICENSE)
[![Plataforma: Linux](https://img.shields.io/badge/plataforma-linux-informational)](#instala%C3%A7%C3%A3o)

[English](README.md) · [Recursos](#recursos) · [Instalação](#instalação) · [Uso](#uso) · [Alternativas](#alternativas--comparação)

![Janela do Uplift](docs/screenshot-gui.png)

O Uplift lê sua biblioteca da Steam, examina cada jogo instalado (motor, API gráfica, upscalers que o jogo já traz, anticheat) e configura o melhor caminho de upscaling que aquele jogo suporta:

## Recursos

| O jogo tem… | O Uplift faz | Qualidade |
|---|---|---|
| DLSS, XeSS ou FSR 2/3 | Instala o **[OptiScaler](https://github.com/optiscaler/OptiScaler)** e troca por **FSR 3.1** (funciona em qualquer placa) | Upscaling temporal de verdade |
| Unreal Engine 4/5 sem upscaler no menu | Liga o **TAAU (UE4) / TSR (UE5)** do próprio motor pelo `Engine.ini` | Temporal, perto do FSR 2 |
| Nada | **gamescope + FSR 1 ou NIS** na resolução que você escolher, com a nitidez ajustada | Espacial |
| Qualquer um acima | Opcionais: nitidez **CAS do vkBasalt**, geração de quadros **lsfg-vk** (Lossless Scaling), GameMode, MangoHud | |

Ele também grava as **opções de inicialização** da Steam. Como a Steam reescreve esse arquivo enquanto está aberta, o Uplift fecha a Steam, grava e abre de novo. As suas opções são mantidas (variáveis, wrappers, argumentos do jogo), e erros comuns são corrigidos (`%%command`, `gamemode` no lugar de `gamemoderun`).

Tudo é registrado e **reversível**: arquivos adicionados são removidos, arquivos substituídos têm backup, as chaves do `Engine.ini` voltam ao valor anterior e as opções de inicialização voltam a ser exatamente o que eram.

## Instalação

```bash
git clone https://github.com/ludoviciphilip/uplift
cd uplift && ./install.sh
```

Precisa de Python 3.10+.

O `./install.sh` oferece instalar as ferramentas que o Uplift usa (gamescope, MangoHud, GameMode, vkBasalt, lsfg-vk, GTK/Textual) com o gerenciador de pacotes da sua distro: Arch (+AUR via paru/yay), Debian/Ubuntu, Fedora, openSUSE. `--deps` instala sem perguntar, `--no-deps` pula. O **Lossless Scaling** (exigido pelo lsfg-vk) é pago na Steam: instale e escolha o beta `lsfg-vk`.

## Uso

- `uplift`: janela. Escolha o jogo, ajuste, **Aplicar** / **Desfazer**
- `uplift --tui`: o mesmo no terminal (`a` aplica, `u` desfaz, `/` busca)
- Linha de comando, para scripts:

```bash
uplift list                                   # biblioteca + recomendação por jogo
uplift show "escape the backrooms"            # detecção + plano
uplift plan 374320 --method gamescope-fsr --quality quality --lsfg x2-perf   # simulação
uplift apply 374320 --lsfg x2-perf -y         # aplica (reinicia a Steam se estiver aberta)
uplift undo 374320 -y
uplift doctor                                 # ferramentas, monitores, placa de vídeo
```

## Observações

- **O caminho do OptiScaler é experimental**: testado de ponta a ponta numa biblioteca sintética (instalar → reaplicar → desfazer idêntico byte a byte), ainda não em muitos jogos reais com DLSS/FSR2. Relatos são bem-vindos!
- **Anticheat** (EasyAntiCheat, BattlEye…): o Uplift nunca coloca DLLs nesses jogos.
- **OptiScaler em NVIDIA GTX** com jogos que só têm DLSS é experimental (spoof de GPU + fakenvapi). Jogos com FSR 2/XeSS funcionam sem isso.
- **Unreal**: abra o jogo uma vez para ele criar a pasta de configuração.
- **lsfg-vk**: o Uplift trava o jogo em taxa do monitor ÷ multiplicador (`DXVK_FRAME_RATE`/`VKD3D_FRAME_RATE`), para os quadros gerados caírem no ritmo da tela.
- O Uplift não redistribui o OptiScaler: baixa a versão oficial do GitHub.

## Alternativas / comparação

- **vs. instalar o [OptiScaler](https://github.com/optiscaler/OptiScaler) manualmente**: o Uplift detecta, por jogo, se dá para trocar DLSS/FSR2/XeSS por FSR 3.1 e faz a cópia de arquivos + configuração para você, com desfazer de um clique (o OptiScaler faz o upscaling; o Uplift automatiza a configuração).
- **vs. a geração de quadros do próprio [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/)**: o Uplift usa o [lsfg-vk](https://github.com/PancakeTAS/lsfg-vk), uma camada Vulkan open-source que leva a geração de quadros do Lossless Scaling para jogos nativos/Proton no Linux, limitando a taxa do jogo para os quadros gerados caírem no ritmo da tela. O Lossless Scaling continua sendo necessário (fornece a DLL de geração de quadros que o lsfg-vk carrega).
- **vs. editar `Engine.ini` ou as opções de inicialização da Steam na mão**: o Uplift encontra as chaves/flags certas para TSR/TAAU do Unreal e para o gamescope, grava com segurança (o arquivo de opções de inicialização da Steam é reescrito enquanto ela roda, então o Uplift fecha/grava/reabre por você) e reverte tudo com `uplift undo`.

### Aviso de marcas registradas

NVIDIA DLSS, AMD FSR e Intel XeSS são marcas registradas de seus respectivos donos. Lossless Scaling é marca registrada de sua desenvolvedora/publicadora, THS. Unreal Engine é marca registrada da Epic Games. O Uplift é um projeto independente e open-source, sem afiliação, patrocínio ou endosso da NVIDIA, AMD, Intel, THS, Epic Games ou Valve.

## Licença

MIT
