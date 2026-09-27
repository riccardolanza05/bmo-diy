from bmo_face.animazione import (
    _TEMPI_BATTITO,
    ComandoFaccia,
    Renderer,
    in_battito,
    indice_corpo,
    indice_da_livello,
)
from bmo_face.build_face import costruisci


def test_in_battito_e_raro_nel_tempo():
    # ~150 ms di battito ogni 2-4.5 s: su un lungo campione la frazione di
    # tempo "chiuso" deve restare piccola, non un occhio che sbatte sempre.
    campioni = [i * 0.01 for i in range(4700)]  # un intero superperiodo, passo 10 ms
    frazione = sum(in_battito(t) for t in campioni) / len(campioni)
    assert 0.01 < frazione < 0.15


def test_in_battito_non_e_periodico_a_intervallo_fisso():
    # L'irregolarità è il punto (§2.11): gli intervalli fra un battito e il
    # successivo non devono essere tutti uguali.
    intervalli = [b - a for a, b in zip(_TEMPI_BATTITO, _TEMPI_BATTITO[1:])]
    assert len(set(round(i, 2) for i in intervalli)) > 1


def test_indice_corpo_idle_segue_il_battito():
    _, manifesto = costruisci(16, 16)
    primo_battito = _TEMPI_BATTITO[0]
    assert indice_corpo("idle", 0.0, manifesto) == 0
    assert indice_corpo("idle", primo_battito, manifesto) == manifesto.corpo["idle"].frames - 1


def test_indice_corpo_stato_statico_e_sempre_zero():
    _, manifesto = costruisci(16, 16)
    assert indice_corpo("parlato", 0.0, manifesto) == 0
    assert indice_corpo("parlato", 123.4, manifesto) == 0


def test_indice_da_livello_clampa_fuori_range():
    assert indice_da_livello(-1.0, 5) == 0
    assert indice_da_livello(2.0, 5) == 4
    assert indice_da_livello(0.5, 5) == 2
    assert indice_da_livello(0.5, 1) == 0


def test_renderer_disegna_dimensioni_corrette():
    dati, manifesto = costruisci(48, 32)
    renderer = Renderer(manifesto, dati)
    immagine = renderer.disegna(ComandoFaccia(stato="idle"), 0.0)
    assert immagine.size == (48, 32)


def test_renderer_bocca_segue_linviluppo_durante_parlato():
    dati, manifesto = costruisci(48, 32)
    renderer = Renderer(manifesto, dati)
    parlato_muto = renderer.disegna(
        ComandoFaccia(stato="parlato", inviluppo=[0.0], inviluppo_inizio=0.0), 0.0
    )
    parlato_aperto = renderer.disegna(
        ComandoFaccia(stato="parlato", inviluppo=[1.0], inviluppo_inizio=0.0), 0.0
    )
    assert parlato_muto.tobytes() != parlato_aperto.tobytes()
    # In "idle" l'inviluppo non deve avere nessun effetto: non c'è overlay bocca.
    idle_a = renderer.disegna(ComandoFaccia(stato="idle", inviluppo=[0.0], inviluppo_inizio=0.0), 0.3)
    idle_b = renderer.disegna(ComandoFaccia(stato="idle", inviluppo=[1.0], inviluppo_inizio=0.0), 0.3)
    assert idle_a.tobytes() == idle_b.tobytes()


def test_livello_bocca_campiona_linviluppo_nel_tempo():
    from bmo_face.animazione import livello_bocca

    comando = ComandoFaccia(inviluppo=[0.1, 0.5, 0.9], inviluppo_fps=10.0, inviluppo_inizio=2.0)
    assert livello_bocca(comando, 2.0) == 0.1  # campione 0 (trascorso 0 s)
    assert livello_bocca(comando, 2.15) == 0.5  # campione 1 (trascorso 0.15 s * 10 fps = 1.5 -> 1)
    assert livello_bocca(comando, 2.25) == 0.9  # campione 2
    assert livello_bocca(comando, 2.5) == 0.0  # oltre la fine (3 campioni = 0.3 s): bocca chiusa
    assert livello_bocca(ComandoFaccia(), 5.0) == 0.0  # nessun inviluppo attivo


def test_renderer_pupille_solo_durante_ascolto():
    # Risoluzione più vicina a un pannello vero: lo scarto delle pupille è
    # in frazione di pixel dell'occhio, e su una tela minuscola (48×32) può
    # arrotondare allo stesso pixel per tutti i livelli — non un bug del
    # renderer, solo una scala di prova sbagliata per questa asserzione.
    dati, manifesto = costruisci(160, 120)
    renderer = Renderer(manifesto, dati)
    ascolto_basso = renderer.disegna(ComandoFaccia(stato="ascolto", livello=0.0), 0.0)
    ascolto_alto = renderer.disegna(ComandoFaccia(stato="ascolto", livello=1.0), 0.0)
    assert ascolto_basso.tobytes() != ascolto_alto.tobytes()


def test_renderer_espressione_scade():
    dati, manifesto = costruisci(48, 32)
    renderer = Renderer(manifesto, dati)
    comando = ComandoFaccia(stato="parlato", espressione="felice", espressione_scadenza=1.0)
    con_espressione = renderer.disegna(comando, 0.5)
    dopo_scadenza = renderer.disegna(comando, 1.5)
    senza_espressione = renderer.disegna(ComandoFaccia(stato="parlato"), 1.5)
    assert con_espressione.tobytes() != dopo_scadenza.tobytes()
    assert dopo_scadenza.tobytes() == senza_espressione.tobytes()


def test_renderer_timer_disegna_qualcosa_di_diverso_dal_corpo_nudo():
    dati, manifesto = costruisci(64, 48)
    renderer = Renderer(manifesto, dati)
    con_countdown = renderer.disegna(ComandoFaccia(stato="timer", timer_rimanente=125, timer_etichetta="pasta"), 0.0)
    senza_countdown = renderer._fotogramma(
        manifesto.corpo["timer"].offset, 0, manifesto.larghezza, manifesto.altezza
    )
    assert con_countdown.tobytes() != senza_countdown.tobytes()


def test_renderer_e_puro_stesso_input_stesso_risultato():
    dati, manifesto = costruisci(32, 24)
    renderer = Renderer(manifesto, dati)
    comando = ComandoFaccia(stato="pensiero")
    a = renderer.disegna(comando, 1.234).tobytes()
    b = renderer.disegna(comando, 1.234).tobytes()
    assert a == b


def test_renderer_stato_sconosciuto_non_va_in_crash():
    # Trovato dal vivo il 26/9: brain.py mandava per sbaglio un'espressione
    # ("felice") a mostra() invece che a esprimi() — FacciaSocket la
    # inoltrava fedelmente, e il renderer andava in KeyError. Corretto in
    # brain.py, ma il renderer deve restare comunque robusto a qualunque
    # stato sconosciuto arrivi dal socket: non è l'unico bug possibile.
    dati, manifesto = costruisci(32, 24)
    renderer = Renderer(manifesto, dati)
    immagine = renderer.disegna(ComandoFaccia(stato="felice"), 0.0)
    assert immagine.size == (32, 24)
    atteso = renderer.disegna(ComandoFaccia(stato="idle"), 0.0)
    assert immagine.tobytes() == atteso.tobytes()
