"""Tipo de armadura e atributo primário por classe.

Valores do jogo (WoW 12.1.5). Ficam aqui, fora do pacote ``web``, para que o
pacote ``masmorras`` e a heurística os usem sem depender da camada web.
"""

from __future__ import annotations

_TECIDO = {"warlock", "priest", "mage"}
_COURO = {"druid", "rogue", "monk", "demonhunter"}
_MALHA = {"hunter", "shaman", "evoker"}
_PLACA = {"warrior", "paladin", "deathknight"}
_FORCA = {"warrior", "paladin", "deathknight"}
_AGILIDADE = {"rogue", "hunter", "monk", "demonhunter"}


def tipo_armadura_da_classe(classe: str | None) -> str:
    """Mapeia a classe para o tipo de armadura real: tecido, couro, malha ou placa.

    Antes, classes de malha/placa caíam em tecido silenciosamente, gerando pools
    com armadura ilegal para Caçadores/Xamãs/Evocadores e Guerreiros/Paladinos/DKs.
    """
    nome = (classe or "").lower()
    if nome in _PLACA:
        return "placa"
    if nome in _MALHA:
        return "malha"
    if nome in _COURO:
        return "couro"
    if nome in _TECIDO:
        return "tecido"
    return "tecido"


def atributo_da_classe(classe: str | None) -> str:
    nome = (classe or "").lower()
    if nome in _FORCA:
        return "Força"
    if nome in _AGILIDADE:
        return "Agilidade"
    return "Intelecto"
