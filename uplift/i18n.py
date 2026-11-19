"""Tiny i18n: English + Brazilian Portuguese, picked from LANG/LC_* (UPLIFT_LANG overrides)."""
from __future__ import annotations

import locale
import os

EN = {
    "app_title": "Uplift",
    "app_subtitle": "Better upscaling and frame generation for your Steam games",
    "search": "Search games",
    "no_steam": "Steam was not found.",
    "no_games": "No installed games found.",
    "detected": "Detected",
    "engine": "Engine", "api": "Graphics API", "platform": "Platform", "upscalers": "Built-in upscalers",
    "anticheat": "Anti-cheat", "proton": "Compatibility tool", "none": "none", "unknown": "unknown",
    "native_linux": "Native Linux", "windows_proton": "Windows (Proton)",
    "upscaling": "Upscaling", "method": "Method", "quality": "Render resolution", "sharpness": "Sharpness",
    "monitor": "Monitor",
    "extras": "Extras", "cas": "Extra sharpening (vkBasalt CAS)", "cas_sub": "Press Home in game to toggle",
    "framegen": "Frame generation (lsfg-vk)", "framegen_sub": "Lossless Scaling's frame generation",
    "gamemode": "GameMode", "gamemode_sub": "CPU performance mode while playing",
    "mangohud": "MangoHud", "mangohud_sub": "FPS / frame-time overlay",
    "launch_preview": "Launch options", "apply": "Apply", "undo": "Undo", "applied_badge": "Applied",
    "recommended": "recommended",
    "m_auto": "Automatic", "m_off": "Off", "m_unreal": "Unreal Engine temporal upscaling (TAAU / TSR)",
    "m_optiscaler": "OptiScaler → FSR 3.1", "m_gamescope-fsr": "gamescope + FSR 1",
    "m_gamescope-nis": "gamescope + NVIDIA Image Scaling", "m_wine-fsr": "Proton-GE FSR 1",
    "q_native": "Native (100%)", "q_ultra": "Ultra quality (77%)", "q_quality": "Quality (67%)",
    "q_balanced": "Balanced (58%)", "q_performance": "Performance (50%)",
    "fg_off": "Off", "fg_x2": "2× (quality)", "fg_x2-perf": "2× (performance)", "fg_x3": "3× (performance)",
    "restart_title": "Steam will restart",
    "restart_body": "Steam keeps launch options in a file it rewrites while open, so Uplift closes Steam, "
                    "saves the options and opens it again. Continue?",
    "continue": "Continue", "cancel": "Cancel", "done": "Done", "working": "Applying…",
    "undone": "Restored", "error": "Error",
    "step_unreal": "Engine.ini: {algo} at {pct}% of the resolution, reconstructed to native",
    "step_optiscaler": "OptiScaler as {dll} in the game folder (replaces {inputs} with FSR 3.1)",
    "step_gamescope": "gamescope renders {w}×{h} and upscales with {filter} to {W}×{H}",
    "step_winefsr": "Proton-GE FSR 1: pick {w}×{h} (or similar) in the game's settings, fullscreen",
    "step_cas": "vkBasalt CAS sharpening ({s:.2f})",
    "step_lsfg": "lsfg-vk {mult}×: game capped at {cap} fps → {out} fps shown",
    "warn_anticheat": "Anti-cheat ({names}): Uplift won't inject DLLs into this game",
    "warn_opengl": "OpenGL game: Vulkan layers (vkBasalt, lsfg-vk) won't work",
    "warn_need_vkbasalt": "vkBasalt is not installed",
    "warn_need_lsfg": "lsfg-vk is not installed",
    "warn_need_lossless": "Lossless Scaling (Steam) is not installed — lsfg-vk needs it",
    "warn_lsfg_branch": "Lossless Scaling: switch to the 'lsfg-vk' beta branch in Steam (Properties → Betas)",
    "warn_winefsr_ge": "This only works with GE-Proton (set it in the game's Compatibility tab)",
    "warn_dlss_gtx": "DLSS-only game on a non-RTX NVIDIA card: experimental (GPU spoofing + fakenvapi)",
    "blocked_anticheat": "Blocked: anti-cheat present",
    "blocked_unreal_run_once": "Run the game once so it creates its config, then come back",
    "blocked_no_exe": "Couldn't find the game's executable",
    "blocked_proxy_taken": "All proxy DLL names are taken (ReShade/other mods?)",
    "blocked_need_gamescope": "gamescope is not installed",
    "fix_command_typo": "Fixed a typo in %command%",
    "fix_gamemode": "'gamemode' → 'gamemoderun'",
    "tools": "Tools", "missing_tools": "Optional tools missing: {names}",
    "install_hint": "Install: {cmd}",
}

PT = {
    "app_subtitle": "Upscaling e geração de quadros melhores para seus jogos da Steam",
    "search": "Buscar jogos",
    "no_steam": "A Steam não foi encontrada.",
    "no_games": "Nenhum jogo instalado encontrado.",
    "detected": "Detectado",
    "engine": "Motor", "api": "API gráfica", "platform": "Plataforma", "upscalers": "Upscalers do jogo",
    "anticheat": "Anticheat", "proton": "Ferramenta de compatibilidade", "none": "nenhum",
    "unknown": "desconhecido", "native_linux": "Linux nativo", "windows_proton": "Windows (Proton)",
    "upscaling": "Upscaling", "method": "Método", "quality": "Resolução de renderização", "sharpness": "Nitidez",
    "monitor": "Monitor",
    "extras": "Extras", "cas": "Nitidez extra (vkBasalt CAS)", "cas_sub": "Home no jogo liga/desliga",
    "framegen": "Geração de quadros (lsfg-vk)", "framegen_sub": "A geração de quadros do Lossless Scaling",
    "gamemode": "GameMode", "gamemode_sub": "Modo desempenho do processador durante o jogo",
    "mangohud": "MangoHud", "mangohud_sub": "FPS e tempo de quadro na tela",
    "launch_preview": "Opções de inicialização", "apply": "Aplicar", "undo": "Desfazer", "applied_badge": "Aplicado",
    "recommended": "recomendado",
    "m_auto": "Automático", "m_off": "Desligado", "m_unreal": "Upscale temporal da Unreal (TAAU / TSR)",
    "m_optiscaler": "OptiScaler → FSR 3.1", "m_gamescope-fsr": "gamescope + FSR 1",
    "m_gamescope-nis": "gamescope + NVIDIA Image Scaling", "m_wine-fsr": "FSR 1 do Proton-GE",
    "q_native": "Nativa (100%)", "q_ultra": "Ultra qualidade (77%)", "q_quality": "Qualidade (67%)",
    "q_balanced": "Equilibrado (58%)", "q_performance": "Desempenho (50%)",
    "fg_off": "Desligada", "fg_x2": "2× (qualidade)", "fg_x2-perf": "2× (desempenho)", "fg_x3": "3× (desempenho)",
    "restart_title": "A Steam vai reiniciar",
    "restart_body": "A Steam guarda as opções de inicialização num arquivo que ela reescreve enquanto está "
                    "aberta. O Uplift fecha a Steam, grava as opções e abre de novo. Continuar?",
    "continue": "Continuar", "cancel": "Cancelar", "done": "Pronto", "working": "Aplicando…",
    "undone": "Restaurado", "error": "Erro",
    "step_unreal": "Engine.ini: {algo} em {pct}% da resolução, reconstruído para a nativa",
    "step_optiscaler": "OptiScaler como {dll} na pasta do jogo (troca {inputs} por FSR 3.1)",
    "step_gamescope": "gamescope renderiza {w}×{h} e aumenta com {filter} para {W}×{H}",
    "step_winefsr": "FSR 1 do Proton-GE: escolha {w}×{h} (ou parecida) no jogo, em tela cheia",
    "step_cas": "Nitidez CAS do vkBasalt ({s:.2f})",
    "step_lsfg": "lsfg-vk {mult}×: jogo travado em {cap} fps → {out} fps na tela",
    "warn_anticheat": "Anticheat ({names}): o Uplift não injeta DLLs neste jogo",
    "warn_opengl": "Jogo OpenGL: camadas Vulkan (vkBasalt, lsfg-vk) não funcionam",
    "warn_need_vkbasalt": "O vkBasalt não está instalado",
    "warn_need_lsfg": "O lsfg-vk não está instalado",
    "warn_need_lossless": "O Lossless Scaling (Steam) não está instalado — o lsfg-vk precisa dele",
    "warn_lsfg_branch": "Lossless Scaling: mude para o beta 'lsfg-vk' na Steam (Propriedades → Betas)",
    "warn_winefsr_ge": "Só funciona com o GE-Proton (escolha na aba Compatibilidade do jogo)",
    "warn_dlss_gtx": "Jogo só com DLSS numa NVIDIA sem RTX: experimental (spoof de GPU + fakenvapi)",
    "blocked_anticheat": "Bloqueado: o jogo tem anticheat",
    "blocked_unreal_run_once": "Abra o jogo uma vez para ele criar a configuração e volte aqui",
    "blocked_no_exe": "Não achei o executável do jogo",
    "blocked_proxy_taken": "Todos os nomes de DLL proxy estão ocupados (ReShade/outros mods?)",
    "blocked_need_gamescope": "O gamescope não está instalado",
    "fix_command_typo": "Corrigido um erro de digitação no %command%",
    "fix_gamemode": "'gamemode' → 'gamemoderun'",
    "tools": "Ferramentas", "missing_tools": "Ferramentas opcionais faltando: {names}",
    "install_hint": "Instale: {cmd}",
}


def _lang() -> str:
    v = os.environ.get("UPLIFT_LANG") or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") \
        or os.environ.get("LANG") or (locale.getlocale()[0] or "")
    return "pt" if v.lower().startswith("pt") else "en"


LANG = _lang()
_TABLE = {**EN, **PT} if LANG == "pt" else EN


def t(key: str, **args) -> str:
    s = _TABLE.get(key, EN.get(key, key))
    try:
        return s.format(**args) if args else s
    except (KeyError, ValueError, IndexError):
        return s
