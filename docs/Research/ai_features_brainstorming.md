# Brainstorming e Ricerca: Estensioni AI e Custom UI per Google Drive

Questo documento esplora la fattibilità, le opzioni e le architetture per creare un sistema intelligente che aiuti a categorizzare, valutare e organizzare i file su Google Drive (es. memo vocali, documenti fiscali) tramite l'uso dell'Intelligenza Artificiale.

## 1. Funzionalità Native di Google Drive e AI

### 1.1 Metadati e Categorizzazione (Drive Labels API)
Google Drive offre la **Drive Labels API**, che permette di aggiungere metadati strutturati (etichette/tag) a file e cartelle (es. tag "Da Valutare", "Bozza", "Anno 2026").
- **Vantaggi**: Facilita enormemente la ricerca nativa in Drive.
- **Limiti da Verificare**: Le Drive Labels sono spesso una feature ristretta agli account **Google Workspace** aziendali. Se usi un account Google personale (@gmail.com / Google One), potremmo dover optare per una soluzione alternativa (es. salvare i tag nel nome del file, o in un database collegato alla nostra app).

### 1.2 Interpretazione AI dei Documenti
- **Classificazione Nativa**: Nelle versioni aziendali, Drive usa Gemini per auto-classificare i documenti in base a regole.
- **Il nostro Approccio Custom (Consigliato)**: Creare una pipeline nel nostro backend Python. L'app rileva un nuovo file, lo invia alle API di **Gemini (Google AI Studio)** per l'analisi (estrazione testo, categorizzazione), e in base alla risposta AI decide in quale cartella spostarlo e come rinominarlo.

## 2. Scenari Applicativi (App per Cartella)

Creare un'estensione con UI personalizzata a seconda del contesto della cartella è un pattern utilissimo e fattibile. Lo svilupperemo come moduli separati nella nostra web app.

### 2.1 Valutatore di Memo Vocali (Idee Musicali)
- **Flusso Proposto**: 
  1. Caricamento del memo vocale nell'app (o rilevamento automatico dalla cartella Drive "Memo Grezzi").
  2. Il backend converte l'audio in testo (usando Whisper o Google Speech-to-Text API). Note: le recenti API di Gemini 1.5 Pro supportano direttamente l'input audio nativo!
  3. L'audio viene passato a Gemini AI con il prompt: *"Valuta questa registrazione vocale musicale, estrai parole chiave, sentiment e categorizza se è un ritornello, una strofa o un'idea confusa"*.
  4. L'app mostra il memo in una UI tipo "Player Musicale", con la valutazione dell'AI affiancata. Puoi aggiungere note manuali, un voto da 1 a 5, e cliccare "Approva".
  5. Una volta approvato, il file viene spostato nella cartella definitiva (es. `Progetti Musicali/Bozze`).

### 2.2 Gestione Documenti Fiscali (Dichiarazioni e Pagamenti)
- **Flusso Proposto**:
  1. Una sezione dell'app (es. `/taxes`) mostra una **Checklist** di documenti necessari per il commercialista (es. F24, Fatture, CU).
  2. L'utente carica un file.
  3. L'AI (Gemini Vision) legge il PDF/immagine per verificare che sia effettivamente il documento richiesto (es. verifica che ci sia scritto "Modello F24").
  4. Se validato, il file viene rinominato in modo standard (es. `2026_06_F24_Pagato.pdf`), spostato nella cartella fiscale corretta su Drive, e il task nella dashboard viene segnato come "Completato".

## 3. Architettura Suggerita

Visto che stiamo già creando un applicativo con backend Python, possiamo integrare tutto questo senza ricorrere a piattaforme terze a pagamento, mantenendo il pieno controllo.

- **Storage**: Google Drive API (per caricare, spostare cartelle, rinominare).
- **Intelligenza Artificiale**: Gemini API (per capire cosa c'è nei file audio, pdf, immagini e testi).
- **Database Locale (Shadow DB)**: Un semplice database (es. SQLite) integrato nella nostra app. È fondamentale! Salverà lo "stato" dei task (cosa manca da caricare) e i tag/valutazioni dei memo vocali, mappandoli agli ID dei file su Drive. Questo evita di fare richieste lente a Google Drive ad ogni click.
## Decisioni Prese (Piano d'Azione)

Sulla base delle preferenze accordate, il progetto procederà con queste direttive:
1. **Applicativo Separato**: Creeremo un'applicazione Web dedicata (es. `drive-ai-manager`) separata dall'attuale strumento di migrazione Dropbox.
2. **Gestione Metadati Ibrida (Shadow DB Locale)**: Utilizzeremo un **Database Locale** nell'applicativo per salvare i tag, le valutazioni AI e le categorie, garantendo velocità nell'interfaccia utente.
