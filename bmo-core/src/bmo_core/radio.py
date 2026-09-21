"""La radio di BMO: sintonizzarsi, scorrere le stazioni, salvare quelle belle.

Niente libreria musicale locale: riempire una microSD di file è una noia, e
una radio non si riempie. Quindi tutto quello che riguarda la musica passa di
qui, e "metti un po' di jazz" diventa una stazione che suona jazz.

Ci sono due elenchi, e la differenza conta:

- le **preferite**, salvate in `<cartella dati>/radio.json`, che sono le tue e
  restano anche senza rete (l'indirizzo sì, il suono no);
- i **risultati di una ricerca** su radio-browser.info, l'elenco pubblico e
  gratuito di radio online, che serve a trovarne di nuove.

Scorrere avanti e indietro (`successivo`, `precedente`) si muove sull'elenco
che si sta ascoltando in quel momento: le preferite se hai chiesto una delle
tue, i risultati della ricerca se stai esplorando. Quando ne passa una che
piace, `salva_stazione` la mette fra le preferite — con il nome che vuoi tu,
e con la frequenza se il nome ne contiene una, così "quella sui 101 e 7"
continua a funzionare.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from .adapters import LettoreAdapter, VolumeAdapter, crea_lettore, crea_volume
from .config import percorso_dati

# Elenco pubblico di radio online: nessuna chiave, nessun account.
INDIRIZZO_ELENCO = "https://all.api.radio-browser.info/json/stations/search"
QUANTE = 8  # quante stazioni tenere in un elenco da scorrere
PAESE_PREDEFINITO = "IT"
_FREQUENZA = re.compile(r"\b(\d{2,3}[.,]\d{1,2})\b")


@dataclass
class Stazione:
    nome: str
    url: str
    frequenza: str | None = None
    paese: str = ""


def _parole(testo: str) -> list[str]:
    return [p for p in "".join(c if c.isalnum() else " " for c in (testo or "").lower()).split() if p]


def frequenza_nel_nome(nome: str) -> str | None:
    """"Radio Deejay 107.0" → "107.0". Le radio online spesso si chiamano così."""
    trovata = _FREQUENZA.search(nome or "")
    return trovata.group(1).replace(",", ".") if trovata else None


def _con_httpx(parametri: dict[str, Any]) -> list[dict[str, Any]]:
    import httpx  # arriva con l'SDK di Gemini; importata qui per partire anche senza rete

    risposta = httpx.get(
        INDIRIZZO_ELENCO,
        params=parametri,
        headers={"User-Agent": "bmo-diy/0.1"},
        timeout=8.0,
        follow_redirects=True,
    )
    risposta.raise_for_status()
    return risposta.json()


def cerca_stazioni(
    query: str = "",
    quante: int = QUANTE,
    richiesta: Callable[[dict[str, Any]], list[dict[str, Any]]] = _con_httpx,
) -> list[Stazione]:
    """Cerca stazioni per nome o per genere; senza query, le più ascoltate in Italia."""
    parametri: dict[str, Any] = {
        "limit": quante,
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
    }
    if query.strip():
        parametri["name"] = query.strip()
    else:
        parametri["countrycode"] = PAESE_PREDEFINITO
    trovate = richiesta(parametri)
    if not trovate and query.strip():
        # Nessuna stazione si chiama così: forse è un genere ("jazz", "rock").
        trovate = richiesta({**parametri, "name": None, "tag": query.strip()})
    stazioni: list[Stazione] = []
    # L'elenco pubblico ha piu' voci per la stessa radio (indirizzi diversi,
    # stesso nome): scorrere tre "Radio Deejay" di fila non serve a niente.
    gia_viste: set[str] = set()
    for dato in trovate or []:
        indirizzo = dato.get("url_resolved") or dato.get("url") or ""
        nome = (dato.get("name") or "").strip()
        if not indirizzo or not nome or nome.lower() in gia_viste:
            continue
        gia_viste.add(nome.lower())
        stazioni.append(Stazione(nome, indirizzo, frequenza_nel_nome(nome), dato.get("country", "")))
    return stazioni[:quante]


def carica_preferite(percorso: Path) -> list[Stazione]:
    """Le stazioni salvate. Un file mancante o rotto non deve fermare BMO."""
    try:
        dato = json.loads(percorso.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if isinstance(dato, dict):  # vecchio formato: {"nome": "indirizzo"}
        return [Stazione(str(k), str(v), frequenza_nel_nome(str(k))) for k, v in dato.items()]
    preferite = []
    for riga in dato if isinstance(dato, list) else []:
        if isinstance(riga, dict) and riga.get("nome") and riga.get("url"):
            preferite.append(
                Stazione(
                    str(riga["nome"]),
                    str(riga["url"]),
                    riga.get("frequenza"),
                    str(riga.get("paese", "")),
                )
            )
    return preferite


def salva_preferite(percorso: Path, stazioni: list[Stazione]) -> None:
    """Scrittura atomica, come per i timer: un file a metà perderebbe tutto."""
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=percorso.parent, prefix=".radio-", delete=False
    ) as file:
        json.dump([asdict(s) for s in stazioni], file, ensure_ascii=False, indent=1)
        file.flush()
        os.fsync(file.fileno())
        temporaneo = Path(file.name)
    temporaneo.replace(percorso)


class Radio:
    """Gli strumenti del suono: radio, controlli e volume."""

    def __init__(
        self,
        lettore: LettoreAdapter | None = None,
        volume: VolumeAdapter | None = None,
        percorso: Path | None = None,
        cercatore: Callable[..., list[Stazione]] = cerca_stazioni,
    ) -> None:
        self.lettore = lettore or crea_lettore()
        self.volume = volume or crea_volume()
        self.percorso = Path(percorso) if percorso else percorso_dati() / "radio.json"
        self.cercatore = cercatore
        self.preferite = carica_preferite(self.percorso)
        # L'elenco che si sta scorrendo e dove siamo arrivati.
        self.elenco: list[Stazione] = []
        self.posizione = -1

    def registra(self, cervello: Any) -> None:
        cervello.registra_strumento("riproduci_musica", self.riproduci)
        cervello.registra_strumento("controllo_riproduzione", self.controllo)
        cervello.registra_strumento("salva_stazione", self.salva_stazione)
        cervello.registra_strumento("elenca_stazioni", self.elenca_stazioni)
        cervello.registra_strumento("regola_volume", self.regola_volume)

    # --- stato interno -------------------------------------------------------

    @property
    def in_ascolto(self) -> Stazione | None:
        if 0 <= self.posizione < len(self.elenco):
            return self.elenco[self.posizione]
        return None

    @contextmanager
    def sospesa(self) -> Iterator[None]:
        """Mette in pausa la radio per la durata del blocco, se sta suonando.

        Il microfono aperto durante l'ascolto (o la conferma, #17) sente la
        radio come se fosse voce: con il volume alto il VAD non distingue
        più niente. Se non ha mai suonato non fa nulla — chiamare `pausa()`
        accenderebbe un mpv idle inutilmente. Non distingue una radio già in
        pausa per un comando esplicito da una che sta suonando: la si
        riprenderà comunque alla fine del blocco, un limite noto e accettato
        per ora.
        """
        if not self.lettore.in_riproduzione():
            yield
            return
        self.lettore.pausa()
        try:
            yield
        finally:
            self.lettore.riprendi()

    def _sintonizza(self, posizione: int) -> dict[str, Any]:
        self.posizione = posizione
        stazione = self.elenco[posizione]
        self.lettore.riproduci([stazione.url])
        risultato = {
            "stato": "ok",
            "stazione": stazione.nome,
            "posizione": f"{posizione + 1} di {len(self.elenco)}",
        }
        if stazione.frequenza:
            risultato["frequenza"] = stazione.frequenza
        return risultato

    def _fra_le_preferite(self, query: str) -> int | None:
        parole = _parole(query)
        if not parole:
            return None
        for numero, stazione in enumerate(self.preferite):
            cercabile = _parole(f"{stazione.nome} {stazione.frequenza or ''}")
            if any(p in cercabile for p in parole):
                return numero
        return None

    # --- gli strumenti -------------------------------------------------------

    def riproduci(self, query: str = "") -> dict[str, Any]:
        """Accende la radio: prima cerca fra le preferite, poi sull'elenco online."""
        trovata = self._fra_le_preferite(query)
        if trovata is not None:
            self.elenco = list(self.preferite)
            return {**self._sintonizza(trovata), "elenco": "preferite"}
        if not query.strip() and self.preferite:
            self.elenco = list(self.preferite)
            return {**self._sintonizza(0), "elenco": "preferite"}
        try:
            stazioni = self.cercatore(query)
        except Exception as errore:
            # Sotto c'è la rete e un servizio di terzi: BMO lo dice e tira avanti.
            return {"stato": "errore", "motivo": f"non riesco a cercare le stazioni ({type(errore).__name__})"}
        if not stazioni:
            return {"stato": "non_trovato", "query": query}
        self.elenco = stazioni
        return {**self._sintonizza(0), "elenco": "risultati della ricerca"}

    def controllo(self, azione: str) -> dict[str, Any]:
        if azione in ("successivo", "precedente"):
            return self._scorri(1 if azione == "successivo" else -1)
        azioni = {"pausa": self.lettore.pausa, "riprendi": self.lettore.riprendi, "stop": self.lettore.stop}
        if azione not in azioni:
            raise ValueError(f"azione deve essere una fra: pausa, riprendi, stop, successivo, precedente")
        if not self.lettore.in_riproduzione():
            return {"stato": "niente_in_riproduzione"}
        azioni[azione]()
        if azione == "stop":
            self.elenco, self.posizione = [], -1
        return {"stato": "ok", "azione": azione}

    def _scorri(self, passo: int) -> dict[str, Any]:
        """Avanti e indietro di una stazione, girando in tondo come una manopola."""
        if not self.elenco:
            return {"stato": "niente_in_riproduzione"}
        return self._sintonizza((self.posizione + passo) % len(self.elenco))

    def salva_stazione(self, nome: str | None = None) -> dict[str, Any]:
        """Mette fra le preferite quella che sta suonando adesso."""
        stazione = self.in_ascolto
        if stazione is None:
            return {"stato": "niente_in_riproduzione"}
        if any(p.url == stazione.url for p in self.preferite):
            return {"stato": "gia_salvata", "stazione": stazione.nome}
        etichetta = (nome or "").strip() or stazione.nome
        # La frequenza può stare nel nome della stazione o in quello che hai detto tu.
        salvata = Stazione(
            nome=etichetta,
            url=stazione.url,
            frequenza=frequenza_nel_nome(etichetta) or stazione.frequenza,
            paese=stazione.paese,
        )
        self.preferite.append(salvata)
        salva_preferite(self.percorso, self.preferite)
        # Da qui in poi si scorre fra le preferite: è quello che hai appena scelto.
        risultato = {"stato": "ok", "salvata": salvata.nome, "preferite": len(self.preferite)}
        if salvata.frequenza:
            risultato["frequenza"] = salvata.frequenza
        return risultato

    def elenca_stazioni(self) -> dict[str, Any]:
        return {
            "preferite": [
                {"nome": s.nome, **({"frequenza": s.frequenza} if s.frequenza else {})}
                for s in self.preferite
            ]
        }

    def regola_volume(self, percentuale: int) -> dict[str, Any]:
        percentuale = int(percentuale)
        if not 0 <= percentuale <= 100:
            raise ValueError("percentuale deve essere fra 0 e 100")
        self.volume.imposta(percentuale)
        return {"stato": "ok", "percentuale": percentuale}
