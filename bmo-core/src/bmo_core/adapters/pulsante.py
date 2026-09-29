"""Adapter per il pulsante extra del HAT audio (issue #70).

Il HAT audio WM8960, comprato usato, è arrivato con un bottone in più
oltre a quello di serie (documentato da Waveshare su GPIO17/BCM17): un
proprietario precedente l'ha aggiunto, e il pin a cui è cablato non è
ancora noto — va tracciato a mano con un multimetro sulla scheda reale.
Per questo `PulsanteGpio` prende il pin come parametro esplicito, e la
fabbrica (`factory.crea_pulsante`) resta su `PulsanteAssente` finché non
viene configurato: meglio un bottone inerte che uno che legge un pin a
caso.
"""
from __future__ import annotations


class PulsanteGpio:
    """Il pulsante vero, su un pin BCM del Raspberry Pi.

    `gpiozero` si importa qui dentro, non in testa al modulo: è una
    dipendenza che ha senso solo sul Pi, stesso principio di `onnxruntime`
    in `wake_word.py` o di `edge-tts` in `tts.py` — non deve pesare
    sull'avvio di chi non la usa.

    `pull_up=True`: il pin resta alto a riposo e va a massa quando il
    bottone chiude il circuito verso GND — il cablaggio più comune per un
    bottone a due terminali su un HAT. Se il bottone tracciato risultasse
    cablato al contrario, `pull_up=False` è il parametro da cambiare qui,
    non altrove.
    """

    def __init__(self, pin: int, pull_up: bool = True) -> None:
        from gpiozero import Button

        self.pin = pin
        self._bottone = Button(pin, pull_up=pull_up)

    def premuto(self) -> bool:
        return bool(self._bottone.is_pressed)


class PulsanteAssente:
    """Nessun bottone collegato: sempre `False`.

    Predefinito sul PC di sviluppo (niente GPIO) e sul Pi finché
    `BMO_PULSANTE_PIN` non è impostata — il pin del bottone extra non è
    ancora tracciato, quindi non c'è un default sicuro da indovinare.
    """

    def premuto(self) -> bool:
        return False
